# src/pico_ioc/api.py
from __future__ import annotations

import inspect as _inspect
import importlib
import logging
import os
from types import ModuleType
from typing import Callable, Optional, Tuple, Any, Dict, Iterable, Sequence

from .container import PicoContainer
from .plugins import PicoPlugin
from . import _state
from .builder import PicoContainerBuilder

# The only helpers left are those directly related to the public API signature or fingerprinting
def reset() -> None:
    _state._container = None
    _state._root_name = None
    _state.set_fingerprint(None)

def _combine_excludes(a: Optional[Callable[[str], bool]], b: Optional[Callable[[str], bool]]):
    if not a and not b: return None
    if a and not b: return a
    if b and not a: return b
    return lambda mod, _a=a, _b=b: _a(mod) or _b(mod)

# -------- fingerprint helpers --------
def _callable_id(cb) -> tuple:
    try:
        mod = getattr(cb, "__module__", None)
        qn = getattr(cb, "__qualname__", None)
        code = getattr(cb, "__code__", None)
        fn_line = getattr(code, "co_firstlineno", None) if code else None
        return (mod, qn, fn_line)
    except Exception:
        return (repr(cb),)

def _plugins_id(plugins: Tuple[PicoPlugin, ...]) -> tuple:
    out = [(type(p).__module__, type(p).__qualname__) for p in plugins or ()]
    return tuple(sorted(out))

def _normalize_for_fp(value):
    if isinstance(value, ModuleType):
        return getattr(value, "__name__", repr(value))
    if isinstance(value, (tuple, list)):
        return tuple(_normalize_for_fp(v) for v in value)
    if isinstance(value, set):
        return tuple(sorted(_normalize_for_fp(v) for v in value))
    if callable(value):
        return ("callable",) + _callable_id(value)
    return value

_FP_EXCLUDE_KEYS = set()

def _normalize_overrides_for_fp(overrides: Optional[Dict[Any, Any]]) -> tuple:
    if not overrides:
        return ()
    items = []
    for k, v in overrides.items():
        nk = _normalize_for_fp(k)
        nv = _normalize_for_fp(v)
        items.append((nk, nv))
    return tuple(sorted(items))

def _make_fingerprint_from_signature(locals_in_init: dict) -> tuple:
    sig = _inspect.signature(init)
    entries = []
    for name in sig.parameters.keys():
        if name in _FP_EXCLUDE_KEYS: continue
        if name == "root_package":
            rp = locals_in_init.get("root_package")
            root_name = rp if isinstance(rp, str) else getattr(rp, "__name__", None)
            entries.append(("root", root_name))
            continue
        val = locals_in_init.get(name, None)
        if name == "plugins":
            val = _plugins_id(val or ())
        elif name in ("profiles", "auto_scan"):
            val = tuple(val or ())
        elif name in ("exclude", "auto_scan_exclude"):
            val = _callable_id(val) if val else None
        elif name == "overrides":
            val = _normalize_overrides_for_fp(val)
        else:
            val = _normalize_for_fp(val)
        entries.append((name, val))
    return tuple(sorted(entries))

# -------- container reuse and caller exclusion helpers --------
def _maybe_reuse_existing(fp: tuple, overrides: Optional[Dict[Any, Any]]) -> Optional[PicoContainer]:
    if _state.get_fingerprint() == fp:
        return _state._container
    return None

def _build_exclude(
    exclude: Optional[Callable[[str], bool]], auto_exclude_caller: bool, *, root_name: Optional[str] = None
) -> Optional[Callable[[str], bool]]:
    if not auto_exclude_caller: return exclude
    caller = _get_caller_module_name()
    if not caller: return exclude
    def _under_root(mod: str) -> bool:
        return bool(root_name) and (mod == root_name or mod.startswith(root_name + "."))
    if exclude is None:
        return lambda mod, _caller=caller: (mod == _caller) and not _under_root(mod)
    return lambda mod, _caller=caller, _prev=exclude: (((mod == _caller) and not _under_root(mod)) or _prev(mod))

def _get_caller_module_name() -> Optional[str]:
    try:
        f = _inspect.currentframe()
        # Stack: _get_caller -> _build_exclude -> init -> caller
        if f and f.f_back and f.f_back.f_back and f.f_back.f_back.f_back:
            mod = _inspect.getmodule(f.f_back.f_back.f_back)
            return getattr(mod, "__name__", None)
    except Exception:
        pass
    return None

# ---------------- public API ----------------
def init(
    root_package, *, profiles: Optional[list[str]] = None, exclude: Optional[Callable[[str], bool]] = None,
    auto_exclude_caller: bool = True, plugins: Tuple[PicoPlugin, ...] = (), reuse: bool = True,
    overrides: Optional[Dict[Any, Any]] = None, auto_scan: Sequence[str] = (),
    auto_scan_exclude: Optional[Callable[[str], bool]] = None, strict_autoscan: bool = False,
) -> PicoContainer:
    root_name = root_package if isinstance(root_package, str) else getattr(root_package, "__name__", None)
    fp = _make_fingerprint_from_signature(locals())

    if reuse:
        reused = _maybe_reuse_existing(fp, overrides)
        if reused is not None:
            return reused

    builder = PicoContainerBuilder().with_plugins(plugins).with_profiles(profiles).with_overrides(overrides)

    combined_exclude = _build_exclude(exclude, auto_exclude_caller, root_name=root_name)
    builder.add_scan_package(root_package, exclude=combined_exclude)

    if auto_scan:
        for pkg in auto_scan:
            try:
                mod = importlib.import_module(pkg)
                scan_exclude = _combine_excludes(exclude, auto_scan_exclude)
                builder.add_scan_package(mod, exclude=scan_exclude)
            except ImportError as e:
                msg = f"pico-ioc: auto_scan package not found: {pkg}"
                if strict_autoscan:
                    logging.error(msg)
                    raise e
                logging.warning(msg)

    container = builder.build()

    _state._container = container
    _state._root_name = root_name
    _state.set_fingerprint(fp)
    return container

def scope(
    *, modules: Iterable[Any] = (), roots: Iterable[type] = (), profiles: Optional[list[str]] = None,
    overrides: Optional[Dict[Any, Any]] = None, base: Optional[PicoContainer] = None,
    include_tags: Optional[set[str]] = None, exclude_tags: Optional[set[str]] = None,
    strict: bool = True, lazy: bool = True,
) -> PicoContainer:
    builder = PicoContainerBuilder()

    if base is not None and not strict:
        base_providers = getattr(base, "_providers", {})
        builder._providers.update(base_providers)
        if profiles is None:
            builder.with_profiles(list(getattr(base, "_active_profiles", ())))

    builder.with_profiles(profiles)\
           .with_overrides(overrides)\
           .with_tag_filters(include=include_tags, exclude=exclude_tags)\
           .with_roots(roots)

    for m in modules:
        builder.add_scan_package(m)

    built_container = builder.build()

    scoped_container = _ScopedContainer(base=base, strict=strict, built_container=built_container)

    if not lazy:
        from .proxy import ComponentProxy
        for rk in roots or ():
            try:
                obj = scoped_container.get(rk)
                if isinstance(obj, ComponentProxy):
                    _ = obj._get_real_object()
            except NameError:
                if strict: raise

    logging.info("Scope container ready.")
    return scoped_container

class _ScopedContainer(PicoContainer):
    def __init__(self, built_container: PicoContainer, base: Optional[PicoContainer], strict: bool):
        super().__init__(providers=getattr(built_container, "_providers", {}).copy())
        
        self._active_profiles = getattr(built_container, "_active_profiles", ())
        
        base_method_its = getattr(base, "_method_interceptors", ()) if base else ()
        base_container_its = getattr(base, "_container_interceptors", ()) if base else ()
        
        self._method_interceptors = base_method_its
        self._container_interceptors = base_container_its
        self._seen_interceptor_types = {type(it) for it in (base_method_its + base_container_its)}

        for it in getattr(built_container, "_method_interceptors", ()):
            self.add_method_interceptor(it)
        for it in getattr(built_container, "_container_interceptors", ()):
            self.add_container_interceptor(it)

        self._base = base
        self._strict = strict

        if base:
            self._singletons.update(getattr(base, "_singletons", {}))

    def __enter__(self): return self
    def __exit__(self, exc_type, exc, tb): return False

    def has(self, key: Any) -> bool:
        if super().has(key): return True
        if not self._strict and self._base is not None:
            return self._base.has(key)
        return False

    def get(self, key: Any):
        try:
            return super().get(key)
        except NameError as e:
            if not self._strict and self._base is not None and self._base.has(key):
                return self._base.get(key)
            raise e

def container_fingerprint() -> Optional[tuple]:
    return _state.get_fingerprint()
