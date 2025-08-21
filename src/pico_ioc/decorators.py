# pico_ioc/decorators.py

import functools
from typing import Any

COMPONENT_FLAG = "_is_component"
COMPONENT_KEY = "_component_key"
COMPONENT_LAZY = "_component_lazy"
FACTORY_FLAG = "_is_factory_component"
PROVIDES_KEY = "_provides_name"
PROVIDES_LAZY = "_pico_lazy"

def factory_component(cls):
    setattr(cls, FACTORY_FLAG, True)
    return cls

def provides(key: Any, *, lazy: bool = False):
    def dec(func):
        @functools.wraps(func)
        def w(*a, **k): return func(*a, **k)
        setattr(w, PROVIDES_KEY, key)
        setattr(w, PROVIDES_LAZY, bool(lazy))
        return w
    return dec

def component(cls=None, *, name: Any = None, lazy: bool = False):
    def dec(c):
        setattr(c, COMPONENT_FLAG, True)
        setattr(c, COMPONENT_KEY, name if name is not None else c)
        setattr(c, COMPONENT_LAZY, bool(lazy))
        return c
    return dec(cls) if cls else dec

