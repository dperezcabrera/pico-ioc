# src/pico_ioc/scope.py
import contextvars
import inspect
from typing import Any, Dict, Optional, Tuple
from collections import OrderedDict

class ScopeProtocol:
    def get_id(self) -> Any | None: ...

class ContextVarScope(ScopeProtocol):
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
    def __init__(self) -> None:
        self._scopes: Dict[str, ScopeProtocol] = {
            "request": ContextVarScope(contextvars.ContextVar("pico_request_id", default=None)),
            "session": ContextVarScope(contextvars.ContextVar("pico_session_id", default=None)),
            "transaction": ContextVarScope(contextvars.ContextVar("pico_tx_id", default=None)),
        }
    def register_scope(self, name: str, implementation: ScopeProtocol) -> None:
        if not isinstance(name, str) or not name:
            from .exceptions import ScopeError
            raise ScopeError("Scope name must be a non-empty string")
        if name in ("singleton", "prototype"):
            from .exceptions import ScopeError
            raise ScopeError("Cannot register or override reserved scopes: 'singleton' or 'prototype'")
        self._scopes[name] = implementation
    def get_id(self, name: str) -> Any | None:
        if name in ("singleton", "prototype"):
            return None
        impl = self._scopes.get(name)
        return impl.get_id() if impl else None
    def activate(self, name: str, scope_id: Any) -> Optional[contextvars.Token]:
        if name in ("singleton", "prototype"):
            return None
        impl = self._scopes.get(name)
        if impl is None:
            from .exceptions import ScopeError
            raise ScopeError(f"Unknown scope: {name}")
        if hasattr(impl, "activate"):
            return getattr(impl, "activate")(scope_id)
        return None
    def deactivate(self, name: str, token: Optional[contextvars.Token]) -> None:
        if name in ("singleton", "prototype"):
            return
        impl = self._scopes.get(name)
        if impl is None:
            from .exceptions import ScopeError
            raise ScopeError(f"Unknown scope: {name}")
        if token is not None and hasattr(impl, "deactivate"):
            getattr(impl, "deactivate")(token)
    def names(self) -> Tuple[str, ...]:
        return tuple(n for n in self._scopes.keys() if n not in ("singleton", "prototype"))
    def signature(self, names: Tuple[str, ...]) -> Tuple[Any, ...]:
        return tuple(self.get_id(n) for n in names)
    def signature_all(self) -> Tuple[Any, ...]:
        return self.signature(self.names())

class ScopedCaches:
    def __init__(self, max_scopes_per_type: int = 2048) -> None:
        self._singleton = ComponentContainer()
        self._by_scope: Dict[str, OrderedDict[Any, ComponentContainer]] = {}
        self._max = int(max_scopes_per_type)
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
                    except Exception:
                        pass
        except Exception:
            pass
            
    def cleanup_scope(self, scope_name: str, scope_id: Any) -> None:
        bucket = self._by_scope.get(scope_name)
        if bucket and scope_id in bucket:
            container = bucket.pop(scope_id)
            self._cleanup_container(container)

    def _cleanup_container(self, container: "ComponentContainer") -> None:
        try:
            for _, obj in container.items():
                self._cleanup_object(obj)
        except Exception:
            pass

    def for_scope(self, scopes: ScopeManager, scope: str) -> ComponentContainer:
        if scope == "singleton":
            return self._singleton
        if scope == "prototype":
            return self._no_cache
        sid = scopes.get_id(scope)
        bucket = self._by_scope.setdefault(scope, OrderedDict())
        if sid in bucket:
            c = bucket.pop(sid)
            bucket[sid] = c
            return c
        if len(bucket) >= self._max:
            _, old = bucket.popitem(last=False)
            self._cleanup_container(old)
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
        if scope in ("singleton", "prototype"):
            return
        bucket = self._by_scope.get(scope)
        if not bucket:
            return
        k = max(0, int(keep))
        while len(bucket) > k:
            _, old = bucket.popitem(last=False)
            self._cleanup_container(old)

