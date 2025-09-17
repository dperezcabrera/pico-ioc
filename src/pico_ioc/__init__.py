try:
    from ._version import __version__
except Exception:
    __version__ = "0.0.0"

from .container import PicoContainer, Binder
from .scope import ScopedContainer
from .decorators import (
    component, factory_component, provides, plugin,
    Qualifier, qualifier,
    on_missing, primary, conditional, infrastructure,
)
from .plugins import PicoPlugin
from .resolver import Resolver
from .api import init, reset, scope, container_fingerprint
from .proxy import ComponentProxy, IoCProxy
from .interceptors import (
    MethodInterceptor,
    ContainerInterceptor,
    MethodCtx,
    ResolveCtx,
    CreateCtx,
)
from .config import (
    config_component, EnvSource, FileSource,
    Env, File, Path, Value,
)
from .infra import Infra, Select

__all__ = [
    "__version__",
    "PicoContainer",
    "Binder",
    "PicoPlugin",
    "ComponentProxy",
    "IoCProxy",
    "MethodInterceptor",
    "ContainerInterceptor",
    "MethodCtx",
    "ResolveCtx",
    "CreateCtx",
    "init",
    "scope",
    "reset",
    "container_fingerprint",
    "component",
    "factory_component",
    "provides",
    "plugin",
    "Qualifier",
    "qualifier",
    "on_missing",
    "primary",
    "conditional",
    "infrastructure",
    "Resolver",
    "ScopedContainer",
    "config_component",
    "EnvSource",
    "FileSource",
    "Env",
    "File",
    "Path",
    "Value",
    "Infra",
    "Select",
]

