# pico_ioc/api.py
from __future__ import annotations

import inspect
import logging
import os
from typing import Callable, Optional, Tuple, Any, Dict, Iterable, Sequence
from .container import PicoContainer, Binder
from .policy import apply_policy, _conditional_active
from .plugins import PicoPlugin, run_plugin_hook
from .scanner import scan_and_configure
from .resolver import Resolver
from . import _state

def reset() -> None:
    _state._container = None
    _state._root_name = None

# ---------------- helpers ----------------

def _resolve_profiles(profiles: Optional[list[str]]) -> list[str]:
    if profiles is not None:
        return list(profiles)
    env_val = os.getenv("PICO_PROFILE", "")
    return [p.strip() for p in env_val.split(",") if p.strip()]


def _as_provider(val):
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

def _compute_allowed_subgraph(container: PicoContainer, roots: Iterable[type]) -> set:
    from .resolver import _get_hints
    from .container import _is_compatible
    from typing import get_origin, get_args, Annotated
    import inspect as _insp

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
            sig = _insp.signature(cls.__init__)
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

def _restrict_to_subgraph(container: PicoContainer, roots: Iterable[type], overrides: Optional[Dict[Any, Any]]) -> None:
    allowed = _compute_allowed_subgraph(container, roots)
    keep_keys: set[Any] = set(allowed) | (set(overrides.keys()) if overrides else set())
    container._providers = {k: v for k, v in container._providers.items() if k in keep_keys}  # type: ignore[attr-defined]

def _combine_excludes(a: Optional[Callable[[str], bool]], b: Optional[Callable[[str], bool]]):
    if not a and not b: return None
    if a and not b: return a
    if b and not a: return b
    return lambda mod, _a=a, _b=b: _a(mod) or _b(mod)

# ---------------- interceptor bootstrap ----------------

def _activate_and_build_interceptors(
    *,
    container: PicoContainer,
    interceptor_decls: list[tuple[Any, dict]],
    profiles: list[str],
) -> None:
    resolver = Resolver(container)
    active: list[tuple[int, str, str, Any]] = []  # (order, qualname, kind, instance)

    for obj, meta in interceptor_decls:
        if not _conditional_active(obj, profiles=profiles):
            continue
        kind = meta.get("kind", "method")
        order = int(meta.get("order", 0))
        try:
            if isinstance(obj, type):
                inst = resolver.create_instance(obj)
            else:
                kwargs = resolver.kwargs_for_callable(obj, owner_cls=None)
                inst = obj(**kwargs)
        except Exception:
            logging.exception("Failed to construct interceptor %r", obj)
            continue

        qn = getattr(obj, "__qualname__", repr(obj))
        active.append((order, qn, kind, inst))

    active.sort(key=lambda t: (t[0], t[1]))
    for _order, _qn, kind, inst in active:
        if kind == "container":
            container.add_container_interceptor(inst)
        else:
            container.add_method_interceptor(inst)

# ---------------- bootstrap core ----------------

def _bootstrap(
    *,
    container: PicoContainer,
    scan_plan: Iterable[tuple[Any, Optional[Callable[[str], bool]], Tuple[PicoPlugin, ...]]],
    overrides: Optional[Dict[Any, Any]],
    profiles: Optional[list[str]],
    plugins: Tuple[PicoPlugin, ...],
) -> list[str]:
    requested_profiles = _resolve_profiles(profiles)
    interceptor_decls: list[tuple[Any, dict]] = []

    for pkg, exclude, scan_plugins in scan_plan:
        with _state.scanning_flag():
            c, f, decls = scan_and_configure(pkg, container, exclude=exclude, plugins=scan_plugins)
            logging.info("Scanned '%s' (components: %d, factories: %d)", getattr(pkg, "__name__", pkg), c, f)
            interceptor_decls.extend(decls)

    _activate_and_build_interceptors(container=container, interceptor_decls=interceptor_decls, profiles=requested_profiles)

    if overrides:
        _apply_overrides(container, overrides)

    binder = Binder(container)
    run_plugin_hook(plugins, "after_bind", container, binder)
    run_plugin_hook(plugins, "before_eager", container, binder)

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

# ---------------- public API ----------------

def init(
    root_package,
    *,
    profiles: Optional[list[str]] = None,
    exclude: Optional[Callable[[str], bool]] = None,
    auto_exclude_caller: bool = True,
    plugins: Tuple[PicoPlugin, ...] = (),
    reuse: bool = True,
    overrides: Optional[Dict[Any, Any]] = None,
    auto_scan: Sequence[str] = (),
    auto_scan_exclude: Optional[Callable[[str], bool]] = None,
) -> PicoContainer:
    root_name = root_package if isinstance(root_package, str) else getattr(root_package, "__name__", None)
    requested_profiles = _resolve_profiles(profiles)

    reused = _maybe_reuse_existing(root_name, requested_profiles, overrides, reuse)
    if reused is not None:
        return reused

    container = PicoContainer()

    combined_exclude = _build_exclude(exclude, auto_exclude_caller, root_name=root_name)

    scan_plan: list[tuple[Any, Optional[Callable[[str], bool]], Tuple[PicoPlugin, ...]]] = []
    scan_plan.append((root_package, combined_exclude, plugins))
    if auto_scan:
        for pkg in auto_scan:
            scan_plan.append((pkg, _combine_excludes(exclude, auto_scan_exclude), plugins))

    _bootstrap(
        container=container,
        scan_plan=scan_plan,
        overrides=overrides,
        profiles=profiles,
        plugins=plugins,
    )

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
) -> PicoContainer:
    c = _ScopedContainer(base=base, strict=strict)

    def _after_scan_filter(cont: PicoContainer):
        _filter_by_tags(cont, include_tags, exclude_tags)
        if roots:
            _restrict_to_subgraph(cont, roots, overrides)

    scan_plan = [(m, None, ()) for m in modules]
    _bootstrap(
        container=c,
        scan_plan=scan_plan,
        overrides=overrides,
        profiles=profiles,
        plugins=(),
    )

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

    _after_scan_filter(c)
    logging.info("Scope container ready.")
    return c


class _ScopedContainer(PicoContainer):
    def __init__(self, base: Optional[PicoContainer], strict: bool):
        super().__init__()
        self._base = base
        self._strict = strict
        if base is not None:
            for it in getattr(base, "_method_interceptors", ()):
                self.add_method_interceptor(it)
            for it in getattr(base, "_container_interceptors", ()):
                self.add_container_interceptor(it)

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

