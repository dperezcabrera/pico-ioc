from __future__ import annotations

import inspect
from typing import Any, Dict, get_origin, get_args, Annotated
import typing as _t

from .proxy import IoCProxy
from .interceptors import MethodInterceptor, ContainerInterceptor, MethodCtx, ResolveCtx, CreateCtx, run_resolve_chain, run_create_chain
from .decorators import QUALIFIERS_KEY
from . import _state

class Binder:
    def __init__(self, container: PicoContainer):
        self._c = container

    def bind(self, key: Any, provider, *, lazy: bool, tags: tuple[str, ...] = ()):
        self._c.bind(key, provider, lazy=lazy, tags=tags)

    def has(self, key: Any) -> bool:
        return self._c.has(key)

    def get(self, key: Any):
        return self._c.get(key)

class PicoContainer:
    def __init__(self, providers: Dict[Any, Dict[str, Any]] | None = None):
        self._providers = providers or {}
        self._singletons: Dict[Any, Any] = {}
        self._method_interceptors: tuple[MethodInterceptor, ...] = ()
        self._container_interceptors: tuple[ContainerInterceptor, ...] = ()
        self._active_profiles: tuple[str, ...] = ()
        self._seen_interceptor_types: set[type] = set()
        self._method_cap: int | None = None

    def add_method_interceptor(self, it: MethodInterceptor) -> None:
        self._method_interceptors = self._method_interceptors + (it,)

    def add_container_interceptor(self, it: ContainerInterceptor) -> None:
        t = type(it)
        if t in self._seen_interceptor_types:
            return
        self._seen_interceptor_types.add(t)
        self._container_interceptors = self._container_interceptors + (it,)

    def set_method_cap(self, n: int | None) -> None:
        self._method_cap = (int(n) if n is not None else None)

    def binder(self) -> Binder:
        return Binder(self)

    def bind(self, key: Any, provider, *, lazy: bool, tags: tuple[str, ...] = ()):
        self._singletons.pop(key, None)
        meta = {"factory": provider, "lazy": bool(lazy)}
        try:
            q = getattr(key, QUALIFIERS_KEY, ())
        except Exception:
            q = ()
        meta["qualifiers"] = tuple(q) if q else ()
        meta["tags"] = tuple(tags) if tags else ()
        self._providers[key] = meta

    def has(self, key: Any) -> bool:
        return key in self._providers

    def _notify_resolve(self, key: Any, ann: Any, quals: tuple[str, ...] | tuple()):
        ctx = ResolveCtx(key=key, qualifiers={q: True for q in quals or ()}, requested_by=None, profiles=self._active_profiles)
        run_resolve_chain(self._container_interceptors, ctx)

    def get(self, key: Any):
        if _state._scanning.get() and not _state._resolving.get():
            raise RuntimeError("re-entrant container access during scan")
        prov = self._providers.get(key)
        if prov is None:
            raise NameError(f"No provider found for key {key!r}")
        if key in self._singletons:
            return self._singletons[key]
        def base_provider():
            return prov["factory"]()
        cls = key if isinstance(key, type) else None
        ctx = CreateCtx(key=key, component=cls, provider=base_provider, profiles=self._active_profiles)
        tok = _state._resolving.set(True)
        try:
            instance = run_create_chain(self._container_interceptors, ctx)
        finally:
            _state._resolving.reset(tok)
        if self._method_interceptors and not isinstance(instance, IoCProxy):
            chain = self._method_interceptors
            cap = getattr(self, "_method_cap", None)
            if isinstance(cap, int) and cap >= 0:
                chain = chain[:cap]
            instance = IoCProxy(instance, chain, container=self, request_key=key)
        self._singletons[key] = instance
        return instance

    def eager_instantiate_all(self):
        for key, prov in list(self._providers.items()):
            if not prov["lazy"]:
                self.get(key)

    def get_all(self, base_type: Any):
        return tuple(self._resolve_all_for_base(base_type, qualifiers=()))

    def get_all_qualified(self, base_type: Any, *qualifiers: str):
        return tuple(self._resolve_all_for_base(base_type, qualifiers=qualifiers))

    def _resolve_all_for_base(self, base_type: Any, qualifiers=()):
        matches = []
        for provider_key, meta in self._providers.items():
            cls = provider_key if isinstance(provider_key, type) else None
            if cls is None:
                continue
            if _requires_collection_of_base(cls, base_type):
                continue
            if _is_compatible(cls, base_type):
                prov_qs = meta.get("qualifiers", ())
                if all(q in prov_qs for q in qualifiers):
                    inst = self.get(provider_key)
                    matches.append(inst)
        return matches

    def get_providers(self) -> Dict[Any, Dict]:
        return self._providers.copy()

def _is_protocol(t) -> bool:
    return getattr(t, "_is_protocol", False) is True

def _is_compatible(cls, base) -> bool:
    try:
        if isinstance(base, type) and issubclass(cls, base):
            return True
    except TypeError:
        pass
    if _is_protocol(base):
        names = set(getattr(base, "__annotations__", {}).keys())
        names.update(n for n in getattr(base, "__dict__", {}).keys() if not n.startswith("_"))
        for n in names:
            if n.startswith("__") and n.endswith("__"):
                continue
            if not hasattr(cls, n):
                return False
        return True
    return False

def _requires_collection_of_base(cls, base) -> bool:
    try:
        sig = inspect.signature(cls.__init__)
    except Exception:
        return False
    try:
        from .resolver import _get_hints
        hints = _get_hints(cls.__init__, owner_cls=cls)
    except Exception:
        hints = {}
    for name, param in sig.parameters.items():
        if name == "self":
            continue
        ann = hints.get(name, param.annotation)
        origin = get_origin(ann) or ann
        if origin in (list, tuple, _t.List, _t.Tuple):
            inner = (get_args(ann) or (object,))[0]
            if get_origin(inner) is Annotated:
                args = get_args(inner)
                if args:
                    inner = args[0]
            if inner is base:
                return True
    return False

