# src/pico_ioc/__init__.py

import functools, inspect, pkgutil, importlib, logging, sys
from typing import Callable, Any, Iterator, AsyncIterator

try:
    # written at build time by setuptools-scm
    from ._version import __version__
except Exception:  # pragma: no cover
    __version__ = "0.0.0"

__all__ = ["__version__"]

# ==============================================================================
# --- 1. Container and Chameleon Proxy (Framework-Agnostic) ---
# ==============================================================================
class PicoContainer:
    def __init__(self):
        self._providers = {}
        self._singletons = {}

    def bind(self, key: Any, provider: Callable[[], Any]):
        self._providers[key] = provider

    def get(self, key: Any) -> Any:
        if key in self._singletons:
            return self._singletons[key]
        if key in self._providers:
            instance = self._providers[key]()
            self._singletons[key] = instance
            return instance
        raise NameError(f"No provider found for key: {key}")

class LazyProxy:
    """
    A full-fledged lazy proxy that delegates almost all operations
    to the real object, which is created only on first access.
    It is completely framework-agnostic.
    """
    def __init__(self, object_creator: Callable[[], Any]):
        object.__setattr__(self, "_object_creator", object_creator)
        object.__setattr__(self, "__real_object", None)

    def _get_real_object(self) -> Any:
        real_obj = object.__getattribute__(self, "__real_object")
        if real_obj is None:
            real_obj = object.__getattribute__(self, "_object_creator")()
            object.__setattr__(self, "__real_object", real_obj)
        return real_obj

    # --- Core Proxying and Representation ---
    @property
    def __class__(self):
        return self._get_real_object().__class__

    def __getattr__(self, name):
        return getattr(self._get_real_object(), name)
        
    def __setattr__(self, name, value):
        setattr(self._get_real_object(), name, value)

    def __delattr__(self, name):
        delattr(self._get_real_object(), name)

    def __str__(self):
        return str(self._get_real_object())

    def __repr__(self):
        return repr(self._get_real_object())
        
    def __dir__(self):
        return dir(self._get_real_object())

    # --- Emulation of container types ---
    def __len__(self): return len(self._get_real_object())
    def __getitem__(self, key): return self._get_real_object()[key]
    def __setitem__(self, key, value): self._get_real_object()[key] = value
    def __delitem__(self, key): del self._get_real_object()[key]
    def __iter__(self): return iter(self._get_real_object())
    def __reversed__(self): return reversed(self._get_real_object())
    def __contains__(self, item): return item in self._get_real_object()

    # --- Emulation of numeric types and operators ---
    def __add__(self, other): return self._get_real_object() + other
    def __sub__(self, other): return self._get_real_object() - other
    def __mul__(self, other): return self._get_real_object() * other
    def __matmul__(self, other): return self._get_real_object() @ other
    def __truediv__(self, other): return self._get_real_object() / other
    def __floordiv__(self, other): return self._get_real_object() // other
    def __mod__(self, other): return self._get_real_object() % other
    def __divmod__(self, other): return divmod(self._get_real_object(), other)
    def __pow__(self, other, modulo=None): return pow(self._get_real_object(), other, modulo)
    def __lshift__(self, other): return self._get_real_object() << other
    def __rshift__(self, other): return self._get_real_object() >> other
    def __and__(self, other): return self._get_real_object() & other
    def __xor__(self, other): return self._get_real_object() ^ other
    def __or__(self, other): return self._get_real_object() | other

    # --- Right-hand side numeric operators ---
    def __radd__(self, other): return other + self._get_real_object()
    def __rsub__(self, other): return other - self._get_real_object()
    def __rmul__(self, other): return other * self._get_real_object()
    def __rmatmul__(self, other): return other @ self._get_real_object()
    def __rtruediv__(self, other): return other / self._get_real_object()
    def __rfloordiv__(self, other): return other // self._get_real_object()
    def __rmod__(self, other): return other % self._get_real_object()
    def __rdivmod__(self, other): return divmod(other, self._get_real_object())
    def __rpow__(self, other): return pow(other, self._get_real_object())
    def __rlshift__(self, other): return other << self._get_real_object()
    def __rrshift__(self, other): return other >> self._get_real_object()
    def __rand__(self, other): return other & self._get_real_object()
    def __rxor__(self, other): return other ^ self._get_real_object()
    def __ror__(self, other): return other | self._get_real_object()

    # --- Unary operators ---
    def __neg__(self): return -self._get_real_object()
    def __pos__(self): return +self._get_real_object()
    def __abs__(self): return abs(self._get_real_object())
    def __invert__(self): return ~self._get_real_object()

    # --- Comparison operators ---
    def __eq__(self, other): return self._get_real_object() == other
    def __ne__(self, other): return self._get_real_object() != other
    def __lt__(self, other): return self._get_real_object() < other
    def __le__(self, other): return self._get_real_object() <= other
    def __gt__(self, other): return self._get_real_object() > other
    def __ge__(self, other): return self._get_real_object() >= other
    def __hash__(self): return hash(self._get_real_object())

    # --- Truthiness, Callability and Context Management ---
    def __bool__(self): return bool(self._get_real_object())
    def __call__(self, *args, **kwargs): return self._get_real_object()(*args, **kwargs)
    def __enter__(self): return self._get_real_object().__enter__()
    def __exit__(self, exc_type, exc_val, exc_tb): return self._get_real_object().__exit__(exc_type, exc_val, exc_tb)

# ==============================================================================
# --- 2. The Scanner and `init` Facade ---
# ==============================================================================
def _scan_and_configure(package_or_name, container: PicoContainer):
    package = importlib.import_module(package_or_name) if isinstance(package_or_name, str) else package_or_name
    logging.info(f"🚀 Scanning in '{package.__name__}'...")
    component_classes, factory_classes = [], []
    for _, name, _ in pkgutil.walk_packages(package.__path__, package.__name__ + '.'):
        try:
            module = importlib.import_module(name)
            for _, obj in inspect.getmembers(module, inspect.isclass):
                if hasattr(obj, '_is_component'):
                    component_classes.append(obj)
                elif hasattr(obj, '_is_factory_component'):
                    factory_classes.append(obj)
        except Exception as e:
            logging.warning(f"  ⚠️ Module {name} not processed: {e}")

    for factory_cls in factory_classes:
        try:
            sig = inspect.signature(factory_cls.__init__)
            instance = factory_cls(container) if 'container' in sig.parameters else factory_cls()
            for _, method in inspect.getmembers(instance, inspect.ismethod):
                if hasattr(method, '_provides_name'):
                    container.bind(getattr(method, '_provides_name'), method)
        except Exception as e:
            logging.error(f"  ❌ Error in factory {factory_cls.__name__}: {e}", exc_info=True)

    for component_cls in component_classes:
        key = getattr(component_cls, '_component_key', component_cls)
        def create_component(cls=component_cls):
            sig = inspect.signature(cls.__init__)
            deps = {}
            for p in sig.parameters.values():
                if p.name == 'self' or p.kind in (
                    inspect.Parameter.VAR_POSITIONAL,  # *args
                    inspect.Parameter.VAR_KEYWORD,     # **kwargs
                ):
                    continue
                dep_key = p.annotation if p.annotation is not inspect._empty else p.name
                deps[p.name] = container.get(dep_key)
            return cls(**deps)
        container.bind(key, create_component)

_container = None
def init(root_package):
    global _container
    if _container:
        return _container
    _container = PicoContainer()
    logging.info("🔌 Initializing 'pico-ioc'...")
    _scan_and_configure(root_package, _container)
    logging.info("✅ Container configured and ready.")
    return _container

# ==============================================================================
# --- 3. The Decorators ---
# ==============================================================================
def factory_component(cls):
    setattr(cls, '_is_factory_component', True)
    return cls

def provides(name: str, lazy: bool = True):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return LazyProxy(lambda: func(*args, **kwargs)) if lazy else func(*args, **kwargs)
        setattr(wrapper, '_provides_name', name)
        return wrapper
    return decorator

def component(cls=None, *, name: str = None):
    def decorator(cls):
        setattr(cls, '_is_component', True)
        setattr(cls, '_component_key', name if name is not None else cls)
        return cls
    return decorator(cls) if cls else decorator

