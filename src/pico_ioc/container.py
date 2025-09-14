# pico_ioc/container.py
from __future__ import annotations
import inspect
from typing import Any, Dict, get_origin, get_args, Annotated, Sequence, Optional, Callable, Union, Tuple
import typing as _t
from .proxy import IoCProxy
from .interceptors import MethodInterceptor, ContainerInterceptor

_InterceptorLike = Union[MethodInterceptor, type]

from .decorators import QUALIFIERS_KEY
from . import _state


class Binder:
    def __init__(self, container: "PicoContainer"):
        self._c = container

    def bind(self, key: Any, provider, *, lazy: bool, tags: tuple[str, ...] = ()):
        self._c.bind(key, provider, lazy=lazy, tags=tags)

    def has(self, key: Any) -> bool:
        return self._c.has(key)

    def get(self, key: Any):
        return self._c.get(key)


class PicoContainer:
    def __init__(
        self,
        *,
        method_interceptors: Sequence[_InterceptorLike] = (),
        container_interceptors: Sequence[ContainerInterceptor] = (),
    ):
        self._providers: Dict[Any, Dict[str, Any]] = {}
        self._singletons: Dict[Any, Any] = {}
        self._method_interceptors_raw: tuple[_InterceptorLike, ...] = tuple(method_interceptors)
        self._method_interceptors: tuple[MethodInterceptor, ...] = ()
        self._container_interceptors: tuple[ContainerInterceptor, ...] = tuple(container_interceptors)
        if self._method_interceptors_raw:
            self._build_interceptors()

    def set_container_interceptors(self, interceptors: Sequence[ContainerInterceptor]) -> None:
        self._container_interceptors = tuple(interceptors)
        
    def set_method_interceptors(self, interceptors: Sequence[_InterceptorLike]) -> None:
        self._method_interceptors_raw = tuple(interceptors)
        self._build_interceptors()

    def _build_interceptors(self) -> None:
        built: list[MethodInterceptor] = []
        for it in self._method_interceptors_raw:
            if isinstance(it, type):
                try:
                    built.append(it(self))
                except TypeError:
                    built.append(it())      # fallback to no-arg ctor
            else:
                built.append(it)            # already callable
        self._method_interceptors = tuple(built)


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

    def get(self, key: Any):
        if _state._scanning.get() and not _state._resolving.get():
            raise RuntimeError("re-entrant container access during scan")
        prov = self._providers.get(key)
        if prov is None:
            raise NameError(f"No provider found for key {key!r}")
        if key in self._singletons:
            return self._singletons[key]

        # on_before_create
        for ci in self._container_interceptors:
            try: ci.on_before_create(key)
            except Exception: pass

        tok = _state._resolving.set(True)
        try:
            try:
                instance = prov["factory"]()
            except BaseException as exc:
                for ci in self._container_interceptors:
                    try: ci.on_exception(key, exc)
                    except Exception: pass
                raise
        finally:
            _state._resolving.reset(tok)

        if self._method_interceptors and not isinstance(instance, IoCProxy):
            instance = IoCProxy(instance, self._method_interceptors)

        # on_after_create (permite reemplazar)
        for ci in self._container_interceptors:
            try:
                maybe = ci.on_after_create(key, instance)
                if maybe is not None:
                    instance = maybe
            except Exception:
                pass

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
    """
    Return True if `cls.__init__` has any parameter annotated as a collection
    (list/tuple, including Annotated variants) of `base`. Avoids recursion.
    """
    try:
        sig = inspect.signature(cls.__init__)
    except Exception:
        return False

    try:
        from .resolver import _get_hints  # deferred import
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

