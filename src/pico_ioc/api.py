import inspect
import logging
from contextlib import contextmanager
from typing import Callable, Optional, Tuple

from .container import PicoContainer, Binder
from .plugins import PicoPlugin
from .scanner import scan_and_configure
from . import _state


def reset() -> None:
    """Reset the global container state."""
    _state._container = None


def init(
    root_package,
    *,
    exclude: Optional[Callable[[str], bool]] = None,
    auto_exclude_caller: bool = True,
    plugins: Tuple[PicoPlugin, ...] = (),
    reuse: bool = True,
) -> PicoContainer:
    """
    Initialize and configure a PicoContainer with automatic scanning.

    Args:
        root_package: Root package to scan for components.
        exclude: Optional filter to exclude specific modules.
        auto_exclude_caller: If True, exclude the calling module automatically.
        plugins: Plugins that can hook into the container lifecycle.
        reuse: If True, reuse an already-initialized container.

    Returns:
        A fully configured PicoContainer instance.
    """
    if reuse and _state._container:
        return _state._container

    combined_exclude = _build_exclude(exclude, auto_exclude_caller)

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

    _run_hooks(plugins, "after_bind", container, binder)
    _run_hooks(plugins, "before_eager", container, binder)

    container.eager_instantiate_all()

    _run_hooks(plugins, "after_ready", container, binder)

    logging.info("Container configured and ready.")
    _state._container = container
    return container


# -------------------- Private helpers --------------------

def _build_exclude(
    exclude: Optional[Callable[[str], bool]],
    auto_exclude_caller: bool,
) -> Optional[Callable[[str], bool]]:
    """
    Build the exclude function, optionally excluding the calling module as well.
    """
    if not auto_exclude_caller:
        return exclude

    caller = _get_caller_module_name()
    if not caller:
        return exclude

    if exclude is None:
        return lambda mod, _caller=caller: mod == _caller

    prev = exclude
    return lambda mod, _caller=caller, _prev=prev: (mod == _caller) or _prev(mod)


def _get_caller_module_name() -> Optional[str]:
    """
    Return the module name of the code that called `init`.

    Uses frame inspection with minimal depth instead of full inspect.stack()
    to reduce overhead and complexity.
    """
    try:
        frame = inspect.currentframe()
        # frame -> _get_caller_module_name -> _build_exclude -> init
        # We want the caller of init, which is 3 frames up.
        if frame and frame.f_back and frame.f_back.f_back and frame.f_back.f_back.f_back:
            mod = inspect.getmodule(frame.f_back.f_back.f_back)
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
    """
    Execute the given lifecycle hook safely across all plugins.
    Exceptions are logged but do not stop execution.
    """
    for pl in plugins:
        try:
            fn = getattr(pl, hook_name, None)
            if fn:
                fn(container, binder)
        except Exception:
            logging.exception("Plugin %s failed", hook_name)


@contextmanager
def _scanning_flag():
    """
    Context manager that temporarily sets the `_scanning` flag in global state.
    """
    tok = _state._scanning.set(True)
    try:
        yield
    finally:
        _state._scanning.reset(tok)

