# src/pico_ioc/container.py
import inspect
import contextvars
from typing import Any, Dict, List, Optional, Tuple, overload, Union
from contextlib import contextmanager
from .constants import LOGGER, PICO_META
from .exceptions import CircularDependencyError, ComponentCreationError, ProviderNotFoundError, AsyncResolutionError
from .factory import ComponentFactory
from .locator import ComponentLocator
from .scope import ScopedCaches, ScopeManager
from .aop import UnifiedComponentProxy, ContainerObserver

KeyT = Union[str, type]
_resolve_chain: contextvars.ContextVar[Tuple[KeyT, ...]] = contextvars.ContextVar("pico_resolve_chain", default=())

class _TracerFrame:
    __slots__ = ("parent_key", "via")
    def __init__(self, parent_key: KeyT, via: str):
        self.parent_key = parent_key
        self.via = via

class ResolutionTracer:
    def __init__(self, container: "PicoContainer") -> None:
        self._container = container
        self._stack_var: contextvars.ContextVar[List[_TracerFrame]] = contextvars.ContextVar("pico_tracer_stack", default=[])
        self._edges: Dict[Tuple[KeyT, KeyT], Tuple[str, str]] = {}

    def enter(self, parent_key: KeyT, via: str) -> contextvars.Token:
        stack = list(self._stack_var.get())
        stack.append(_TracerFrame(parent_key, via))
        return self._stack_var.set(stack)

    def leave(self, token: contextvars.Token) -> None:
        self._stack_var.reset(token)

    def override_via(self, new_via: str) -> Optional[str]:
        stack = self._stack_var.get()
        if not stack:
            return None
        prev = stack[-1].via
        stack[-1].via = new_via
        return prev

    def restore_via(self, previous: Optional[str]) -> None:
        if previous is None:
            return
        stack = self._stack_var.get()
        if not stack:
            return
        stack[-1].via = previous

    def note_param(self, child_key: KeyT, param_name: str) -> None:
        stack = self._stack_var.get()
        if not stack:
            return
        parent = stack[-1].parent_key
        via = stack[-1].via
        self._edges[(parent, child_key)] = (via, param_name)

    def describe_cycle(self, chain: Tuple[KeyT, ...], current: KeyT, locator: Optional[ComponentLocator]) -> str:
        def name_of(k: KeyT) -> str:
            return getattr(k, "__name__", str(k))
        def scope_of(k: KeyT) -> str:
            if not locator:
                return "singleton"
            md = locator._metadata.get(k)
            return md.scope if md else "singleton"
        lines: List[str] = []
        lines.append("Circular dependency detected.")
        lines.append("")
        lines.append("Resolution chain:")
        full = tuple(chain) + (current,)
        for idx, k in enumerate(full, 1):
            mark = "  ❌" if idx == len(full) else ""
            lines.append(f"  {idx}. {name_of(k)} [scope={scope_of(k)}]{mark}")
            if idx < len(full):
                parent = k
                child = full[idx]
                via, param = self._edges.get((parent, child), ("provider", "?"))
                lines.append(f"     └─ via {via} param '{param}' → {name_of(child)}")
        lines.append("")
        lines.append("Hint: break the cycle with a @configure setter or use a factory/provider.")
        return "\n".join(lines)

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
        self._tracer = ResolutionTracer(self)

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
        chain = list(_resolve_chain.get())

        for k_in_chain in chain:
            if k_in_chain == key:
                details = self._tracer.describe_cycle(tuple(chain), key, self._locator)
                raise ComponentCreationError(key, CircularDependencyError(chain, key, details=details))

        token_chain = _resolve_chain.set(tuple(chain + [key]))
        token_container = self.activate()
        token_tracer = self._tracer.enter(key, via="provider")

        requester = chain[-1] if chain else None
        instance_or_awaitable = None

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
            self._tracer.leave(token_tracer)
            _resolve_chain.reset(token_chain)
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

    def _resolve_type_key(self, key: type):
        if not self._locator:
            return None
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
        if not cands:
            return None
        prim = [k for is_p, k in cands if is_p]
        return prim[0] if prim else cands[0][1]

    def _maybe_wrap_with_aspects(self, key, instance: Any) -> Any:
        if isinstance(instance, UnifiedComponentProxy):
            return instance
        cls = type(instance)
        for _, fn in inspect.getmembers(cls, predicate=lambda m: inspect.isfunction(m) or inspect.ismethod(m) or inspect.iscoroutinefunction(m)):
            if getattr(fn, "_pico_interceptors_", None):
                return UnifiedComponentProxy(container=self, target=instance)
        return instance

    def cleanup_all(self) -> None:
        for _, obj in self._caches.all_items():
            for _, m in inspect.getmembers(obj, predicate=inspect.ismethod):
                meta = getattr(m, PICO_META, {})
                if meta.get("cleanup", False):
                    from .api import _resolve_args
                    kwargs = _resolve_args(m, self)
                    m(**kwargs)
        if self._locator:
            seen = set()
            for md in self._locator._metadata.values():
                fc = md.factory_class
                if fc and fc not in seen:
                    seen.add(fc)
                    inst = self.get(fc) if self._factory.has(fc) else fc()
                    for _, m in inspect.getmembers(inst, predicate=inspect.ismethod):
                        meta = getattr(m, PICO_META, {})
                        if meta.get("cleanup", False):
                            from .api import _resolve_args
                            kwargs = _resolve_args(m, self)
                            m(**kwargs)

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

    async def cleanup_all_async(self) -> None:
        for _, obj in self._caches.all_items():
            for _, m in inspect.getmembers(obj, predicate=inspect.ismethod):
                meta = getattr(m, PICO_META, {})
                if meta.get("cleanup", False):
                    from .api import _resolve_args
                    res = m(**_resolve_args(m, self))
                    import inspect as _i
                    if _i.isawaitable(res):
                        await res
        if self._locator:
            seen = set()
            for md in self._locator._metadata.values():
                fc = md.factory_class
                if fc and fc not in seen:
                    seen.add(fc)
                    inst = self.get(fc) if self._factory.has(fc) else fc()
                    for _, m in inspect.getmembers(inst, predicate=inspect.ismethod):
                        meta = getattr(m, PICO_META, {})
                        if meta.get("cleanup", False):
                            from .api import _resolve_args
                            res = m(**_resolve_args(m, self))
                            import inspect as _i
                            if _i.isawaitable(res):
                                await res
        try:
            from .event_bus import EventBus
            for _, obj in self._caches.all_items():
                if isinstance(obj, EventBus):
                    await obj.aclose()
        except Exception:
            pass

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

        from .api import _build_resolution_graph

        md_by_key = self._locator._metadata
        graph = _build_resolution_graph(self)

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

