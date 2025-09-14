# pico_ioc/api.py

from __future__ import annotations

import inspect
import logging
import os
from contextlib import contextmanager
from typing import Callable, Optional, Tuple, Any, Dict, Iterable, Sequence
from .interceptors import MethodInterceptor, ContainerInterceptor
from .container import PicoContainer, Binder
from .policy import apply_policy
from .plugins import PicoPlugin, run_plugin_hook
from .scanner import scan_and_configure
from . import _state

def reset() -> None:
    _state._container = None
    _state._root_name = None

# ---------------- shared helpers ----------------

def _resolve_profiles(profiles: Optional[list[str]]) -> list[str]:
    if profiles is not None:
        return list(profiles)
    env_val = os.getenv("PICO_PROFILE", "")
    return [p.strip() for p in env_val.split(",") if p.strip()]


def _as_provider(val):
    """
    Normalize override values into a (provider_callable, lazy_bool) tuple.
    Accepts:
      - (callable, bool) → explicit (provider, lazy)
      - callable        → (provider, False)
      - any value       → (lambda: value, False)
    """
    if isinstance(val, tuple) and len(val) == 2 and callable(val[0]) and isinstance(val[1], bool):
        return val[0], val[1]
    if callable(val):
        return val, False
    return (lambda v=val: v), False
    
def _apply_overrides(container: PicoContainer, overrides: Dict[Any, Any]) -> None:
    for key, val in overrides.items():
        provider, lazy = _as_provider(val)
        container.bind(key, provider, lazy=lazy)


def _filter_by_tags(container: PicoContainer, include_tags: Optional[set[str]], exclude_tags: Optional[set[str]]) -> None:
    if not include_tags and not exclude_tags:
        return
    def _tag_ok(meta: dict) -> bool:
        tags = set(meta.get("tags", ()))
        if include_tags and not tags.intersection(include_tags):
            return False
        if exclude_tags and tags.intersection(exclude_tags):
            return False
        return True
    container._providers = {k: v for k, v in container._providers.items() if _tag_ok(v)}  # type: ignore[attr-defined]


def _restrict_to_subgraph(container: PicoContainer, roots: Iterable[type], overrides: Optional[Dict[Any, Any]]) -> None:
    allowed = _compute_allowed_subgraph(container, roots)
    keep_keys: set[Any] = set(allowed) | (set(overrides.keys()) if overrides else set())
    container._providers = {k: v for k, v in container._providers.items() if k in keep_keys}  # type: ignore[attr-defined]


def _bootstrap(
    *,
    container: PicoContainer,
    to_scan: Iterable[Any],
    plugins: Tuple[PicoPlugin, ...],
    overrides: Optional[Dict[Any, Any]],
    profiles: Optional[list[str]],
    after_scan_filter: Optional[Callable[[PicoContainer], None]] = None,
) -> list[str]:
    """Common bootstrap: scan → overrides → plugin hooks → policy."""
    binder = Binder(container)
    logging.info("Initializing pico-ioc...")

    with _state.scanning_flag():
        for pkg in to_scan:
            scan_and_configure(pkg, container, exclude=None, plugins=plugins)

    if after_scan_filter:
        after_scan_filter(container)

    if overrides:
        _apply_overrides(container, overrides)

    run_plugin_hook(plugins, "after_bind", container, binder)
    run_plugin_hook(plugins, "before_eager", container, binder)

    requested_profiles = _resolve_profiles(profiles)
    apply_policy(container, profiles=requested_profiles)
    container._active_profiles = tuple(requested_profiles)

    run_plugin_hook(plugins, "after_ready", container, binder)
    logging.info("Container configured and ready.")
    return requested_profiles


def _maybe_reuse_existing(root_name: Optional[str], requested_profiles: list[str], overrides: Optional[Dict[Any, Any]], reuse: bool) -> Optional[PicoContainer]:
    if not reuse:
        return None
    live = _state._container
    if not (live and _state._root_name == root_name):
        return None
    live_profiles = getattr(live, "_active_profiles", None)
    if requested_profiles and live_profiles is not None and live_profiles != tuple(requested_profiles):
        return None
    if overrides:
        _apply_overrides(live, overrides)
    return live


def _build_exclude(
    exclude: Optional[Callable[[str], bool]],
    auto_exclude_caller: bool,
    *,
    root_name: Optional[str] = None,
) -> Optional[Callable[[str], bool]]:
    if not auto_exclude_caller:
        return exclude

    caller = _get_caller_module_name()
    if not caller:
        return exclude

    def _under_root(mod: str) -> bool:
        return bool(root_name) and (mod == root_name or mod.startswith(root_name + "."))

    if exclude is None:
        return lambda mod, _caller=caller: (mod == _caller) and not _under_root(mod)

    prev = exclude
    return lambda mod, _caller=caller, _prev=prev: (((mod == _caller) and not _under_root(mod)) or _prev(mod))


def _get_caller_module_name() -> Optional[str]:
    try:
        f = inspect.currentframe()
        if f and f.f_back and f.f_back and f.f_back.f_back:
            mod = inspect.getmodule(f.f_back.f_back.f_back)
            return getattr(mod, "__name__", None)
    except Exception:
        pass
    return None


# ---------------- public API (thin wrappers) ----------------

def init(
    root_package,
    *,
    profiles: Optional[list[str]] = None,
    exclude: Optional[Callable[[str], bool]] = None,
    auto_exclude_caller: bool = True,
    plugins: Tuple[PicoPlugin, ...] = (),
    reuse: bool = True,
    overrides: Optional[Dict[Any, Any]] = None,
    method_interceptors: Sequence[MethodInterceptor | type] = (),
    interceptors: Sequence[ContainerInterceptor] = (),
) -> PicoContainer:

    root_name = root_package if isinstance(root_package, str) else getattr(root_package, "__name__", None)
    requested_profiles = _resolve_profiles(profiles)

    # Reuse?
    reused = _maybe_reuse_existing(root_name, requested_profiles, overrides, reuse)
    if reused is not None:
        return reused

    combined_exclude = _build_exclude(exclude, auto_exclude_caller, root_name=root_name)

    container = PicoContainer(
        method_interceptors=method_interceptors,
        container_interceptors=interceptors,
    )

    # Scan with module-level exclusion (only for init)
    with _state.scanning_flag():
        scan_and_configure(root_package, container, exclude=combined_exclude, plugins=plugins)

    # Finish bootstrap (overrides, policy, hooks)
    _bootstrap(
        container=container,
        to_scan=(),  # already scanned above to honor combined_exclude
        plugins=plugins,
        overrides=overrides,
        profiles=profiles,
    )

    # Eager instantiate after policy/aliasing
    container.eager_instantiate_all()

    _state._container = container
    _state._root_name = root_name
    return container


def scope(
    *,
    modules: Iterable[Any] = (),
    roots: Iterable[type] = (),
    profiles: Optional[list[str]] = None,
    overrides: Optional[Dict[Any, Any]] = None,
    base: Optional[PicoContainer] = None,
    include_tags: Optional[set[str]] = None,
    exclude_tags: Optional[set[str]] = None,
    strict: bool = True,
    lazy: bool = True,
    method_interceptors: Sequence[MethodInterceptor | type] = (),
    interceptors: Sequence[ContainerInterceptor] = (),
) -> PicoContainer:
    c = _ScopedContainer(
        base=base,
        strict=strict,
        method_interceptors=method_interceptors,
        container_interceptors=interceptors,
    )

    # Bootstrap (scan all modules; tag-filter + subgraph restriction right after)
    def _after_scan_filter(cont: PicoContainer):
        _filter_by_tags(cont, include_tags, exclude_tags)
        if roots:
            _restrict_to_subgraph(cont, roots, overrides)

    _bootstrap(
        container=c,
        to_scan=modules,
        plugins=(),
        overrides=overrides,
        profiles=profiles,
        after_scan_filter=_after_scan_filter,
    )

    # Optional “eager” just for the requested roots if lazy=False
    if not lazy:
        from .proxy import ComponentProxy
        for rk in roots or ():
            try:
                obj = c.get(rk)
                if isinstance(obj, ComponentProxy):
                    _ = obj._get_real_object()
            except NameError:
                if strict:
                    raise
                continue

    logging.info("Scope container ready.")
    return c


# ---------------- subgraph + scoped container ----------------

def _compute_allowed_subgraph(container: PicoContainer, roots: Iterable[type]) -> set:
    from .resolver import _get_hints
    from .container import _is_compatible
    from typing import get_origin, get_args, Annotated

    allowed: set[Any] = set()
    stack = list(roots or ())

    def _add_impls_for_base(base_t):
        for prov_key, meta in container._providers.items():  # type: ignore[attr-defined]
            cls = prov_key if isinstance(prov_key, type) else None
            if cls is None:
                continue
            if _is_compatible(cls, base_t):
                if prov_key not in allowed:
                    allowed.add(prov_key)
                    stack.append(prov_key)

    while stack:
        k = stack.pop()
        if k in allowed:
            continue
        allowed.add(k)

        if isinstance(k, type):
            _add_impls_for_base(k)

        cls = k if isinstance(k, type) else None
        if cls is None or not container.has(k):
            continue

        try:
            sig = inspect.signature(cls.__init__)
        except Exception:
            continue

        hints = _get_hints(cls.__init__, owner_cls=cls)
        for pname, param in sig.parameters.items():
            if pname == "self":
                continue
            ann = hints.get(pname, param.annotation)

            origin = get_origin(ann) or ann
            if origin in (list, tuple):
                inner = (get_args(ann) or (object,))[0]
                if get_origin(inner) is Annotated:
                    inner = (get_args(inner) or (object,))[0]
                if isinstance(inner, type):
                    allowed.add(inner)
                    _add_impls_for_base(inner)
                continue

            if isinstance(ann, type):
                stack.append(ann)
            elif container.has(pname):
                stack.append(pname)

    return allowed


class _ScopedContainer(PicoContainer):
    def __init__(
        self,
        base: Optional[PicoContainer],
        strict: bool,
        *,
        method_interceptors: Sequence[MethodInterceptor | type] = (),
        container_interceptors: Sequence[ContainerInterceptor] = (),
    ):
        super().__init__(
            method_interceptors=method_interceptors,
            container_interceptors=container_interceptors,
        )
        self._base = base
        self._strict = strict

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def has(self, key: Any) -> bool:
        if super().has(key):
            return True
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

