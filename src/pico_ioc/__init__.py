from ._version import __version__
from .container import PicoContainer, Binder
from .decorators import component, factory_component, provides
from .plugins import PicoPlugin
from .resolver import Resolver
from .api import init, reset
from .proxy import ComponentProxy

try:
    from ._version import __version__
except Exception:
    __version__ = "0.0.0"

__all__ = [
    "__version__",
    "PicoContainer",
    "Binder",
    "PicoPlugin",
    "init",
    "reset", 
    "component",
    "factory_component",
    "provides",
    "resolve_param",
    "create_instance",
]

