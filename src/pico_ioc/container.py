# pico_ioc/container.py
from __future__ import annotations
import inspect
from typing import Any, Dict, get_origin, get_args, Annotated
import typing as _t 

from .decorators import QUALIFIERS_KEY
from . import _state  # re-entrancy guard


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
    def __init__(self):
        self._providers: Dict[Any, Dict[str, Any]] = {}
        self._singletons: Dict[Any, Any] = {}

    def bind(self, key: Any, provider, *, lazy: bool, tags: tuple[str, ...] = ()):
        self._singletons.pop(key, None)
        meta = {"factory": provider, "lazy": bool(lazy)}
        # qualifiers already present:
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
        # block only when scanning and NOT currently resolving a dependency
        if _state._scanning.get() and not _state._resolving.get():
            raise RuntimeError("re-entrant container access during scan")

        prov = self._providers.get(key)
        if prov is None:
            raise NameError(f"No provider found for key {key!r}")

        if key in self._singletons:
            return self._singletons[key]

        # mark resolving around factory execution
        tok = _state._resolving.set(True)
        try:
            instance = prov["factory"]()
        finally:
            _state._resolving.reset(tok)

        # memoize always (both lazy and non-lazy after first get)
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

            # Avoid self-inclusion loops: if the class itself requires a collection
            # of `base_type` in its __init__, don't treat it as an implementation
            # of `base_type` when building that collection.
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
        # simple structural check: ensure methods/attrs declared on the Protocol exist on the class
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
    (list/tuple, including Annotated variants) of `base`. This prevents treating
    `cls` as an implementation of `base` while building that collection,
    avoiding recursion.
    """
    try:
        sig = inspect.signature(cls.__init__)
    except Exception:
        return False

    try:
        from .resolver import _get_hints  # type: ignore
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
            # Unwrap Annotated[T, ...] si aparece
            if get_origin(inner) is Annotated:
                args = get_args(inner)
                if args:
                    inner = args[0]
            if inner is base:
                return True
    return False


