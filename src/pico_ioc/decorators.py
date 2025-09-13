# pico_ioc/decorators.py
from __future__ import annotations
import functools
from typing import Any, Iterable

COMPONENT_FLAG = "_is_component"
COMPONENT_KEY = "_component_key"
COMPONENT_LAZY = "_component_lazy"

FACTORY_FLAG = "_is_factory_component"
PROVIDES_KEY = "_provides_name"
PROVIDES_LAZY = "_pico_lazy"

PLUGIN_FLAG = "_is_pico_plugin"
QUALIFIERS_KEY = "_pico_qualifiers"

COMPONENT_TAGS = "_pico_tags"
PROVIDES_TAGS = "_pico_tags"

def factory_component(cls):
    setattr(cls, FACTORY_FLAG, True)
    return cls


def component(cls=None, *, name: Any = None, lazy: bool = False, tags: Iterable[str] = ()):
    def dec(c):
        setattr(c, COMPONENT_FLAG, True)
        setattr(c, COMPONENT_KEY, name if name is not None else c)
        setattr(c, COMPONENT_LAZY, bool(lazy))
        setattr(c, COMPONENT_TAGS, tuple(tags) if tags else ())
        return c
    return dec(cls) if cls else dec

def provides(key: Any, *, lazy: bool = False, tags: Iterable[str] = ()):
    def dec(fn):
        @functools.wraps(fn)
        def w(*a, **k):
            return fn(*a, **k)
        setattr(w, PROVIDES_KEY, key)
        setattr(w, PROVIDES_LAZY, bool(lazy))
        setattr(w, PROVIDES_TAGS, tuple(tags) if tags else ())
        return w
    return dec


def plugin(cls):
    setattr(cls, PLUGIN_FLAG, True)
    return cls


class Qualifier(str):
    __slots__ = ()  # tiny memory win; immutable like str


def qualifier(*qs: Qualifier):
    def dec(cls):
        current: Iterable[Qualifier] = getattr(cls, QUALIFIERS_KEY, ())
        seen = set(current)
        merged = list(current)
        for q in qs:
            if q not in seen:
                merged.append(q)
                seen.add(q)
        setattr(cls, QUALIFIERS_KEY, tuple(merged))
        return cls
    return dec


__all__ = [
    # decorators
    "component", "factory_component", "provides", "plugin", "qualifier",
    # qualifier type
    "Qualifier",
    # metadata keys (exported for advanced use/testing)
    "COMPONENT_FLAG", "COMPONENT_KEY", "COMPONENT_LAZY",
    "FACTORY_FLAG", "PROVIDES_KEY", "PROVIDES_LAZY",
    "PLUGIN_FLAG", "QUALIFIERS_KEY", "COMPONENT_TAGS", "PROVIDES_TAGS"
]

