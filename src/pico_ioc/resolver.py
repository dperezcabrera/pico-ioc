# pico_ioc/resolver.py (Python 3.10+)

from __future__ import annotations
import inspect
from typing import Any, Annotated, get_args, get_origin, get_type_hints
from contextvars import ContextVar

_path: ContextVar[list[tuple[str, str]]] = ContextVar("pico_resolve_path", default=[])

def _get_hints(obj, owner_cls=None) -> dict:
    """type hints with include_extras=True and correct globals/locals."""
    mod = inspect.getmodule(obj)
    g = getattr(mod, "__dict__", {})
    l = vars(owner_cls) if owner_cls is not None else None
    return get_type_hints(obj, globalns=g, localns=l, include_extras=True)


def _is_collection_hint(tp) -> bool:
    """True if tp is a list[...] or tuple[...]."""
    origin = get_origin(tp) or tp
    return origin in (list, tuple)


def _base_and_qualifiers_from_hint(tp):
    """
    Extract (base, qualifiers, container_kind) from a collection hint.
    Supports list[T] / tuple[T] and Annotated[T, "qual1", ...].
    """
    origin = get_origin(tp) or tp
    args = get_args(tp) or ()
    container_kind = list if origin is list else tuple

    if not args:
        return (object, (), container_kind)

    inner = args[0]
    if get_origin(inner) is Annotated:
        base, *extras = get_args(inner)
        quals = tuple(a for a in extras if isinstance(a, str))
        return (base, quals, container_kind)

    return (inner, (), container_kind)


class Resolver:
    def __init__(self, container, *, prefer_name_first: bool = True):
        self.c = container
        self._prefer_name_first = bool(prefer_name_first)

    def create_instance(self, cls):
        sig = inspect.signature(cls.__init__)
        hints = _get_hints(cls.__init__, owner_cls=cls)
        kwargs = {}
        for name, param in sig.parameters.items():
            if name == "self" or param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue
            ann = hints.get(name, param.annotation)
            st = _path.get()
            _path.set(st + [(cls.__name__, name)])
            try:
                value = self._resolve_param(name, ann)
            except NameError as e:
                # ⬅️ Important: skip if parameter has a default
                if param.default is not inspect._empty:
                    continue
                chain = " -> ".join(f"{c}.__init__.{p}" for c, p in _path.get())
                raise NameError(f"{e} (required by {chain})") from e
            finally:
                cur = _path.get()
                _path.set(cur[:-1] if cur else [])
            kwargs[name] = value
        return cls(**kwargs)

    def kwargs_for_callable(self, fn, *, owner_cls=None):
        sig = inspect.signature(fn)
        hints = _get_hints(fn, owner_cls=owner_cls)
        kwargs = {}
        owner_name = getattr(owner_cls, "__name__", getattr(fn, "__qualname__", "callable"))
        for name, param in sig.parameters.items():
            if name == "self" or param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue
            ann = hints.get(name, param.annotation)
            st = _path.get()
            _path.set(st + [(owner_name, name)])
            try:
                value = self._resolve_param(name, ann)
            except NameError as e:
                # ⬅️ Important: skip if parameter has a default
                if param.default is not inspect._empty:
                    # do not include in kwargs
                    _path.set(st)  # pop before continue
                    continue
                chain = " -> ".join(f"{c}.__init__.{p}" for c, p in _path.get())
                raise NameError(f"{e} (required by {chain})") from e
            finally:
                cur = _path.get()
                _path.set(cur[:-1] if cur else [])
            kwargs[name] = value
        return kwargs

    def _resolve_param(self, name: str, ann: Any):
        # collections (list/tuple) with optional qualifiers via Annotated
        if _is_collection_hint(ann):
            base, quals, container_kind = _base_and_qualifiers_from_hint(ann)
            items = self.c._resolve_all_for_base(base, qualifiers=quals)
            return list(items) if container_kind is list else tuple(items)

        # precedence: by name > by exact annotation > by MRO > by name again
        if self._prefer_name_first and self.c.has(name):
            return self.c.get(name)

        if ann is not inspect._empty and self.c.has(ann):
            return self.c.get(ann)

        if ann is not inspect._empty and isinstance(ann, type):
            for base in ann.__mro__[1:]:
                if self.c.has(base):
                    return self.c.get(base)

        if self.c.has(name):
            return self.c.get(name)

        missing = ann if ann is not inspect._empty else name
        raise NameError(f"No provider found for key {missing!r}")
