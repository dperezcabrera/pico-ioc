# pico_ioc/api.py
from __future__ import annotations

import inspect
import logging
import os
from contextlib import contextmanager
from typing import Callable, Optional, Tuple, Any, Dict, Iterable

from .container import PicoContainer, Binder
from .core_policy import apply_core_policy
from .plugins import PicoPlugin
from .scanner import scan_and_configure
from . import _state


def reset() -> None:
    _state._container = None
    _state._root_name = None


def init(
    root_package,
    *,
    profiles: Optional[list[str]] = None,
    exclude: Optional[Callable[[str], bool]] = None,
    auto_exclude_caller: bool = True,
    plugins: Tuple[PicoPlugin, ...] = (),
    reuse: bool = True,
    overrides: Optional[Dict[Any, Any]] = None,
) -> PicoContainer:

    root_name = root_package if isinstance(root_package, str) else getattr(root_package, "__name__", None)

    requested_profiles = profiles or [p.strip() for p in os.getenv("PICO_PROFILE", "").split(",") if p.strip()]
    if reuse and _state._container and _state._root_name == root_name:
        live = _state._container
        live_profiles = getattr(live, "_active_profiles", None)
        if (requested_profiles and live_profiles is not None and live_profiles != tuple(requested_profiles)):
            reuse = False
        if reuse:
            if overrides:
                _apply_overrides(live, overrides)
            return live

    combined_exclude = _build_exclude(exclude, auto_exclude_caller, root_name=root_name)

    container = PicoContainer()
    binder = Binder(container)
    logging.info("Initializing pico-ioc...")

    with _scanning_flag():
        scan_and_configure(
            root_package,
            container,
            exclude=combined_exclude,
            plugins=plugins,
        )

    if overrides:
        _apply_overrides(container, overrides)

    _run_hooks(plugins, "after_bind", container, binder)
    _run_hooks(plugins, "before_eager", container, binder)

    try:
        container._build_interceptors()
    except Exception:
        logging.exception("Failed to build method interceptors")

    apply_core_policy(container, profiles=requested_profiles)
    container._active_profiles = tuple(requested_profiles)
    container.apply_defaults()

    container.eager_instantiate_all()

    _run_hooks(plugins, "after_ready", container, binder)

    logging.info("Container configured and ready.")
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
    include: Optional[set[str]] = None,   # tag include (any-match)
    exclude: Optional[set[str]] = None,   # tag exclude (any-match)
    strict: bool = True,
    lazy: bool = True,
) -> PicoContainer:
    c = _ScopedContainer(base=base, strict=strict)

    logging.info("Initializing pico-ioc scope...")
    with _scanning_flag():
        for m in modules:
            scan_and_configure(m, c, exclude=None, plugins=())

    if overrides:
        _apply_overrides(c, overrides)

    def _tag_ok(meta: dict) -> bool:
        if include and not set(include).intersection(meta.get("tags", ())):
            return False
        if exclude and set(exclude).intersection(meta.get("tags", ())):
            return False
        return True

    c._providers = {k: v for k, v in c._providers.items() if _tag_ok(v)}  # type: ignore[attr-defined]

    allowed = _compute_allowed_subgraph(c, roots)
    keep_keys: set[Any] = set(allowed) | (set(overrides.keys()) if overrides else set())
    c._providers = {k: v for k, v in c._providers.items() if k in keep_keys}  # type: ignore[attr-defined]

    try:
        c._build_interceptors()
    except Exception:
        logging.exception("Failed to build method interceptors for scope")

    requested_profiles = profiles or [p.strip() for p in os.getenv("PICO_PROFILE", "").split(",") if p.strip()]
    apply_core_policy(c, profiles=requested_profiles)
    c._active_profiles = tuple(requested_profiles)
    c.apply_defaults()

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


def _apply_overrides(container: PicoContainer, overrides: Dict[Any, Any]) -> None:
    for key, val in overrides.items():
        lazy = False
        if isinstance(val, tuple) and len(val) == 2 and callable(val[0]) and isinstance(val[1], bool):
            provider = val[0]
            lazy = val[1]
        elif callable(val):
            provider = val
        else:
            def provider(v=val):
                return v
        container.bind(key, provider, lazy=lazy)


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
        if f and f.f_back and f.f_back.f_back and f.f_back.f_back.f_back:
            mod = inspect.getmodule(f.f_back.f_back.f_back)
            return getattr(mod, "__name__", None)
    except Exception:
        pass
    return None


def _run_hooks(
    plugins: Tuple[PicoPlugin, ...],
    hook_name: str,
    container: PicoContainer,
    binder: Binder,
) -> None:
    for pl in plugins:
        try:
            fn = getattr(pl, hook_name, None)
            if fn:
                fn(container, binder)
        except Exception:
            logging.exception("Plugin %s failed", hook_name)


@contextmanager
def _scanning_flag():
    tok = _state._scanning.set(True)
    try:
        yield
    finally:
        _state._scanning.reset(tok)

def _compute_allowed_subgraph(container: PicoContainer, roots: Iterable[type]) -> set:
    """
    Traverse constructor annotations from roots to collect reachable provider keys.
    Includes implementations for collection injections (list[T]/tuple[T]).
    Also include implementations for a root base class itself.
    """
    from .resolver import _get_hints
    from .container import _is_compatible  # structural / subclass check
    import inspect
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

        # NEW: if k is a base class, include its implementations too
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
    def __init__(self, base: Optional[PicoContainer], strict: bool):
        super().__init__()
        self._base = base
        self._strict = strict

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, key: Any):
        try:
            return super().get(key)
        except NameError as e:
            if not self._strict and self._base is not None and self._base.has(key):
                return self._base.get(key)
            raise e

