# pico_ioc/policy.py
from __future__ import annotations

import inspect
import os
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Tuple, Optional
from .utils import create_alias_provider
from .decorators import (
    CONDITIONAL_META,
    PRIMARY_FLAG,
    ON_MISSING_META,
)

# ---------------- helpers ----------------

def _target_from_provider(provider):
    """
    Best-effort: find the real target behind a provider closure.
    Priority: bound method > plain function > class. Fallback to the provider itself.
    """
    fn = provider
    try:
        cells = getattr(fn, "__closure__", None) or ()
        first_func = None
        first_cls = None
        for cell in cells:
            cc = getattr(cell, "cell_contents", None)
            if inspect.ismethod(cc):
                return cc                    # highest priority: bound method
            if first_func is None and inspect.isfunction(cc):
                first_func = cc              # keep first function seen
            elif first_cls is None and inspect.isclass(cc):
                first_cls = cc               # keep first class seen
        if first_func is not None:
            return first_func
        if first_cls is not None:
            return first_cls
    except Exception:
        pass
    return fn


def _owner_func(obj):
    """
    If obj is a bound method, return the unbound function owned by the class (if resolvable).
    This lets us read decorator flags placed on the original function.
    """
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
    """
    Finds an attribute on a target object, searching the object itself,
    its __func__ (for bound methods), or the owning class's function.
    """
    # 1. Check the object itself
    value = getattr(target, attr_name, None)
    if value is not None:
        return value

    # 2. Check the underlying function for bound methods
    base_func = getattr(target, "__func__", None)
    if base_func is not None:
        value = getattr(base_func, attr_name, None)
        if value is not None:
            return value
    
    # 3. Check the function on the owner class
    owner_func = _owner_func(target)
    if owner_func is not None:
        value = getattr(owner_func, attr_name, None)
        if value is not None:
            return value
            
    return None


def _has_flag(obj, flag_name: str) -> bool:
    """Reads a boolean decorator flag from the target."""
    return bool(_find_attribute_on_target(obj, flag_name))


def _get_meta(obj, meta_name: str) -> Any:
    """Reads metadata (e.g., a dict) from the target."""
    return _find_attribute_on_target(obj, meta_name)


def _on_missing_meta(target):
    """
    Normalize @on_missing metadata.

    IMPORTANT: The decorator stores {"selector": <T>, "priority": <int>}.
    """
    meta = _get_meta(target, ON_MISSING_META)
    if not meta:
        return None
    selector = meta.get("selector")
    prio = int(meta.get("priority", 0))
    return (selector, prio)

def _conditional_active(target, *, profiles: List[str]) -> bool:
    """
    Returns True if the target is active given profiles/env/predicate.
    Activation logic (conjunctive across what's provided):
      - If `profiles` present on target → at least one must match requested profiles.
      - If `require_env` present → all listed env vars must be non-empty.
      - If `predicate` present → must return True; exceptions → inactive (fail-closed).
      - If none provided → active by default.
    """
    meta = _get_meta(target, CONDITIONAL_META)
    if not meta:
        return True

    profs = tuple(meta.get("profiles", ())) or ()
    req_env = tuple(meta.get("require_env", ())) or ()
    pred = meta.get("predicate", None)

    # 1) profiles (if declared)
    if profs:
        if not profiles or not any(p in profs for p in profiles):
            return False

    # 2) require_env (if declared)
    if req_env:
        if not all(os.getenv(k) not in (None, "") for k in req_env):
            return False

    # 3) predicate (if declared)
    if callable(pred):
        try:
            if not bool(pred()):
                return False
        except Exception:
            return False

    # default: active
    return True

# ---------------- public API ----------------

def apply_policy(container, *, profiles: Optional[List[str]] = None) -> None:
    profiles = list(profiles or [])

    _filter_inactive_factory_candidates(container, profiles=profiles)
    _collapse_identical_keys_preferring_primary(container)
    _create_active_component_base_aliases(container, profiles=profiles)
    apply_defaults(container)


def apply_defaults(container) -> None:
    """
    Bind default providers declared via @on_missing when no binding exists for the selector.

    Supports:
      - Class components decorated with @on_missing(Selector, priority=...)
      - Factory @provides(...) where the provided method (or its owner) carries @on_missing
        AND the provider got tagged with _pico_alias_for (the base type key).
    """
    defaults: dict[Any, list[tuple[int, Any]]] = {}

    # (1) Class components with @on_missing
    for prov_key, meta in list(container._providers.items()):  # type: ignore[attr-defined]
        if not isinstance(prov_key, type):
            continue
        target = _target_from_provider(meta.get("factory"))
        om = _on_missing_meta(target)
        if not om:
            continue
        selector, prio = om
        defaults.setdefault(selector, []).append((prio, prov_key))

    # (2) Factory @provides(...) with @on_missing on the provided method/owner
    for prov_key, meta in list(container._providers.items()):  # type: ignore[attr-defined]
        prov = meta.get("factory")
        base = getattr(prov, "_pico_alias_for", None)
        if base is None:
            continue
        target = _target_from_provider(prov)
        om = _on_missing_meta(target)
        if not om:
            continue
        _selector_from_flag, prio = om
        defaults.setdefault(base, []).append((prio, prov_key))

    # Bind highest priority default for each selector if not already bound
    for base, candidates in defaults.items():
        if container.has(base):
            continue
        candidates.sort(key=lambda t: t[0], reverse=True)
        chosen_key = candidates[0][1]

        def _make_delegate(_chosen_key=chosen_key):
            def _factory():
                return container.get(_chosen_key)
            return _factory

        container.bind(base, _make_delegate(), lazy=True)

# ---------------- stages ----------------

def _filter_inactive_factory_candidates(container, *, profiles: List[str]) -> None:
    """
    Remove factory-provided candidates whose target is inactive under the given profiles/env/predicate.
    This trims the candidate set early so later selection/aliasing runs on active options only.
    """
    to_delete = []
    for prov_key, meta in list(container._providers.items()):  # type: ignore[attr-defined]
        prov = meta.get("factory")
        base = getattr(prov, "_pico_alias_for", None)
        if base is None:
            continue
        target = _target_from_provider(prov)
        active = _conditional_active(target, profiles=profiles)
        if not active:
            to_delete.append(prov_key)
    for k in to_delete:
        container._providers.pop(k, None)  # type: ignore[attr-defined]


def _collapse_identical_keys_preferring_primary(container) -> None:
    """
    For factory-provided products of the same base type, collapse to a single alias:
      - If any candidate is marked @primary -> pick the first primary.
      - Else leave multiple to be decided by defaults or later alias logic.
    """
    alias_groups: dict[Any, list[tuple[Any, dict]]] = defaultdict(list)
    for k, m in list(container._providers.items()):  # type: ignore[attr-defined]
        prov = m.get("factory")
        base_key = getattr(prov, "_pico_alias_for", None)
        if base_key is not None:
            alias_groups[base_key].append((k, m))

    for base, entries in alias_groups.items():
        if not entries:
            continue

        if len(entries) == 1:
            keep_key, _ = entries[0]
            if (not container.has(base)) or (base != keep_key):
                factory = create_alias_provider(container, keep_key)
                container.bind(base, factory, lazy=True)
            continue

        primaries: list[tuple[Any, dict]] = []
        for (kk, mm) in entries:
            tgt = _target_from_provider(mm.get("factory"))
            if _has_flag(tgt, PRIMARY_FLAG):
                primaries.append((kk, mm))

        if primaries:
            keep_key, _ = primaries[0]
            if (not container.has(base)) or (base != keep_key):
                factory = create_alias_provider(container, keep_key)
                container.bind(base, factory, lazy=True)
            for (kk, _mm) in entries:
                if kk != keep_key and kk != base:
                    container._providers.pop(kk, None)  # type: ignore[attr-defined]
        else:
            # multiple, no @primary -> leave for defaults
            pass


def _create_active_component_base_aliases(container, *, profiles: List[str]) -> None:
    """
    For class components (not factory-bound), create base->impl aliases among ACTIVE implementations.

    Preference order:
      1) Regular active implementations (non-@on_missing), prefer @primary; else first.
      2) If none, fall back to @on_missing implementations, prefer @primary; else first.
    """
    base_to_impls: Dict[Any, List[Tuple[Any, Dict[str, Any]]]] = defaultdict(list)

    # Collect active implementations
    impls: List[Tuple[type, Dict[str, Any]]] = []
    for key, meta in list(container._providers.items()):  # type: ignore[attr-defined]
        if not isinstance(key, type):
            continue
        tgt = _target_from_provider(meta.get("factory"))
        if _conditional_active(tgt, profiles=profiles):
            impls.append((key, meta))

    # Map each impl to all bases in its MRO (excluding itself and object)
    for impl_key, impl_meta in impls:
        for base in getattr(impl_key, "__mro__", ())[1:]:
            if base is object:
                break
            base_to_impls.setdefault(base, []).append((impl_key, impl_meta))

    # Choose per-base implementation with correct priority
    for base, impl_list in base_to_impls.items():
        if container.has(base) or not impl_list:
            continue

        regular: List[Tuple[Any, Dict[str, Any]]] = []
        fallbacks: List[Tuple[Any, Dict[str, Any]]] = []

        for (impl_key, impl_meta) in impl_list:
            tgt = _target_from_provider(impl_meta.get("factory"))
            if _on_missing_meta(tgt):
                fallbacks.append((impl_key, impl_meta))
            else:
                regular.append((impl_key, impl_meta))

        def pick(cands: List[Tuple[Any, Dict[str, Any]]]) -> Optional[Any]:
            if not cands:
                return None
            primaries = []
            for (ik, im) in cands:
                tgt = _target_from_provider(im.get("factory"))
                if _has_flag(tgt, PRIMARY_FLAG):
                    primaries.append((ik, im))
            chosen_key, _ = primaries[0] if primaries else cands[0]
            return chosen_key

        chosen_key = pick(regular) or pick(fallbacks)
        if chosen_key is None:
            continue

        factory = create_alias_provider(container, chosen_key)
        container.bind(base, factory, lazy=True)

