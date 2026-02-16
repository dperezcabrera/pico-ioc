"""Scope management for component lifecycles.

Provides :class:`ScopeProtocol`, :class:`ContextVarScope`,
:class:`ScopeManager`, and :class:`ScopedCaches` -- the machinery that ties
component instances to a lifecycle (singleton, prototype, request, session,
transaction, or custom scopes).
"""

import contextvars
import inspect
import logging
from typing import Any, Dict, Optional, Tuple

from .constants import SCOPE_PROTOTYPE, SCOPE_SINGLETON
from .exceptions import ScopeError

_logger = logging.getLogger(__name__)


class ScopeProtocol:
    """Protocol for scope implementations.

    A scope implementation must provide a ``get_id()`` method that returns the
    current scope identifier (or ``None`` if the scope is not active).
    """

    def get_id(self) -> Any | None: ...


class ContextVarScope(ScopeProtocol):
    """Scope implementation backed by a :class:`contextvars.ContextVar`.

    Each scope name (e.g. ``"request"``) gets its own ``ContextVar``. The
    scope is activated by setting the var to a scope ID and deactivated by
    resetting it.

    Args:
        var: The context variable that stores the scope identifier.
    """
    def __init__(self, var: contextvars.ContextVar) -> None:
        self._var = var

    def get_id(self) -> Any | None:
        return self._var.get()

    def activate(self, scope_id: Any) -> contextvars.Token:
        return self._var.set(scope_id)

    def deactivate(self, token: contextvars.Token) -> None:
        self._var.reset(token)


class ComponentContainer:
    def __init__(self) -> None:
        self._instances: Dict[object, object] = {}

    def get(self, key):
        return self._instances.get(key)

    def put(self, key, value):
        self._instances[key] = value

    def items(self):
        return list(self._instances.items())


class _NoCacheContainer(ComponentContainer):
    def __init__(self) -> None:
        pass

    def get(self, key):
        return None

    def put(self, key, value):
        return

    def items(self):
        return []


class ScopeManager:
    """Registry and coordinator for all scope implementations.

    Pre-registers the built-in context-aware scopes (``request``, ``session``,
    ``websocket``, ``transaction``) and allows custom scopes to be added via
    :meth:`register_scope`.
    """

    def __init__(self) -> None:
        self._scopes: Dict[str, ScopeProtocol] = {
            "request": ContextVarScope(contextvars.ContextVar("pico_request_id", default=None)),
            "session": ContextVarScope(contextvars.ContextVar("pico_session_id", default=None)),
            "websocket": ContextVarScope(contextvars.ContextVar("pico_websocket_id", default=None)),
            "transaction": ContextVarScope(contextvars.ContextVar("pico_tx_id", default=None)),
        }

    def register_scope(self, name: str) -> None:
        """Register a custom scope backed by a new ``ContextVar``.

        Args:
            name: The scope name (must be a non-empty string, not
                ``'singleton'`` or ``'prototype'``).

        Raises:
            ScopeError: If *name* is empty or is a reserved scope name.
        """
        if not isinstance(name, str) or not name:
            raise ScopeError("Scope name must be a non-empty string")
        if name in (SCOPE_SINGLETON, SCOPE_PROTOTYPE):
            raise ScopeError(f"Cannot register reserved scope: '{name}'")
        if name in self._scopes:
            return

        var_name = f"pico_{name}_id"
        context_var = contextvars.ContextVar(var_name, default=None)
        implementation = ContextVarScope(context_var)
        self._scopes[name] = implementation

    def get_id(self, name: str) -> Any | None:
        if name in (SCOPE_SINGLETON, SCOPE_PROTOTYPE):
            return None
        impl = self._scopes.get(name)
        return impl.get_id() if impl else None

    def activate(self, name: str, scope_id: Any) -> Optional[contextvars.Token]:
        if name in (SCOPE_SINGLETON, SCOPE_PROTOTYPE):
            return None
        impl = self._scopes.get(name)
        if impl is None:
            from .exceptions import ScopeError

            raise ScopeError(f"Unknown scope: {name}")
        if hasattr(impl, "activate"):
            return getattr(impl, "activate")(scope_id)
        return None

    def deactivate(self, name: str, token: Optional[contextvars.Token]) -> None:
        if name in (SCOPE_SINGLETON, SCOPE_PROTOTYPE):
            return
        impl = self._scopes.get(name)
        if impl is None:
            from .exceptions import ScopeError

            raise ScopeError(f"Unknown scope: {name}")
        if token is not None and hasattr(impl, "deactivate"):
            getattr(impl, "deactivate")(token)

    def names(self) -> Tuple[str, ...]:
        return tuple(n for n in self._scopes.keys() if n not in (SCOPE_SINGLETON, SCOPE_PROTOTYPE))

    def signature(self, names: Tuple[str, ...]) -> Tuple[Any, ...]:
        return tuple(self.get_id(n) for n in names)

    def signature_all(self) -> Tuple[Any, ...]:
        return self.signature(self.names())


class ScopedCaches:
    """Manages component instance storage across all scopes.

    Maintains a singleton cache, per-scope-id caches for context-aware scopes,
    and a no-op cache for prototype scope.
    """

    def __init__(self) -> None:
        self._singleton = ComponentContainer()
        self._by_scope: Dict[str, Dict[Any, ComponentContainer]] = {}
        self._no_cache = _NoCacheContainer()

    def _cleanup_object(self, obj: Any) -> None:
        try:
            from .constants import PICO_META
        except Exception:
            PICO_META = "_pico_meta"
        try:
            for _, m in inspect.getmembers(obj, predicate=inspect.ismethod):
                meta = getattr(m, PICO_META, {})
                if meta.get("cleanup", False):
                    try:
                        m()
                    except Exception as e:
                        _logger.warning(
                            "Cleanup method %s.%s failed: %s",
                            type(obj).__name__,
                            getattr(m, "__name__", "<unknown>"),
                            e,
                        )
        except Exception as e:
            _logger.debug("Failed to inspect object for cleanup: %s", e)

    def cleanup_scope(self, scope_name: str, scope_id: Any) -> None:
        bucket = self._by_scope.get(scope_name)
        if bucket and scope_id in bucket:
            container = bucket.pop(scope_id)
            self._cleanup_container(container)

    def _cleanup_container(self, container: "ComponentContainer") -> None:
        try:
            for _, obj in container.items():
                self._cleanup_object(obj)
        except Exception as e:
            _logger.debug("Failed to cleanup container: %s", e)

    def for_scope(self, scopes: ScopeManager, scope: str) -> ComponentContainer:
        if scope == SCOPE_SINGLETON:
            return self._singleton
        if scope == SCOPE_PROTOTYPE:
            return self._no_cache

        sid = scopes.get_id(scope)

        if sid is None:
            raise ScopeError(
                f"Cannot resolve component in scope '{scope}': No active scope ID found. "
                f"Are you trying to use a {scope}-scoped component outside of its context?"
            )

        bucket = self._by_scope.setdefault(scope, {})
        if sid in bucket:
            return bucket[sid]

        c = ComponentContainer()
        bucket[sid] = c
        return c

    def all_items(self):
        for item in self._singleton.items():
            yield item
        for b in self._by_scope.values():
            for c in b.values():
                for item in c.items():
                    yield item

    def shrink(self, scope: str, keep: int) -> None:
        if scope in (SCOPE_SINGLETON, SCOPE_PROTOTYPE):
            return
        bucket = self._by_scope.get(scope)
        if not bucket:
            return

        # Manual cleanup if needed, though we rely on explicit cleanup now
        if len(bucket) > keep:
            # Simple eviction strategy if forced manually
            keys_to_remove = list(bucket.keys())[: len(bucket) - keep]
            for k in keys_to_remove:
                container = bucket.pop(k)
                self._cleanup_container(container)
