"""Decorators for registering components, factories, and providers.

This module contains the core decorator API used to mark classes and functions
for discovery by the pico-ioc container: :func:`component`, :func:`factory`,
:func:`provides`, :func:`configured`, :func:`configure`, and :func:`cleanup`.
"""

import inspect
import typing
from dataclasses import MISSING
from typing import Any, Callable, Dict, Iterable, Optional

from .constants import PICO_INFRA, PICO_KEY, PICO_META, PICO_NAME


def _meta_get(obj: Any) -> Dict[str, Any]:
    m = getattr(obj, PICO_META, None)
    if m is None:
        m = {}
        setattr(obj, PICO_META, m)
    return m


def _apply_common_metadata(
    obj: Any,
    *,
    qualifiers: Iterable[str] = (),
    scope: str = "singleton",
    primary: bool = False,
    lazy: bool = False,
    conditional_profiles: Iterable[str] = (),
    conditional_require_env: Iterable[str] = (),
    conditional_predicate: Optional[Callable[[], bool]] = None,
    on_missing_selector: Optional[object] = None,
    on_missing_priority: int = 0,
):
    m = _meta_get(obj)
    m["qualifier"] = tuple(str(q) for q in qualifiers or ())
    m["scope"] = scope

    if primary:
        m["primary"] = True
    if lazy:
        m["lazy"] = True

    has_conditional = conditional_profiles or conditional_require_env or conditional_predicate is not None

    if has_conditional:
        m["conditional"] = {
            "profiles": tuple(p for p in conditional_profiles or ()),
            "require_env": tuple(e for e in conditional_require_env or ()),
            "predicate": conditional_predicate,
        }

    if on_missing_selector is not None:
        m["on_missing"] = {"selector": on_missing_selector, "priority": int(on_missing_priority)}
    return obj


def component(
    cls=None,
    *,
    name: Any = None,
    qualifiers: Iterable[str] = (),
    scope: str = "singleton",
    primary: bool = False,
    lazy: bool = False,
    conditional_profiles: Iterable[str] = (),
    conditional_require_env: Iterable[str] = (),
    conditional_predicate: Optional[Callable[[], bool]] = None,
    on_missing_selector: Optional[object] = None,
    on_missing_priority: int = 0,
):
    """Register a class as a container-managed component.

    Can be used with or without parentheses::

        @component
        class MyService: ...

        @component(scope="request", qualifiers={"fast"})
        class FastService: ...

    Args:
        cls: The class to decorate (populated automatically when used without
            parentheses).
        name: Explicit registration key. Defaults to the class itself.
        qualifiers: String tags for multi-binding and list injection.
        scope: Lifecycle scope (``'singleton'``, ``'prototype'``, ``'request'``,
            ``'session'``, ``'transaction'``, or a custom scope name).
        primary: If ``True``, this component wins when multiple implementations
            exist for the same type.
        lazy: If ``True``, the component is wrapped in a proxy and created on
            first attribute access rather than at container startup.
        conditional_profiles: Only register when one of these profiles is active.
        conditional_require_env: Only register when all listed environment
            variables are set and non-empty.
        conditional_predicate: Only register when this callable returns ``True``.
        on_missing_selector: Register as a fallback for the given key/type if
            no other provider is bound.
        on_missing_priority: Precedence among ``on_missing`` fallbacks (higher
            wins).

    Returns:
        The decorated class, unchanged, with pico metadata attached.

    Example:
        >>> @component(scope="prototype", qualifiers={"cache"})
        ... class InMemoryCache:
        ...     pass
    """
    def dec(c):
        setattr(c, PICO_INFRA, "component")
        setattr(c, PICO_NAME, name if name is not None else getattr(c, "__name__", str(c)))
        setattr(c, PICO_KEY, name if name is not None else c)

        _apply_common_metadata(
            c,
            qualifiers=qualifiers,
            scope=scope,
            primary=primary,
            lazy=lazy,
            conditional_profiles=conditional_profiles,
            conditional_require_env=conditional_require_env,
            conditional_predicate=conditional_predicate,
            on_missing_selector=on_missing_selector,
            on_missing_priority=on_missing_priority,
        )
        return c

    return dec(cls) if cls else dec


def factory(
    cls=None,
    *,
    name: Any = None,
    qualifiers: Iterable[str] = (),
    scope: str = "singleton",
    primary: bool = False,
    lazy: bool = False,
    conditional_profiles: Iterable[str] = (),
    conditional_require_env: Iterable[str] = (),
    conditional_predicate: Optional[Callable[[], bool]] = None,
    on_missing_selector: Optional[object] = None,
    on_missing_priority: int = 0,
):
    """Register a class as a factory that produces components via ``@provides`` methods.

    A factory class groups related provider methods. The factory itself is
    instantiated by the container (with its own dependencies injected), and
    each ``@provides``-decorated method becomes a separate provider::

        @factory
        class InfraFactory:
            @provides(Database)
            def build_db(self) -> Database:
                return Database(url="sqlite://")

    Args:
        cls: The class to decorate (populated automatically when used without
            parentheses).
        name: Explicit name for the factory. Defaults to the class name.
        qualifiers: String tags inherited by the factory's providers unless
            overridden.
        scope: Default scope for provider methods that do not specify their own.
        primary: Whether the factory's providers are primary by default.
        lazy: If ``True``, the factory is lazily initialised.
        conditional_profiles: Only register when one of these profiles is active.
        conditional_require_env: Only register when all listed environment
            variables are set and non-empty.
        conditional_predicate: Only register when this callable returns ``True``.
        on_missing_selector: Fallback selector key/type.
        on_missing_priority: Fallback priority.

    Returns:
        The decorated class, unchanged, with pico metadata attached.
    """
    def dec(c):
        setattr(c, PICO_INFRA, "factory")
        setattr(c, PICO_NAME, name if name is not None else getattr(c, "__name__", str(c)))

        _apply_common_metadata(
            c,
            qualifiers=qualifiers,
            scope=scope,
            primary=primary,
            lazy=lazy,
            conditional_profiles=conditional_profiles,
            conditional_require_env=conditional_require_env,
            conditional_predicate=conditional_predicate,
            on_missing_selector=on_missing_selector,
            on_missing_priority=on_missing_priority,
        )
        return c

    return dec(cls) if cls else dec


def provides(*dargs, **dkwargs):
    """Mark a function or method as a component provider.

    ``@provides`` can be used on instance methods inside a ``@factory`` class,
    on ``@staticmethod`` / ``@classmethod`` methods, or on module-level
    functions.  The registration key is inferred from the return type annotation
    or can be given explicitly::

        @provides(Database)
        def build_db() -> Database:
            return Database(url="sqlite://")

        @provides  # key inferred from return type
        def build_cache() -> RedisCache:
            return RedisCache()

    Args:
        *dargs: Optional positional argument: the explicit registration key
            (a type or string). When omitted, the key is inferred from the
            return type annotation.
        **dkwargs: Keyword arguments forwarded to metadata (``name``,
            ``qualifiers``, ``scope``, ``primary``, ``lazy``,
            ``conditional_profiles``, ``conditional_require_env``,
            ``conditional_predicate``, ``on_missing_selector``,
            ``on_missing_priority``).

    Returns:
        The decorated function, unchanged, with pico metadata attached.

    Raises:
        TypeError: If the key cannot be inferred and is not provided.
    """
    def _apply(
        fn,
        key_hint,
        *,
        name=None,
        qualifiers=(),
        scope="singleton",
        primary=False,
        lazy=False,
        conditional_profiles=(),
        conditional_require_env=(),
        conditional_predicate=None,
        on_missing_selector=None,
        on_missing_priority=0,
    ):
        target = fn.__func__ if isinstance(fn, (staticmethod, classmethod)) else fn

        inferred_key = key_hint
        if inferred_key is MISSING:
            rt = get_return_type(target)
            if isinstance(rt, type):
                inferred_key = rt
            else:
                inferred_key = getattr(target, "__name__", str(target))

        setattr(target, PICO_INFRA, "provides")
        pico_name = (
            name
            if name is not None
            else (inferred_key if isinstance(inferred_key, str) else getattr(target, "__name__", str(target)))
        )
        setattr(target, PICO_NAME, pico_name)
        setattr(target, PICO_KEY, inferred_key)

        _apply_common_metadata(
            target,
            qualifiers=qualifiers,
            scope=scope,
            primary=primary,
            lazy=lazy,
            conditional_profiles=conditional_profiles,
            conditional_require_env=conditional_require_env,
            conditional_predicate=conditional_predicate,
            on_missing_selector=on_missing_selector,
            on_missing_priority=on_missing_priority,
        )
        return fn

    if dargs and len(dargs) == 1 and inspect.isfunction(dargs[0]) and not dkwargs:
        fn = dargs[0]
        return _apply(fn, MISSING)
    else:
        key = dargs[0] if dargs else MISSING

        def _decorator(fn):
            return _apply(fn, key, **dkwargs)

        return _decorator


class Qualifier(str):
    """A typed string used in ``Annotated`` hints for qualifier-based injection.

    Use with ``typing.Annotated`` to request a specific qualified
    implementation::

        from typing import Annotated
        from pico_ioc import Qualifier

        @component
        class OrderService:
            def __init__(self, cache: Annotated[Cache, Qualifier("fast")]):
                self.cache = cache
    """

    __slots__ = ()


def configure(fn):
    """Mark a method as a post-construction lifecycle hook.

    ``@configure`` methods are called after the component is instantiated and
    all constructor dependencies are injected.  They may themselves declare
    dependencies as parameters, which will be resolved from the container::

        @component
        class CacheService:
            @configure
            def warm_up(self, db: Database):
                self._data = db.load_all()

    Args:
        fn: The method to decorate.

    Returns:
        The same method with lifecycle metadata attached.
    """
    m = _meta_get(fn)
    m["configure"] = True
    return fn


def cleanup(fn):
    """Mark a method as a shutdown lifecycle hook.

    ``@cleanup`` methods are called when the container shuts down (via
    ``container.shutdown()`` or ``await container.ashutdown()``)::

        @component
        class ConnectionPool:
            @cleanup
            async def close(self):
                await self.pool.close()

    Args:
        fn: The method to decorate.

    Returns:
        The same method with lifecycle metadata attached.
    """
    m = _meta_get(fn)
    m["cleanup"] = True
    return fn


def configured(target: Any = "self", *, prefix: str = "", mapping: str = "auto", **kwargs):
    """Bind a dataclass to configuration sources.

    The decorated dataclass is automatically populated from the active
    ``ContextConfig`` (environment variables, JSON/YAML files, dict sources)
    at container startup::

        @configured(prefix="db")
        @dataclass
        class DbConfig:
            host: str = "localhost"
            port: int = 5432

    Args:
        target: The target type to populate. Use ``"self"`` (default) to
            populate the decorated class itself.
        prefix: Dot-separated prefix for looking up keys in the configuration
            tree (e.g., ``"db"`` looks under the ``db`` subtree).
        mapping: Binding strategy:
            ``"auto"`` (default) -- auto-detect from field types,
            ``"flat"`` -- flat key-value lookup (``PREFIX_FIELD``),
            ``"tree"`` -- recursive tree mapping from nested config.
        **kwargs: Extra keyword arguments forwarded to
            :func:`_apply_common_metadata` (``qualifiers``, ``scope``, etc.).

    Returns:
        A decorator that attaches configuration metadata to the class.

    Raises:
        ValueError: If *mapping* is not one of ``'auto'``, ``'flat'``, or
            ``'tree'``.
    """
    if mapping not in ("auto", "flat", "tree"):
        raise ValueError("mapping must be one of 'auto', 'flat', or 'tree'")

    def dec(cls):
        setattr(cls, PICO_INFRA, "configured")
        m = _meta_get(cls)
        m["configured"] = {"target": target, "prefix": prefix, "mapping": mapping}
        _apply_common_metadata(cls, **kwargs)
        return cls

    return dec


def get_return_type(fn: Callable[..., Any]) -> Optional[type]:
    """Extract the concrete return type from a callable's annotations.

    Uses ``typing.get_type_hints`` with ``include_extras=True`` to resolve
    PEP 563 deferred annotations, falling back to ``inspect.signature``.

    Args:
        fn: The callable to inspect.

    Returns:
        The return type if it is a concrete class, otherwise ``None``.
    """
    try:
        hints = typing.get_type_hints(fn, include_extras=True)
        ra = hints.get("return")
    except Exception:
        try:
            ra = inspect.signature(fn).return_annotation
        except Exception:
            return None
    if ra is None or ra is inspect._empty:
        return None
    return ra if isinstance(ra, type) else None
