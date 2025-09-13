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

# New: selection policy / defaults
ON_MISSING_META = "_pico_on_missing"
PRIMARY_FLAG = "_pico_primary"
CONDITIONAL_META = "_pico_conditional"


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


def on_missing(selector: object, *, priority: int = 0):
    """
    Mark this provider as a default for `selector`, used ONLY if no binding exists for `selector`.

    NOTE: We store metadata as {"selector": selector, "priority": int}.
    The core policy reader (`_on_missing_meta`) MUST read the same keys.
    """
    def dec(obj):
        setattr(obj, ON_MISSING_META, {"selector": selector, "priority": int(priority)})
        return obj
    return dec


def primary(obj):
    """Mark this provider as primary among multiple bindings for the same key."""
    setattr(obj, PRIMARY_FLAG, True)
    return obj


def conditional(*, profiles: tuple[str, ...] = (), require_env: tuple[str, ...] = ()):
    """
    Attach activation conditions. Activated when (profile ∈ profiles) OR (all require_env present).
    Enforced during core policy.
    """
    def dec(obj):
        setattr(obj, CONDITIONAL_META, {"profiles": tuple(profiles), "require_env": tuple(require_env)})
        return obj
    return dec


__all__ = [
    # decorators
    "component", "factory_component", "provides", "plugin", "qualifier",
    # qualifier type
    "Qualifier",
    # metadata keys (exported for advanced use/testing)
    "COMPONENT_FLAG", "COMPONENT_KEY", "COMPONENT_LAZY",
    "FACTORY_FLAG", "PROVIDES_KEY", "PROVIDES_LAZY",
    "PLUGIN_FLAG", "QUALIFIERS_KEY", "COMPONENT_TAGS", "PROVIDES_TAGS",
    # selection/defaults API
    "on_missing", "primary", "conditional",
    "ON_MISSING_META", "PRIMARY_FLAG", "CONDITIONAL_META",
]

