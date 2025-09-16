# src/pico_ioc/decorators.py
from __future__ import annotations

import functools
from typing import Any, Iterable, Optional, Callable, Tuple, Literal


# ---- marker attributes (read by scanner/policy) ----

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

ON_MISSING_META = "_pico_on_missing"
PRIMARY_FLAG = "_pico_primary"
CONDITIONAL_META = "_pico_conditional"

INTERCEPTOR_META = "__pico_interceptor__"


# ---- core decorators ----

def factory_component(cls):
    """Mark a class as a factory component (its methods can @provides)."""
    setattr(cls, FACTORY_FLAG, True)
    return cls


def component(cls=None, *, name: Any = None, lazy: bool = False, tags: Iterable[str] = ()):
    """Mark a class as a component. Optional: custom key, lazy instantiation, tags."""
    def dec(c):
        setattr(c, COMPONENT_FLAG, True)
        setattr(c, COMPONENT_KEY, name if name is not None else c)
        setattr(c, COMPONENT_LAZY, bool(lazy))
        setattr(c, COMPONENT_TAGS, tuple(tags) if tags else ())
        return c
    return dec(cls) if cls else dec


def provides(key: Any, *, lazy: bool = False, tags: Iterable[str] = ()):
    """Declare a factory method that provides a binding for `key`."""
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
    """Mark a class as a Pico plugin (scanner lifecycle)."""
    setattr(cls, PLUGIN_FLAG, True)
    return cls


# ---- qualifiers ----

class Qualifier(str):
    """String qualifier type used with Annotated[T, 'q1', ...]."""
    __slots__ = ()


def qualifier(*qs: Qualifier):
    """Attach one or more qualifiers to a component class key."""
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


# ---- defaults / selection ----

def on_missing(selector: object, *, priority: int = 0):
    """Declare this target as a default for `selector` when no binding exists."""
    def dec(obj):
        setattr(obj, ON_MISSING_META, {"selector": selector, "priority": int(priority)})
        return obj
    return dec


def primary(obj):
    """Hint this candidate should be preferred among equals."""
    setattr(obj, PRIMARY_FLAG, True)
    return obj


def conditional(
    *,
    profiles: Tuple[str, ...] = (),
    require_env: Tuple[str, ...] = (),
    predicate: Optional[Callable[[], bool]] = None,
):
    """Activate only when profiles/env/predicate conditions pass."""
    def dec(obj):
        setattr(obj, CONDITIONAL_META, {
            "profiles": tuple(profiles),
            "require_env": tuple(require_env),
            "predicate": predicate,
        })
        return obj
    return dec


# ---- interceptors ----

def interceptor(
    _obj=None,
    *,
    kind: Literal["method", "container"] = "method",
    order: int = 0,
    profiles: Tuple[str, ...] = (),
    require_env: Tuple[str, ...] = (),
    predicate: Callable[[], bool] | None = None,
):
    """Declare an interceptor (method or container) with optional activation metadata."""
    def dec(obj):
        setattr(obj, INTERCEPTOR_META, {
            "kind": kind,
            "order": int(order),
            "profiles": tuple(profiles),
            "require_env": tuple(require_env),
            "predicate": predicate,
        })
        return obj
    return dec if _obj is None else dec(_obj)


__all__ = [
    "component", "factory_component", "provides", "plugin",
    "Qualifier", "qualifier",
    "on_missing", "primary", "conditional", "interceptor",
    "COMPONENT_FLAG", "COMPONENT_KEY", "COMPONENT_LAZY",
    "FACTORY_FLAG", "PROVIDES_KEY", "PROVIDES_LAZY",
    "PLUGIN_FLAG", "QUALIFIERS_KEY", "COMPONENT_TAGS", "PROVIDES_TAGS",
    "ON_MISSING_META", "PRIMARY_FLAG", "CONDITIONAL_META",
    "INTERCEPTOR_META",
]

