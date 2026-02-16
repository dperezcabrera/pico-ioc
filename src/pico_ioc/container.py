import contextvars
import inspect
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Union, overload

from .analysis import DependencyRequest, analyze_callable_dependencies
from .aop import ContainerObserver, UnifiedComponentProxy
from .constants import LOGGER, PICO_META, SCOPE_SINGLETON
from .container_resolution import _ResolutionMixin
from .exceptions import AsyncResolutionError, ComponentCreationError, ProviderNotFoundError
from .factory import ComponentFactory
from .graph_export import _build_resolution_graph
from .graph_export import export_graph as _export_graph
from .locator import ComponentLocator
from .scope import ScopedCaches, ScopeManager

KeyT = Union[str, type]


def _normalize_callable(obj):
    return getattr(obj, "__func__", obj)


def _get_signature_safe(callable_obj):
    try:
        return inspect.signature(callable_obj)
    except (ValueError, TypeError):
        wrapped = getattr(callable_obj, "__wrapped__", None)
        if wrapped is not None:
            return inspect.signature(wrapped)
        raise


def _needs_async_configure(obj: Any) -> bool:
    for _, m in inspect.getmembers(obj, predicate=inspect.ismethod):
        meta = getattr(m, PICO_META, {})
        if meta.get("configure", False) and inspect.iscoroutinefunction(m):
            return True
    return False


def _iter_configure_methods(obj: Any):
    for _, m in inspect.getmembers(obj, predicate=inspect.ismethod):
        meta = getattr(m, PICO_META, {})
        if meta.get("configure", False):
            yield m


class PicoContainer(_ResolutionMixin):
    _container_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("pico_container_id", default=None)
    _container_registry: Dict[str, "PicoContainer"] = {}

    class _Ctx:
        def __init__(self, container_id: str, profiles: Tuple[str, ...], created_at: float) -> None:
            self.container_id = container_id
            self.profiles = profiles
            self.created_at = created_at
            self.resolve_count = 0
            self.cache_hit_count = 0

    def __init__(
        self,
        component_factory: ComponentFactory,
        caches: ScopedCaches,
        scopes: ScopeManager,
        observers: Optional[List["ContainerObserver"]] = None,
        container_id: Optional[str] = None,
        profiles: Tuple[str, ...] = (),
    ) -> None:
        self._factory = component_factory
        self._caches = caches
        self.scopes = scopes
        self._locator: Optional[ComponentLocator] = None
        self._observers = list(observers or [])
        self.container_id = container_id or self._generate_container_id()
        import time as _t

        self.context = PicoContainer._Ctx(container_id=self.container_id, profiles=profiles, created_at=_t.time())
        PicoContainer._container_registry[self.container_id] = self

    @staticmethod
    def _generate_container_id() -> str:
        import random as _r
        import time as _t

        return f"c{_t.time_ns():x}{_r.randrange(1 << 16):04x}"

    @classmethod
    def get_current(cls) -> Optional["PicoContainer"]:
        cid = cls._container_id_var.get()
        return cls._container_registry.get(cid) if cid else None

    @classmethod
    def get_current_id(cls) -> Optional[str]:
        return cls._container_id_var.get()

    @classmethod
    def all_containers(cls) -> Dict[str, "PicoContainer"]:
        return dict(cls._container_registry)

    def activate(self) -> contextvars.Token:
        return PicoContainer._container_id_var.set(self.container_id)

    def deactivate(self, token: contextvars.Token) -> None:
        PicoContainer._container_id_var.reset(token)

    @contextmanager
    def as_current(self):
        token = self.activate()
        try:
            yield self
        finally:
            self.deactivate(token)

    def attach_locator(self, locator: ComponentLocator) -> None:
        self._locator = locator

    def _cache_for(self, key: KeyT):
        md = self._locator._metadata.get(key) if self._locator else None
        sc = md.scope if md else SCOPE_SINGLETON
        return self._caches.for_scope(self.scopes, sc)

    def has(self, key: KeyT) -> bool:
        cache = self._cache_for(key)
        return cache.get(key) is not None or self._factory.has(key)

    def _canonical_key(self, key: KeyT) -> KeyT:
        if self._factory.has(key):
            return key

        if isinstance(key, type) and self._locator:
            cands: List[Tuple[bool, Any]] = []
            for k, md in self._locator._metadata.items():
                typ = md.provided_type or md.concrete_class
                if not isinstance(typ, type):
                    continue
                try:
                    if typ is not key and issubclass(typ, key):
                        cands.append((md.primary, k))
                except Exception:
                    continue
            if cands:
                prim = [k for is_p, k in cands if is_p]
                return prim[0] if prim else cands[0][1]

        if isinstance(key, str) and self._locator:
            for k, md in self._locator._metadata.items():
                if md.pico_name == key:
                    return k

        return key

    def _resolve_or_create_internal(self, key: KeyT) -> Tuple[Any, float, bool]:
        key = self._canonical_key(key)
        cache = self._cache_for(key)
        cached = cache.get(key)

        if cached is not None:
            self.context.cache_hit_count += 1
            for o in self._observers:
                o.on_cache_hit(key)
            return cached, 0.0, True

        import time as _tm

        t0 = _tm.perf_counter()

        token_container = self.activate()
        requester = None

        try:
            provider = self._factory.get(key, origin=requester)
            try:
                instance_or_awaitable = provider()
            except ProviderNotFoundError:
                raise
            except Exception as creation_error:
                raise ComponentCreationError(key, creation_error) from creation_error

            took_ms = (_tm.perf_counter() - t0) * 1000
            return instance_or_awaitable, took_ms, False

        finally:
            self.deactivate(token_container)

    def _run_configure_methods(self, instance: Any) -> Any:
        if not _needs_async_configure(instance):
            for m in _iter_configure_methods(instance):
                configure_deps = analyze_callable_dependencies(m)
                args = self._resolve_args(configure_deps)
                res = m(**args)
                if inspect.isawaitable(res):
                    raise AsyncResolutionError(
                        f"Component {type(instance).__name__} returned an awaitable from synchronous "
                        f"@configure method '{m.__name__}'. You must use 'await container.aget()' "
                        "or make the method synchronous."
                    )
            return instance

        async def runner():
            for m in _iter_configure_methods(instance):
                configure_deps = analyze_callable_dependencies(m)
                args = self._resolve_args(configure_deps)
                r = m(**args)
                if inspect.isawaitable(r):
                    await r
            return instance

        return runner()

    @overload
    def get(self, key: type) -> Any: ...
    @overload
    def get(self, key: str) -> Any: ...
    def get(self, key: KeyT) -> Any:
        instance_or_awaitable, took_ms, was_cached = self._resolve_or_create_internal(key)

        if was_cached:
            return instance_or_awaitable

        instance = instance_or_awaitable
        if inspect.isawaitable(instance):
            raise AsyncResolutionError(key)

        md = self._locator._metadata.get(key) if self._locator else None
        scope = md.scope if md else SCOPE_SINGLETON
        if scope != SCOPE_SINGLETON:
            instance_or_awaitable_configured = self._run_configure_methods(instance)
            if inspect.isawaitable(instance_or_awaitable_configured):
                raise AsyncResolutionError(key)
            instance = instance_or_awaitable_configured

        final_instance = self._maybe_wrap_with_aspects(key, instance)
        cache = self._cache_for(key)
        cache.put(key, final_instance)
        self.context.resolve_count += 1
        for o in self._observers:
            o.on_resolve(key, took_ms)

        return final_instance

    async def aget(self, key: KeyT) -> Any:
        instance_or_awaitable, took_ms, was_cached = self._resolve_or_create_internal(key)

        instance = instance_or_awaitable
        if was_cached:
            if isinstance(instance, UnifiedComponentProxy):
                await instance._async_init_if_needed()
            return instance

        if inspect.isawaitable(instance_or_awaitable):
            instance = await instance_or_awaitable

        md = self._locator._metadata.get(key) if self._locator else None
        scope = md.scope if md else SCOPE_SINGLETON
        if scope != SCOPE_SINGLETON:
            instance_or_awaitable_configured = self._run_configure_methods(instance)
            if inspect.isawaitable(instance_or_awaitable_configured):
                instance = await instance_or_awaitable_configured
            else:
                instance = instance_or_awaitable_configured

        final_instance = self._maybe_wrap_with_aspects(key, instance)

        if isinstance(final_instance, UnifiedComponentProxy):
            await final_instance._async_init_if_needed()

        cache = self._cache_for(key)
        cache.put(key, final_instance)
        self.context.resolve_count += 1
        for o in self._observers:
            o.on_resolve(key, took_ms)

        return final_instance

    def _iterate_cleanup_targets(self) -> Iterable[Any]:
        yield from (obj for _, obj in self._caches.all_items())

        if self._locator:
            seen = set()
            for md in self._locator._metadata.values():
                fc = md.factory_class
                if fc and fc not in seen:
                    seen.add(fc)
                    inst = self.get(fc) if self._factory.has(fc) else fc()
                    yield inst

    def _call_cleanup_method(self, method: Callable[..., Any]) -> Any:
        deps_requests = analyze_callable_dependencies(method)
        return method(**self._resolve_args(deps_requests))

    def cleanup_all(self) -> None:
        for obj in self._iterate_cleanup_targets():
            for _, m in inspect.getmembers(obj, predicate=inspect.ismethod):
                meta = getattr(m, PICO_META, {})
                if meta.get("cleanup", False):
                    res = self._call_cleanup_method(m)
                    if inspect.isawaitable(res):
                        LOGGER.warning(f"Async cleanup method {m} called during sync shutdown. Awaitable ignored.")

    async def cleanup_all_async(self) -> None:
        for obj in self._iterate_cleanup_targets():
            for _, m in inspect.getmembers(obj, predicate=inspect.ismethod):
                meta = getattr(m, PICO_META, {})
                if meta.get("cleanup", False):
                    res = self._call_cleanup_method(m)
                    if inspect.isawaitable(res):
                        await res

        try:
            from .event_bus import EventBus

            for _, obj in self._caches.all_items():
                if isinstance(obj, EventBus):
                    await obj.aclose()
        except Exception:
            pass

    def activate_scope(self, name: str, scope_id: Any):
        return self.scopes.activate(name, scope_id)

    def deactivate_scope(self, name: str, token: Optional[contextvars.Token]) -> None:
        self.scopes.deactivate(name, token)

    def info(self, msg: str) -> None:
        LOGGER.info(f"[{self.container_id[:8]}] {msg}")

    @contextmanager
    def scope(self, name: str, scope_id: Any):
        tok = self.activate_scope(name, scope_id)
        try:
            yield self
        finally:
            self.deactivate_scope(name, tok)

    def health_check(self) -> Dict[str, bool]:
        out: Dict[str, bool] = {}
        for k, obj in self._caches.all_items():
            for name, m in inspect.getmembers(obj, predicate=callable):
                if getattr(m, PICO_META, {}).get("health_check", False):
                    try:
                        out[f"{getattr(k, '__name__', k)}.{name}"] = bool(m())
                    except Exception:
                        out[f"{getattr(k, '__name__', k)}.{name}"] = False
        return out

    def stats(self) -> Dict[str, Any]:
        import time as _t

        resolves = self.context.resolve_count
        hits = self.context.cache_hit_count
        total = resolves + hits
        return {
            "container_id": self.container_id,
            "profiles": self.context.profiles,
            "uptime_seconds": _t.time() - self.context.created_at,
            "total_resolves": resolves,
            "cache_hits": hits,
            "cache_hit_rate": (hits / total) if total > 0 else 0.0,
            "registered_components": len(self._locator._metadata) if self._locator else 0,
        }

    def shutdown(self) -> None:
        self.cleanup_all()
        PicoContainer._container_registry.pop(self.container_id, None)

    async def ashutdown(self) -> None:
        await self.cleanup_all_async()
        PicoContainer._container_registry.pop(self.container_id, None)

    def build_resolution_graph(self):
        return _build_resolution_graph(self._locator)

    def export_graph(
        self,
        path: str,
        *,
        include_scopes: bool = True,
        include_qualifiers: bool = False,
        rankdir: str = "LR",
        title: Optional[str] = None,
    ) -> None:
        _export_graph(
            self._locator,
            path,
            include_scopes=include_scopes,
            include_qualifiers=include_qualifiers,
            rankdir=rankdir,
            title=title,
        )
