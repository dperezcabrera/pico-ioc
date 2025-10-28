import inspect
import contextvars
import functools
from typing import Any, Dict, List, Optional, Tuple, overload, Union, Callable, Iterable, Set, get_args, get_origin, Annotated, Protocol, Mapping
from contextlib import contextmanager
from .constants import LOGGER, PICO_META
from .exceptions import ComponentCreationError, ProviderNotFoundError, AsyncResolutionError
from .factory import ComponentFactory, ProviderMetadata
from .locator import ComponentLocator
from .scope import ScopedCaches, ScopeManager
from .aop import UnifiedComponentProxy, ContainerObserver
from .analysis import analyze_callable_dependencies, DependencyRequest

KeyT = Union[str, type]

def _normalize_callable(obj):
    return getattr(obj, '__func__', obj)

def _get_signature_safe(callable_obj):
    try:
        return inspect.signature(callable_obj)
    except (ValueError, TypeError):
        wrapped = getattr(callable_obj, '__wrapped__', None)
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

def _build_resolution_graph(loc) -> Dict[KeyT, Tuple[KeyT, ...]]:
    if not loc:
        return {}
        
    def _map_dep_to_bound_key(dep_key: KeyT) -> KeyT:
        if dep_key in loc._metadata:
            return dep_key
        
        if isinstance(dep_key, str):
            mapped = loc.find_key_by_name(dep_key)
            if mapped is not None:
                return mapped

        if isinstance(dep_key, type):
            for k, md in loc._metadata.items():
                typ = md.provided_type or md.concrete_class
                if isinstance(typ, type):
                    try:
                        if issubclass(typ, dep_key):
                            return k
                    except Exception:
                        continue
        return dep_key

    graph: Dict[KeyT, Tuple[KeyT, ...]] = {}
    for key, md in list(loc._metadata.items()):
        deps: List[KeyT] = []
        for d in loc.dependency_keys_for_static(md):
            mapped = _map_dep_to_bound_key(d)
            deps.append(mapped)
        graph[key] = tuple(deps)
    return graph

class PicoContainer:
    _container_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("pico_container_id", default=None)
    _container_registry: Dict[str, "PicoContainer"] = {}

    class _Ctx:
        def __init__(self, container_id: str, profiles: Tuple[str, ...], created_at: float) -> None:
            self.container_id = container_id
            self.profiles = profiles
            self.created_at = created_at
            self.resolve_count = 0
            self.cache_hit_count = 0

    def __init__(self, component_factory: ComponentFactory, caches: ScopedCaches, scopes: ScopeManager, observers: Optional[List["ContainerObserver"]] = None, container_id: Optional[str] = None, profiles: Tuple[str, ...] = ()) -> None:
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
        import time as _t, random as _r
        return f"c{_t.time_ns():x}{_r.randrange(1<<16):04x}"

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
        sc = (md.scope if md else "singleton")
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
            for o in self._observers: o.on_cache_hit(key)
            return cached, 0.0, True

        import time as _tm
        t0 = _tm.perf_counter()

        token_container = self.activate()
        requester = None

        try:
            provider = self._factory.get(key, origin=requester)
            try:
                instance_or_awaitable = provider()
            except ProviderNotFoundError as e:
                raise
            except Exception as creation_error:
                raise ComponentCreationError(key, creation_error) from creation_error

            took_ms = (_tm.perf_counter() - t0) * 1000
            return instance_or_awaitable, took_ms, False

        finally:
            self.deactivate(token_container)
            
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
            key_name = getattr(key, '__name__', str(key))
            raise AsyncResolutionError(key)

        final_instance = self._maybe_wrap_with_aspects(key, instance)
        cache = self._cache_for(key)
        cache.put(key, final_instance)
        self.context.resolve_count += 1
        for o in self._observers: o.on_resolve(key, took_ms)

        return final_instance

    async def aget(self, key: KeyT) -> Any:
        instance_or_awaitable, took_ms, was_cached = self._resolve_or_create_internal(key)

        if was_cached:
            return instance_or_awaitable

        instance = instance_or_awaitable
        if inspect.isawaitable(instance_or_awaitable):
            instance = await instance_or_awaitable

        final_instance = self._maybe_wrap_with_aspects(key, instance)
        cache = self._cache_for(key)
        cache.put(key, final_instance)
        self.context.resolve_count += 1
        for o in self._observers: o.on_resolve(key, took_ms)

        return final_instance

    def _maybe_wrap_with_aspects(self, key, instance: Any) -> Any:
        if isinstance(instance, UnifiedComponentProxy):
            return instance
        cls = type(instance)
        for _, fn in inspect.getmembers(cls, predicate=lambda m: inspect.isfunction(m) or inspect.ismethod(m) or inspect.iscoroutinefunction(m)):
            if getattr(fn, "_pico_interceptors_", None):
                return UnifiedComponentProxy(container=self, target=instance)
        return instance

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
                        out[f"{getattr(k,'__name__',k)}.{name}"] = bool(m())
                    except Exception:
                        out[f"{getattr(k,'__name__',k)}.{name}"] = False
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

    def build_resolution_graph(self) -> None:
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

        if not self._locator:
            raise RuntimeError("No locator attached; cannot export dependency graph.")

        md_by_key = self._locator._metadata
        graph = _build_resolution_graph(self._locator)

        lines: List[str] = []
        lines.append("digraph Pico {")
        lines.append(f'  rankdir="{rankdir}";')
        lines.append("  node [shape=box, fontsize=10];")
        if title:
            lines.append(f'  labelloc="t";')
            lines.append(f'  label="{title}";')

        def _node_id(k: KeyT) -> str:
            return f'n_{abs(hash(k))}'

        def _node_label(k: KeyT) -> str:
            name = getattr(k, "__name__", str(k))
            md = md_by_key.get(k)
            parts = [name]
            if md is not None and include_scopes:
                parts.append(f"[scope={md.scope}]")
            if md is not None and include_qualifiers and md.qualifiers:
                q = ",".join(sorted(md.qualifiers))
                parts.append(f"\\n⟨{q}⟩")
            return "\\n".join(parts)

        for key in md_by_key.keys():
            nid = _node_id(key)
            label = _node_label(key)
            lines.append(f'  {nid} [label="{label}"];')

        for parent, deps in graph.items():
            pid = _node_id(parent)
            for child in deps:
                cid = _node_id(child)
                lines.append(f"  {pid} -> {cid};")

        lines.append("}")

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

            
    def _resolve_args(self, dependencies: Tuple[DependencyRequest, ...]) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {}
        if not dependencies:
            return kwargs
            
        for dep in dependencies:
            if dep.is_list:
                keys: Tuple[KeyT, ...] = ()
                if self._locator is not None and isinstance(dep.key, type):
                    keys = tuple(self._locator.collect_by_type(dep.key, dep.qualifier))
                kwargs[dep.parameter_name] = [self.get(k) for k in keys]
                continue

            primary_key = dep.key
            if isinstance(primary_key, str) and self._locator is not None:
                mapped = self._locator.find_key_by_name(primary_key)
                primary_key = mapped if mapped is not None else primary_key
            
            try:
                kwargs[dep.parameter_name] = self.get(primary_key)
            except Exception as first_error:
                if primary_key != dep.parameter_name:
                    try:
                        kwargs[dep.parameter_name] = self.get(dep.parameter_name)
                    except Exception:
                        raise first_error from None
                else:
                    raise first_error from None
        return kwargs


    def build_class(self, cls: type, locator: ComponentLocator, dependencies: Tuple[DependencyRequest, ...]) -> Any:
        init = cls.__init__
        if init is object.__init__:
            inst = cls()
        else:
            deps = self._resolve_args(dependencies)
            inst = cls(**deps)
        
        ainit = getattr(inst, "__ainit__", None)
        has_async = (callable(ainit) and inspect.iscoroutinefunction(ainit)) or _needs_async_configure(inst)
        
        if has_async:
            async def runner():
                if callable(ainit):
                    kwargs = {}
                    try:
                        ainit_deps = analyze_callable_dependencies(ainit)
                        kwargs = self._resolve_args(ainit_deps)
                    except Exception:
                        kwargs = {}
                    res = ainit(**kwargs)
                    if inspect.isawaitable(res):
                        await res
                for m in _iter_configure_methods(inst):
                    configure_deps = analyze_callable_dependencies(m)
                    args = self._resolve_args(configure_deps)
                    r = m(**args)
                    if inspect.isawaitable(r):
                        await r
                return inst
            return runner()
            
        for m in _iter_configure_methods(inst):
            configure_deps = analyze_callable_dependencies(m)
            args = self._resolve_args(configure_deps)
            m(**args)
        return inst

    def build_method(self, fn: Callable[..., Any], locator: ComponentLocator, dependencies: Tuple[DependencyRequest, ...]) -> Any:
        deps = self._resolve_args(dependencies)
        obj = fn(**deps)
        
        has_async = _needs_async_configure(obj)
        if has_async:
            async def runner():
                for m in _iter_configure_methods(obj):
                    configure_deps = analyze_callable_dependencies(m)
                    args = self._resolve_args(configure_deps)
                    r = m(**args)
                    if inspect.isawaitable(r):
                        await r
                return obj
            return runner()
            
        for m in _iter_configure_methods(obj):
            configure_deps = analyze_callable_dependencies(m)
            args = self._resolve_args(configure_deps)
            m(**args)
        return obj
