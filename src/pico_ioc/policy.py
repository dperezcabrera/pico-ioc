# src/pico_ioc/policy.py
from __future__ import annotations

import inspect
import os
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from .utils import create_alias_provider
from .decorators import CONDITIONAL_META, PRIMARY_FLAG, ON_MISSING_META
from . import _state


# ------------------- helpers -------------------

def _target_from_provider(provider):
    """Try to resolve the 'real' target behind a provider closure (class, function or bound method)."""
    fn = provider
    try:
        cells = getattr(fn, "__closure__", None) or ()
        first_func, first_cls = None, None
        for cell in cells:
            cc = getattr(cell, "cell_contents", None)
            if inspect.ismethod(cc):
                return cc
            if first_func is None and inspect.isfunction(cc):
                first_func = cc
            elif first_cls is None and inspect.isclass(cc):
                first_cls = cc
        return first_func or first_cls or fn
    except Exception:
        return fn


def _owner_func(obj):
    """If obj is a bound method, return the unbound function on its owner class."""
    try:
        if inspect.ismethod(obj) and getattr(obj, "__self__", None) is not None:
            owner = obj.__self__.__class__
            name = getattr(obj, "__name__", None)
            if name and hasattr(owner, name):
                cand = getattr(owner, name)
                if inspect.isfunction(cand):
                    return cand
    except Exception:
        pass
    return None


def _find_attribute_on_target(target: Any, attr_name: str) -> Any:
    """Look for metadata on object, its underlying function, or owner class method."""
    val = getattr(target, attr_name, None)
    if val is not None:
        return val
    base_func = getattr(target, "__func__", None)
    if base_func:
        val = getattr(base_func, attr_name, None)
        if val is not None:
            return val
    of = _owner_func(target)
    if of:
        val = getattr(of, attr_name, None)
        if val is not None:
            return val
    return None


def _has_flag(obj, flag_name: str) -> bool:
    return bool(_find_attribute_on_target(obj, flag_name))


def _get_meta(obj, meta_name: str) -> Any:
    return _find_attribute_on_target(obj, meta_name)


def _on_missing_meta(target):
    """Normalize @on_missing metadata."""
    meta = _get_meta(target, ON_MISSING_META)
    if not meta:
        return None
    return (meta.get("selector"), int(meta.get("priority", 0)))


def _conditional_active(target, *, profiles: List[str]) -> bool:
    """Check if target is active given profiles/env/predicate."""
    meta = _get_meta(target, CONDITIONAL_META)
    if not meta:
        return True

    profs = tuple(meta.get("profiles", ()))
    req_env = tuple(meta.get("require_env", ()))
    pred = meta.get("predicate")

    if profs and (not profiles or not any(p in profs for p in profiles)):
        return False
    if req_env and not all(os.getenv(k) not in (None, "") for k in req_env):
        return False
    if callable(pred):
        try:
            if not bool(pred()):
                return False
        except Exception:
            return False
    return True


# ------------------- public API -------------------

def apply_policy(container, *, profiles: Optional[List[str]] = None) -> None:
    """Run all policy stages on the given container."""
    profiles = list(profiles or [])

    _filter_inactive_factory_candidates(container, profiles=profiles)
    _collapse_identical_keys_preferring_primary(container)
    _create_active_component_base_aliases(container, profiles=profiles)
    apply_defaults(container)


def apply_defaults(container) -> None:
    """Bind defaults declared with @on_missing if no binding exists for selector."""
    defaults: dict[Any, list[tuple[int, Any]]] = {}

    # class components
    for prov_key, meta in list(container._providers.items()):  # type: ignore
        if not isinstance(prov_key, type):
            continue
        target = _target_from_provider(meta.get("factory"))
        om = _on_missing_meta(target)
        if om:
            selector, prio = om
            defaults.setdefault(selector, []).append((prio, prov_key))

    # factory provides
    for prov_key, meta in list(container._providers.items()):  # type: ignore
        prov = meta.get("factory")
        base = getattr(prov, "_pico_alias_for", None)
        if base is None:
            continue
        target = _target_from_provider(prov)
        om = _on_missing_meta(target)
        if om:
            _sel, prio = om
            defaults.setdefault(base, []).append((prio, prov_key))

    # bind highest priority candidate
    for base, cands in defaults.items():
        if container.has(base):
            continue
        cands.sort(key=lambda t: t[0], reverse=True)
        chosen_key = cands[0][1]

        def _delegate(_k=chosen_key):
            def _f():
                return container.get(_k)
            return _f

        container.bind(base, _delegate(), lazy=True)


# ------------------- stages -------------------

def _filter_inactive_factory_candidates(container, *, profiles: List[str]) -> None:
    """Remove factories inactive under profiles/env/predicate."""
    to_delete = []
    for prov_key, meta in list(container._providers.items()):  # type: ignore
        prov = meta.get("factory")
        base = getattr(prov, "_pico_alias_for", None)
        if base is None:
            continue
        target = _target_from_provider(prov)
        if not _conditional_active(target, profiles=profiles):
            to_delete.append(prov_key)
    for k in to_delete:
        container._providers.pop(k, None)  # type: ignore


def _collapse_identical_keys_preferring_primary(container) -> None:
    """For multiple factory candidates of same base, keep one (prefer @primary)."""
    groups: dict[Any, list[tuple[Any, dict]]] = defaultdict(list)
    for k, m in list(container._providers.items()):  # type: ignore
        prov = m.get("factory")
        base = getattr(prov, "_pico_alias_for", None)
        if base is not None:
            groups[base].append((k, m))

    for base, entries in groups.items():
        if not entries:
            continue
        if len(entries) == 1:
            keep, _ = entries[0]
            if (not container.has(base)) or (base != keep):
                factory = create_alias_provider(container, keep)
                container.bind(base, factory, lazy=True)
            continue

        prims = [(kk, mm) for (kk, mm) in entries if _has_flag(_target_from_provider(mm["factory"]), PRIMARY_FLAG)]
        if prims:
            keep, _ = prims[0]
            if (not container.has(base)) or (base != keep):
                factory = create_alias_provider(container, keep)
                container.bind(base, factory, lazy=True)
            for kk, _mm in entries:
                if kk != keep and kk != base:
                    container._providers.pop(kk, None)  # type: ignore


def _create_active_component_base_aliases(container, *, profiles: List[str]) -> None:
    """For active class components, create base->impl aliases (prefer @primary)."""
    impls: List[Tuple[type, dict]] = []
    for key, meta in list(container._providers.items()):  # type: ignore
        if not isinstance(key, type):
            continue
        tgt = _target_from_provider(meta.get("factory"))
        if _conditional_active(tgt, profiles=profiles):
            impls.append((key, meta))

    base_to_impls: Dict[Any, List[Tuple[Any, dict]]] = defaultdict(list)
    for impl_key, impl_meta in impls:
        for base in getattr(impl_key, "__mro__", ())[1:]:
            if base is object:
                break
            base_to_impls[base].append((impl_key, impl_meta))

    for base, impl_list in base_to_impls.items():
        if container.has(base) or not impl_list:
            continue

        regular, fallbacks = [], []
        for ik, im in impl_list:
            tgt = _target_from_provider(im["factory"])
            (fallbacks if _on_missing_meta(tgt) else regular).append((ik, im))

        def pick(cands: List[Tuple[Any, dict]]) -> Optional[Any]:
            if not cands:
                return None
            prims = [(ik, im) for ik, im in cands if _has_flag(_target_from_provider(im["factory"]), PRIMARY_FLAG)]
            return prims[0][0] if prims else cands[0][0]

        chosen = pick(regular) or pick(fallbacks)
        if not chosen:
            continue

        factory = create_alias_provider(container, chosen)
        container.bind(base, factory, lazy=True)

