import inspect
import logging
from typing import Callable, Optional, Tuple
from .container import PicoContainer, Binder
from .plugins import PicoPlugin
from .scanner import scan_and_configure
from . import _state


def reset() -> None:
    _state._container = None


def init(
    root_package,
    *,
    exclude: Optional[Callable[[str], bool]] = None,
    auto_exclude_caller: bool = True,
    plugins: Tuple[PicoPlugin, ...] = (),
    reuse: bool = True,
) -> PicoContainer:
    if reuse and _state._container:
        return _state._container

    combined_exclude = exclude
    if auto_exclude_caller:
        try:
            caller_frame = inspect.stack()[1].frame
            caller_module = inspect.getmodule(caller_frame)
            caller_name = getattr(caller_module, "__name__", None)
        except Exception:
            caller_name = None
        if caller_name:
            if combined_exclude is None:
                def combined_exclude(mod: str, _caller=caller_name):
                    return mod == _caller
            else:
                prev = combined_exclude
                def combined_exclude(mod: str, _caller=caller_name, _prev=prev):
                    return mod == _caller or _prev(mod)

    container = PicoContainer()
    binder = Binder(container)
    logging.info("Initializing pico-ioc...")

    tok = _state._scanning.set(True)
    try:
        scan_and_configure(root_package, container, exclude=combined_exclude, plugins=plugins)
    finally:
        _state._scanning.reset(tok)

    for pl in plugins:
        try:
            getattr(pl, "after_bind", lambda *a, **k: None)(container, binder)
        except Exception:
            logging.exception("Plugin after_bind failed")
    for pl in plugins:
        try:
            getattr(pl, "before_eager", lambda *a, **k: None)(container, binder)
        except Exception:
            logging.exception("Plugin before_eager failed")

    container.eager_instantiate_all()

    for pl in plugins:
        try:
            getattr(pl, "after_ready", lambda *a, **k: None)(container, binder)
        except Exception:
            logging.exception("Plugin after_ready failed")

    logging.info("Container configured and ready.")
    _state._container = container
    return container

