# pico_ioc/scanner.py
import importlib
import inspect
import logging
import pkgutil
from types import ModuleType
from typing import Any, Callable, Optional, Tuple, List, Iterable

from .container import PicoContainer, Binder
from .decorators import (
    COMPONENT_FLAG,
    COMPONENT_KEY,
    COMPONENT_LAZY,
    FACTORY_FLAG,
    PROVIDES_KEY,
    PROVIDES_LAZY,
    COMPONENT_TAGS, 
    PROVIDES_TAGS,
)
from .proxy import ComponentProxy
from .resolver import Resolver
from .plugins import PicoPlugin
from . import _state


def scan_and_configure(
    package_or_name: Any,
    container: PicoContainer,
    *,
    exclude: Optional[Callable[[str], bool]] = None,
    plugins: Tuple[PicoPlugin, ...] = (),
) -> None:
    """
    Scan a package, discover component classes/factories, and bind them into the container.

    Args:
        package_or_name: Package module or importable package name (str).
        container: Target PicoContainer to receive bindings.
        exclude: Optional predicate that receives a module name and returns True to skip it.
        plugins: Optional lifecycle plugins that receive scan/bind events.
    """
    package = _as_module(package_or_name)
    logging.info("Scanning in '%s'...", getattr(package, "__name__", repr(package)))

    binder = Binder(container)
    resolver = Resolver(container)

    _run_plugin_hook(plugins, "before_scan", package, binder)

    comp_classes, factory_classes = _collect_decorated_classes(
        package=package,
        exclude=exclude,
        plugins=plugins,
        binder=binder,
    )

    _run_plugin_hook(plugins, "after_scan", package, binder)

    _register_component_classes(
        classes=comp_classes,
        container=container,
        resolver=resolver,
    )

    _register_factory_classes(
        factory_classes=factory_classes,
        container=container,
        resolver=resolver,
    )


# -------------------- Helpers (private) --------------------

def _as_module(package_or_name: Any) -> ModuleType:
    """Return a module from either a module object or an importable string name."""
    if isinstance(package_or_name, str):
        return importlib.import_module(package_or_name)
    if hasattr(package_or_name, "__spec__"):
        return package_or_name  # type: ignore[return-value]
    raise TypeError("package_or_name must be a module or importable package name (str).")


def _run_plugin_hook(
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


def _iter_package_modules(
    package: ModuleType,
) -> Iterable[str]:
    """
    Yield fully qualified module names under the given package.

    Requires the package to have a __path__ (i.e., be a package, not a single module).
    """
    try:
        pkg_path = package.__path__  # type: ignore[attr-defined]
    except Exception:
        return  # not a package; nothing to iterate

    prefix = package.__name__ + "."
    for _finder, name, _is_pkg in pkgutil.walk_packages(pkg_path, prefix):
        yield name


def _collect_decorated_classes(
    *,
    package: ModuleType,
    exclude: Optional[Callable[[str], bool]],
    plugins: Tuple[PicoPlugin, ...],
    binder: Binder,
) -> Tuple[List[type], List[type]]:
    """
    Import modules under `package`, visit classes, and collect those marked with
    @component or @factory_component decorators.
    """
    comp_classes: List[type] = []
    factory_classes: List[type] = []

    def _visit_module(module: ModuleType):
        for _name, obj in inspect.getmembers(module, inspect.isclass):
            # Allow plugins to inspect/transform/record classes
            _run_plugin_hook(plugins, "visit_class", module, obj, binder)

            # Collect decorated classes
            if getattr(obj, COMPONENT_FLAG, False):
                comp_classes.append(obj)
            elif getattr(obj, FACTORY_FLAG, False):
                factory_classes.append(obj)

    # 1) Si es un paquete, recorrer submódulos
    for mod_name in _iter_package_modules(package):
        if exclude and exclude(mod_name):
            logging.info("Skipping module %s (excluded)", mod_name)
            continue

        try:
            module = importlib.import_module(mod_name)
        except Exception as e:
            logging.warning("Module %s not processed: %s", mod_name, e)
            continue

        _visit_module(module)

    # 2) Si el “paquete” raíz es un módulo (sin __path__), también hay que visitarlo.
    if not hasattr(package, "__path__"):
        _visit_module(package)

    return comp_classes, factory_classes


def _register_component_classes(
    *,
    classes: List[type],
    container: PicoContainer,
    resolver: Resolver,
) -> None:
    """
    Register @component classes into the container.

    Binding key:
        - If the class has COMPONENT_KEY, use it; otherwise, bind by the class itself.
    Laziness:
        - If COMPONENT_LAZY is True, provide a proxy that defers instantiation.
    """
    for cls in classes:
        key = getattr(cls, COMPONENT_KEY, cls)
        is_lazy = bool(getattr(cls, COMPONENT_LAZY, False))
        tags = tuple(getattr(cls, COMPONENT_TAGS, ()))
        def _provider_factory(c=cls, lazy=is_lazy):
            def _factory():
                return ComponentProxy(lambda: resolver.create_instance(c)) if lazy else resolver.create_instance(c)
            return _factory
        container.bind(key, _provider_factory(), lazy=is_lazy, tags=tags)


def _register_factory_classes(
    *,
    factory_classes: List[type],
    container: PicoContainer,
    resolver: Resolver,
) -> None:
    """
    Register products of @factory_component classes.

    For each factory class:
        - Instantiate the factory via the resolver.
        - For each method with @provides:
            - Bind the provided key to a callable that calls the factory method.
            - If PROVIDES_LAZY is True, bind a proxy that defers the method call.
    """
    for fcls in factory_classes:
        try:
            # Durante el escaneo, permitir la resolución de dependencias de la factory
            # elevando temporalmente el flag `_resolving` para no chocar con la guardia.
            tok_res = _state._resolving.set(True)
            try:
                finst = resolver.create_instance(fcls)
            finally:
                _state._resolving.reset(tok_res)
        except Exception:
            logging.exception("Error in factory %s", fcls.__name__)
            continue

        for attr_name, func in inspect.getmembers(fcls, predicate=inspect.isfunction):
            provided_key = getattr(func, PROVIDES_KEY, None)
            if provided_key is None:
                continue
            is_lazy = bool(getattr(func, PROVIDES_LAZY, False))
            tags = tuple(getattr(func, PROVIDES_TAGS, ()))
            bound = getattr(finst, attr_name, func.__get__(finst, fcls))
            def _make_provider(m=bound, owner=fcls, lazy=is_lazy):
                def _factory():
                    kwargs = resolver.kwargs_for_callable(m, owner_cls=owner)
                    def _call(): return m(**kwargs)
                    return ComponentProxy(lambda: _call()) if lazy else _call()
                return _factory
            container.bind(provided_key, _make_provider(), lazy=is_lazy, tags=tags)

