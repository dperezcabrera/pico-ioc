from typing import Any, Callable, Dict, Iterable, Optional
import inspect
from dataclasses import MISSING
from .constants import PICO_INFRA, PICO_NAME, PICO_KEY, PICO_META

def _meta_get(obj: Any) -> Dict[str, Any]:
    m = getattr(obj, PICO_META, None)
    if m is None:
        m = {}
        setattr(obj, PICO_META, m)
    return m

def _apply_common_metadata(
    obj: Any,
    *,
    qualifiers: Iterable[str] = (),
    scope: str = "singleton",
    primary: bool = False,
    lazy: bool = False,
    conditional_profiles: Iterable[str] = (),
    conditional_require_env: Iterable[str] = (),
    conditional_predicate: Optional[Callable[[], bool]] = None,
    on_missing_selector: Optional[object] = None,
    on_missing_priority: int = 0,
):
    m = _meta_get(obj)
    m["qualifier"] = tuple(str(q) for q in qualifiers or ())
    m["scope"] = scope
    
    if primary:
        m["primary"] = True
    if lazy:
        m["lazy"] = True
    
    has_conditional = (
        conditional_profiles or 
        conditional_require_env or 
        conditional_predicate is not None
    )
    
    if has_conditional:
        m["conditional"] = {
            "profiles": tuple(p for p in conditional_profiles or ()),
            "require_env": tuple(e for e in conditional_require_env or ()),
            "predicate": conditional_predicate,
        }
    
    if on_missing_selector is not None:
        m["on_missing"] = {
            "selector": on_missing_selector, 
            "priority": int(on_missing_priority)
        }
    return obj

def component(
    cls=None,
    *,
    name: Any = None,
    qualifiers: Iterable[str] = (),
    scope: str = "singleton",
    primary: bool = False,
    lazy: bool = False,
    conditional_profiles: Iterable[str] = (),
    conditional_require_env: Iterable[str] = (),
    conditional_predicate: Optional[Callable[[], bool]] = None,
    on_missing_selector: Optional[object] = None,
    on_missing_priority: int = 0,
):
    def dec(c):
        setattr(c, PICO_INFRA, "component")
        setattr(c, PICO_NAME, name if name is not None else getattr(c, "__name__", str(c)))
        setattr(c, PICO_KEY, name if name is not None else c)
        
        _apply_common_metadata(
            c,
            qualifiers=qualifiers,
            scope=scope,
            primary=primary,
            lazy=lazy,
            conditional_profiles=conditional_profiles,
            conditional_require_env=conditional_require_env,
            conditional_predicate=conditional_predicate,
            on_missing_selector=on_missing_selector,
            on_missing_priority=on_missing_priority,
        )
        return c
    return dec(cls) if cls else dec

def factory(
    cls=None,
    *,
    name: Any = None,
    qualifiers: Iterable[str] = (),
    scope: str = "singleton",
    primary: bool = False,
    lazy: bool = False,
    conditional_profiles: Iterable[str] = (),
    conditional_require_env: Iterable[str] = (),
    conditional_predicate: Optional[Callable[[], bool]] = None,
    on_missing_selector: Optional[object] = None,
    on_missing_priority: int = 0,
):
    def dec(c):
        setattr(c, PICO_INFRA, "factory")
        setattr(c, PICO_NAME, name if name is not None else getattr(c, "__name__", str(c)))
        
        _apply_common_metadata(
            c,
            qualifiers=qualifiers,
            scope=scope,
            primary=primary,
            lazy=lazy,
            conditional_profiles=conditional_profiles,
            conditional_require_env=conditional_require_env,
            conditional_predicate=conditional_predicate,
            on_missing_selector=on_missing_selector,
            on_missing_priority=on_missing_priority,
        )
        return c
    return dec(cls) if cls else dec

def provides(*dargs, **dkwargs):
    def _apply(fn, key_hint, *, name=None, qualifiers=(), scope="singleton", primary=False, lazy=False, conditional_profiles=(), conditional_require_env=(), conditional_predicate=None, on_missing_selector=None, on_missing_priority=0):
        target = fn.__func__ if isinstance(fn, (staticmethod, classmethod)) else fn
        
        inferred_key = key_hint
        if inferred_key is MISSING:
            rt = get_return_type(target)
            if isinstance(rt, type):
                inferred_key = rt
            else:
                inferred_key = getattr(target, "__name__", str(target))
        
        setattr(target, PICO_INFRA, "provides")
        pico_name = name if name is not None else (inferred_key if isinstance(inferred_key, str) else getattr(target, "__name__", str(target)))
        setattr(target, PICO_NAME, pico_name)
        setattr(target, PICO_KEY, inferred_key)
        
        _apply_common_metadata(
            target,
            qualifiers=qualifiers,
            scope=scope,
            primary=primary,
            lazy=lazy,
            conditional_profiles=conditional_profiles,
            conditional_require_env=conditional_require_env,
            conditional_predicate=conditional_predicate,
            on_missing_selector=on_missing_selector,
            on_missing_priority=on_missing_priority,
        )
        return fn

    if dargs and len(dargs) == 1 and inspect.isfunction(dargs[0]) and not dkwargs:
        fn = dargs[0]
        return _apply(fn, MISSING)
    else:
        key = dargs[0] if dargs else MISSING
        def _decorator(fn):
            return _apply(fn, key, **dkwargs)
        return _decorator

class Qualifier(str):
    __slots__ = ()

def configure(fn):
    m = _meta_get(fn)
    m["configure"] = True
    return fn

def cleanup(fn):
    m = _meta_get(fn)
    m["cleanup"] = True
    return fn

def configured(target: Any, *, prefix: str = "", mapping: str = "auto"):
    if mapping not in ("auto", "flat", "tree"):
        raise ValueError("mapping must be one of 'auto', 'flat', or 'tree'")
    def dec(cls):
        setattr(cls, PICO_INFRA, "configured")
        m = _meta_get(cls)
        m["configured"] = {"target": target, "prefix": prefix, "mapping": mapping}
        return cls
    return dec

def get_return_type(fn: Callable[..., Any]) -> Optional[type]:
    try:
        ra = inspect.signature(fn).return_annotation
    except Exception:
        return None
    if ra is inspect._empty:
        return None
    return ra if isinstance(ra, type) else None
