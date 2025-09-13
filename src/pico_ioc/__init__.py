# pico_ioc/__init__.py
try:
    from ._version import __version__
except Exception:
    __version__ = "0.0.0"

from .container import PicoContainer, Binder
from .decorators import (
    component, factory_component, provides, plugin,
    Qualifier, qualifier,
    on_missing, primary, conditional,
)
from .plugins import PicoPlugin
from .resolver import Resolver
from .api import init, reset, scope
from .proxy import ComponentProxy, IoCProxy
from .interceptors import Invocation, MethodInterceptor

__all__ = [
    "__version__",
    "PicoContainer",
    "Binder",
    "PicoPlugin",
    "ComponentProxy",
    "IoCProxy",
    "Invocation",
    "MethodInterceptor",
    "init",
    "scope",
    "reset",
    "component",
    "factory_component",
    "provides",
    "plugin",
    "Qualifier",
    "qualifier",
    "on_missing",
    "primary",
    "conditional",
    "Resolver",
]

