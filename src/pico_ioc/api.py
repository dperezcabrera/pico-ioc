# pico_ioc/api.py

import inspect
import logging
from contextlib import contextmanager
from typing import Callable, Optional, Tuple, Any, Dict  # ⬅️ Any, Dict

from .container import PicoContainer, Binder
from .plugins import PicoPlugin
from .scanner import scan_and_configure
from . import _state


def reset() -> None:
    """Reset the global container."""
    _state._container = None
    _state._root_name = None


def init(
    root_package,
    *,
    exclude: Optional[Callable[[str], bool]] = None,
    auto_exclude_caller: bool = True,
    plugins: Tuple[PicoPlugin, ...] = (),
    reuse: bool = True,
    overrides: Optional[Dict[Any, Any]] = None,  # ⬅️ NUEVO
) -> PicoContainer:

    root_name = root_package if isinstance(root_package, str) else getattr(root_package, "__name__", None)

    if reuse and _state._container and _state._root_name == root_name:
        if overrides:
            _apply_overrides(_state._container, overrides)
        return _state._container

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

    container.eager_instantiate_all()

    _run_hooks(plugins, "after_ready", container, binder)

    logging.info("Container configured and ready.")
    _state._container = container
    _state._root_name = root_name
    return container


# -------------------- helpers --------------------

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
        # frame -> _get_caller_module_name -> _build_exclude -> init
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

