from __future__ import annotations
import importlib
import inspect
import logging
import pkgutil
from types import ModuleType
from typing import Any, Callable, Optional, Tuple, List, Iterable

from .plugins import run_plugin_hook, PicoPlugin
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
    INFRA_META,
)
from .proxy import ComponentProxy
from .resolver import Resolver
from . import _state
from .utils import _provider_from_class, _provider_from_callable
from .config import is_config_component, build_component_instance, ConfigRegistry

def scan_and_configure(
    package_or_name: Any,
    container: PicoContainer,
    *,
    exclude: Optional[Callable[[str], bool]] = None,
    plugins: Tuple[PicoPlugin, ...] = (),
) -> tuple[int, int, list[tuple[type, dict]]]:
    package = _as_module(package_or_name)
    logging.info("Scanning in '%s'...", getattr(package, "__name__", repr(package)))
    binder = Binder(container)
    resolver = Resolver(container)
    run_plugin_hook(plugins, "before_scan", package, binder)
    comp_classes, factory_classes, infra_decls = _collect_decorated(
        package=package,
        exclude=exclude,
        plugins=plugins,
        binder=binder,
    )
    run_plugin_hook(plugins, "after_scan", package, binder)
    _register_component_classes(classes=comp_classes, container=container, resolver=resolver)
    _register_factory_classes(factory_classes=factory_classes, container=container, resolver=resolver)
    return len(comp_classes), len(factory_classes), infra_decls

def _as_module(package_or_name: Any) -> ModuleType:
    if isinstance(package_or_name, str):
        return importlib.import_module(package_or_name)
    if hasattr(package_or_name, "__spec__"):
        return package_or_name
    raise TypeError("package_or_name must be a module or importable package name (str).")

def _iter_package_modules(package: ModuleType) -> Iterable[str]:
    try:
        pkg_path = package.__path__
    except Exception:
        return
    prefix = package.__name__ + "."
    for _finder, name, _is_pkg in pkgutil.walk_packages(pkg_path, prefix):
        yield name

def _collect_decorated(
    *,
    package: ModuleType,
    exclude: Optional[Callable[[str], bool]],
    plugins: Tuple[PicoPlugin, ...],
    binder: Binder,
) -> Tuple[List[type], List[type], List[tuple[type, dict]]]:
    comps: List[type] = []
    facts: List[type] = []
    infras: List[tuple[type, dict]] = []

    def _collect_from_class(cls: type):
        if getattr(cls, COMPONENT_FLAG, False):
            comps.append(cls)
        elif getattr(cls, FACTORY_FLAG, False):
            facts.append(cls)
        infra_m = getattr(cls, INFRA_META, None)
        if infra_m:
            infras.append((cls, dict(infra_m)))
        for _nm, _fn in inspect.getmembers(cls, predicate=inspect.isfunction):
            pass

    def _visit_module(module: ModuleType):
        for _name, obj in inspect.getmembers(module, inspect.isclass):
            run_plugin_hook(plugins, "visit_class", module, obj, binder)
            _collect_from_class(obj)

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

    if not hasattr(package, "__path__"):
        _visit_module(package)

    return comps, facts, infras

def _register_component_classes(
    *,
    classes: List[type],
    container: PicoContainer,
    resolver: Resolver,
) -> None:
    for cls in classes:
        key = getattr(cls, COMPONENT_KEY, cls)
        is_lazy = bool(getattr(cls, COMPONENT_LAZY, False))
        tags = tuple(getattr(cls, COMPONENT_TAGS, ()))
        if is_config_component(cls):
            registry: ConfigRegistry | None = getattr(container, "_config_registry", None)
            def _prov(_c=cls, _reg=registry):
                if _reg is None:
                    raise RuntimeError(f"No config registry found to build {_c.__name__}")
                return build_component_instance(_c, _reg)
            provider = (lambda p=_prov: ComponentProxy(p)) if is_lazy else _prov
        else:
            provider = _provider_from_class(cls, resolver=resolver, lazy=is_lazy)
        container.bind(key, provider, lazy=is_lazy, tags=tags)

def _register_factory_classes(
    *,
    factory_classes: List[type],
    container: PicoContainer,
    resolver: Resolver,
) -> None:
    for fcls in factory_classes:
        try:
            tok_res = _state._resolving.set(True)
            try:
                finst = resolver.create_instance(fcls)
            finally:
                _state._resolving.reset(tok_res)
        except Exception:
            logging.exception("Error in factory %s", fcls.__name__)
            continue
        raw_dict = getattr(fcls, "__dict__", {})
        for attr_name, attr in inspect.getmembers(fcls):
            func = None
            raw = raw_dict.get(attr_name, None)
            if isinstance(raw, classmethod):
                func = raw.__func__
            elif isinstance(raw, staticmethod):
                func = raw.__func__
            elif inspect.isfunction(attr):
                func = attr
            if func is None:
                continue
            provided_key = getattr(func, PROVIDES_KEY, None)
            if provided_key is None:
                continue
            is_lazy = bool(getattr(func, PROVIDES_LAZY, False))
            tags = tuple(getattr(func, PROVIDES_TAGS, ()))
            if isinstance(raw, (classmethod, staticmethod)):
                bound = getattr(fcls, attr_name)
            else:
                bound = getattr(finst, attr_name, func.__get__(finst, fcls))
            prov = _provider_from_callable(bound, owner_cls=fcls, resolver=resolver, lazy=is_lazy)
            if isinstance(provided_key, type):
                try:
                    setattr(prov, "_pico_alias_for", provided_key)
                except Exception:
                    pass
                unique_key = (provided_key, f"{fcls.__name__}.{attr_name}")
                container.bind(unique_key, prov, lazy=is_lazy, tags=tags)
            else:
                container.bind(provided_key, prov, lazy=is_lazy, tags=tags)

