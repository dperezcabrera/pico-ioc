# pico_ioc/plugins.py
from typing import Protocol, Any, Tuple
from .container import Binder, PicoContainer
import logging

class PicoPlugin(Protocol):
    def before_scan(self, package: Any, binder: Binder) -> None: ...
    def visit_class(self, module: Any, cls: type, binder: Binder) -> None: ...
    def after_scan(self, package: Any, binder: Binder) -> None: ...
    def after_bind(self, container: PicoContainer, binder: Binder) -> None: ...
    def before_eager(self, container: PicoContainer, binder: Binder) -> None: ...
    def after_ready(self, container: PicoContainer, binder: Binder) -> None: ...

def run_plugin_hook(
    plugins: Tuple[PicoPlugin, ...],
    hook_name: str,
    *args,
    **kwargs,
) -> None:
    """Run a lifecycle hook across all plugins, logging (but not raising) exceptions."""
    for pl in plugins:
        try:
            fn = getattr(pl, hook_name, None)
            if fn:
                fn(*args, **kwargs)
        except Exception:
            logging.exception("Plugin %s failed", hook_name)

