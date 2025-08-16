import functools
import importlib
import inspect
import logging
import pkgutil
from contextvars import ContextVar
from typing import Any, Callable, Dict, Optional, Protocol, Tuple, runtime_checkable

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
    "component",
    "factory_component",
    "provides",
    "resolve_param",
    "create_instance",
]

_scanning: ContextVar[bool] = ContextVar("pico_scanning", default=False)
_resolving: ContextVar[bool] = ContextVar("pico_resolving", default=False)

class PicoContainer:
    def __init__(self):
        self._providers: Dict[Any, Dict[str, Any]] = {}
        self._singletons: Dict[Any, Any] = {}

    def bind(self, key: Any, provider: Callable[[], Any], *, lazy: bool):
        self._providers[key] = {"factory": provider, "lazy": bool(lazy)}

    def has(self, key: Any) -> bool:
        return key in self._providers or key in self._singletons

    def get(self, key: Any) -> Any:
        if _scanning.get() and not _resolving.get():
            raise RuntimeError("pico-ioc: re-entrant container access during scan.")
        if key in self._singletons:
            return self._singletons[key]
        prov = self._providers.get(key)
        if prov is None:
            raise NameError(f"No provider found for key: {key}")
        instance = prov["factory"]()
        self._singletons[key] = instance
        return instance

    def _eager_instantiate_all(self):
        for key, meta in list(self._providers.items()):
            if not meta.get("lazy", False) and key not in self._singletons:
                self.get(key)

class Binder:
    def __init__(self, container: PicoContainer):
        self._c = container

    def bind(self, key: Any, provider: Callable[[], Any], *, lazy: bool = False):
        self._c.bind(key, provider, lazy=lazy)

    def has(self, key: Any) -> bool:
        return self._c.has(key)

    def get(self, key: Any) -> Any:
        return self._c.get(key)

def factory_component(cls):
    setattr(cls, '_is_factory_component', True)
    return cls

def provides(key: Any, *, lazy: bool = False):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        setattr(wrapper, '_provides_name', key)
        setattr(wrapper, '_pico_lazy', bool(lazy))
        return wrapper
    return decorator

def component(cls=None, *, name: Any = None, lazy: bool = False):
    def decorator(c):
        setattr(c, '_is_component', True)
        setattr(c, '_component_key', name if name is not None else c)
        setattr(c, '_component_lazy', bool(lazy))
        return c
    return decorator(cls) if cls else decorator

class ComponentProxy:
    def __init__(self, object_creator: Callable[[], Any]):
        object.__setattr__(self, "_object_creator", object_creator)
        object.__setattr__(self, "__real_object", None)

    def _get_real_object(self) -> Any:
        real_obj = object.__getattribute__(self, "__real_object")
        if real_obj is None:
            real_obj = object.__getattribute__(self, "_object_creator")()
            object.__setattr__(self, "__real_object", real_obj)
        return real_obj

    @property
    def __class__(self):
        return self._get_real_object().__class__

    def __getattr__(self, name): return getattr(self._get_real_object(), name)
    def __setattr__(self, name, value): setattr(self._get_real_object(), name, value)
    def __delattr__(self, name): delattr(self._get_real_object(), name)
    def __str__(self): return str(self._get_real_object())
    def __repr__(self): return repr(self._get_real_object())
    def __dir__(self): return dir(self._get_real_object())
    def __len__(self): return len(self._get_real_object())
    def __getitem__(self, key): return self._get_real_object()[key]
    def __setitem__(self, key, value): self._get_real_object()[key] = value
    def __delitem__(self, key): del self._get_real_object()[key]
    def __iter__(self): return iter(self._get_real_object())
    def __reversed__(self): return reversed(self._get_real_object())
    def __contains__(self, item): return item in self._get_real_object()
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
    def __neg__(self): return -self._get_real_object()
    def __pos__(self): return +self._get_real_object()
    def __abs__(self): return abs(self._get_real_object())
    def __invert__(self): return ~self._get_real_object()
    def __eq__(self, other): return self._get_real_object() == other
    def __ne__(self, other): return self._get_real_object() != other
    def __lt__(self, other): return self._get_real_object() < other
    def __le__(self, other): return self._get_real_object() <= other
    def __gt__(self, other): return self._get_real_object() > other
    def __ge__(self, other): return self._get_real_object() >= other
    def __hash__(self): return hash(self._get_real_object())
    def __bool__(self): return bool(self._get_real_object())
    def __call__(self, *args, **kwargs): return self._get_real_object()(*args, **kwargs)
    def __enter__(self): return self._get_real_object().__enter__()
    def __exit__(self, exc_type, exc_val, exc_tb): return self._get_real_object().__exit__(exc_type, exc_val, exc_tb)

def resolve_param(container: PicoContainer, p: inspect.Parameter) -> Any:
    if p.name == 'self' or p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
        raise RuntimeError("Invalid param for resolution")
    if container.has(p.name):
        return container.get(p.name)
    ann = p.annotation
    if ann is not inspect._empty and container.has(ann):
        return container.get(ann)
    if ann is not inspect._empty:
        try:
            for base in getattr(ann, "__mro__", ())[1:]:
                if base is object:
                    break
                if container.has(base):
                    return container.get(base)
        except Exception:
            pass
    if container.has(str(p.name)):
        return container.get(str(p.name))
    key = p.name if ann is inspect._empty else ann
    return container.get(key)

def create_instance(cls: type, container: PicoContainer) -> Any:
    """
    Instantiate `cls` with constructor DI from `container`.

    Resolution rules:
      - Skip `self`, *args, **kwargs.
      - Try resolve_param(...) for each parameter.
      - If resolve_param raises NameError AND the parameter has a default,
        skip injecting it so Python uses the default value.
      - Otherwise, propagate the error.

    This preserves the "name > type > MRO > str(name)" precedence in resolve_param,
    while making defaulted, annotated parameters truly optional.
    """
    sig = inspect.signature(cls.__init__)
    deps: Dict[str, Any] = {}

    tok = _resolving.set(True)
    try:
        for p in sig.parameters.values():
            if p.name == 'self' or p.kind in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            ):
                continue

            try:
                deps[p.name] = resolve_param(container, p)
            except NameError:
                if p.default is not inspect._empty:
                    continue
                raise
    finally:
        _resolving.reset(tok)

    return cls(**deps)


@runtime_checkable
class PicoPlugin(Protocol):
    def before_scan(self, package: Any, binder: Binder) -> None: ...
    def visit_class(self, module: Any, cls: type, binder: Binder) -> None: ...
    def after_scan(self, package: Any, binder: Binder) -> None: ...
    def after_bind(self, container: PicoContainer, binder: Binder) -> None: ...
    def before_eager(self, container: PicoContainer, binder: Binder) -> None: ...
    def after_ready(self, container: PicoContainer, binder: Binder) -> None: ...

def _scan_and_configure(
    package_or_name,
    container: PicoContainer,
    *,
    exclude: Optional[Callable[[str], bool]] = None,
    plugins: Tuple[PicoPlugin, ...] = (),
):
    package = importlib.import_module(package_or_name) if isinstance(package_or_name, str) else package_or_name
    logging.info(f"Scanning in '{package.__name__}'...")
    binder = Binder(container)

    for pl in plugins:
        try:
            if hasattr(pl, "before_scan"):
                pl.before_scan(package, binder)
        except Exception:
            logging.exception("Plugin before_scan failed")

    component_classes, factory_classes = [], []
    for _, name, _ in pkgutil.walk_packages(package.__path__, package.__name__ + '.'):
        if exclude and exclude(name):
            logging.info(f"Skipping module {name} (excluded)")
            continue
        try:
            module = importlib.import_module(name)
            for _, obj in inspect.getmembers(module, inspect.isclass):
                for pl in plugins:
                    try:
                        if hasattr(pl, "visit_class"):
                            pl.visit_class(module, obj, binder)
                    except Exception:
                        logging.exception("Plugin visit_class failed")
                if getattr(obj, '_is_component', False):
                    component_classes.append(obj)
                elif getattr(obj, '_is_factory_component', False):
                    factory_classes.append(obj)
        except Exception as e:
            logging.warning(f"Module {name} not processed: {e}")

    for pl in plugins:
        try:
            if hasattr(pl, "after_scan"):
                pl.after_scan(package, binder)
        except Exception:
            logging.exception("Plugin after_scan failed")
            
    for component_cls in component_classes:
        key = getattr(component_cls, '_component_key', component_cls)
        is_lazy = bool(getattr(component_cls, '_component_lazy', False))

        def provider_factory(lazy=is_lazy, cls=component_cls):
            def _factory():
                if lazy:
                    return ComponentProxy(lambda: create_instance(cls, container))
                return create_instance(cls, container)
            return _factory

        container.bind(key, provider_factory(), lazy=is_lazy)


    def _resolve_method_kwargs(meth) -> Dict[str, Any]:
        sig = inspect.signature(meth)
        deps = {}
        tok = _resolving.set(True)
        try:
            for p in sig.parameters.values():
                if p.name == 'self' or p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                    continue
                try:
                    deps[p.name] = resolve_param(container, p)
                except NameError:
                    if p.default is not inspect._empty:
                        continue
                    raise
        finally:
            _resolving.reset(tok)
        return deps

    for factory_cls in factory_classes:
        try:
            factory_instance = create_instance(factory_cls, container)

            for name, func in inspect.getmembers(factory_cls, predicate=inspect.isfunction):
                provides_key = getattr(func, '_provides_name', None)
                if provides_key is None:
                    continue

                is_lazy = bool(getattr(func, '_pico_lazy', False))

                bound_method = getattr(factory_instance, name, None)
                if bound_method is None:
                    bound_method = func.__get__(factory_instance, factory_cls)

                fn_meta_src = getattr(bound_method, '__func__', bound_method)
                if getattr(fn_meta_src, '_provides_name', None) is not None:
                    provides_key = getattr(fn_meta_src, '_provides_name')
                    is_lazy = bool(getattr(fn_meta_src, '_pico_lazy', is_lazy))

                def make_provider(m=bound_method, lazy=is_lazy):
                    def _factory():
                        kwargs = _resolve_method_kwargs(m)

                        def _call():
                            return m(**kwargs)

                        if lazy:
                            return ComponentProxy(lambda: _call())
                        return _call()
                    return _factory

                container.bind(provides_key, make_provider(), lazy=is_lazy)
        except Exception:
            logging.exception(f"Error in factory {factory_cls.__name__}")



_container: Optional[PicoContainer] = None

def init(
    root_package,
    *,
    exclude: Optional[Callable[[str], bool]] = None,
    auto_exclude_caller: bool = True,
    plugins: Tuple[PicoPlugin, ...] = (),
):
    global _container
    if _container:
        return _container
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
    _container = PicoContainer()
    binder = Binder(_container)
    logging.info("Initializing pico-ioc...")
    tok = _scanning.set(True)
    try:
        _scan_and_configure(root_package, _container, exclude=combined_exclude, plugins=plugins)
    finally:
        _scanning.reset(tok)
    for pl in plugins:
        try:
            if hasattr(pl, "after_bind"):
                pl.after_bind(_container, binder)
        except Exception:
            logging.exception("Plugin after_bind failed")
    for pl in plugins:
        try:
            if hasattr(pl, "before_eager"):
                pl.before_eager(_container, binder)
        except Exception:
            logging.exception("Plugin before_eager failed")
    _container._eager_instantiate_all()
    for pl in plugins:
        try:
            if hasattr(pl, "after_ready"):
                pl.after_ready(_container, binder)
        except Exception:
            logging.exception("Plugin after_ready failed")
    logging.info("Container configured and ready.")
    return _container

