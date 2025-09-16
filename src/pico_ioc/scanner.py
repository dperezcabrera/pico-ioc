# src/pico_ioc/scanner.py
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
    INTERCEPTOR_META,
)
from .proxy import ComponentProxy
from .resolver import Resolver
from . import _state
from .utils import _provider_from_class, _provider_from_callable


def scan_and_configure(
    package_or_name: Any,
    container: PicoContainer,
    *,
    exclude: Optional[Callable[[str], bool]] = None,
    plugins: Tuple[PicoPlugin, ...] = (),
) -> tuple[int, int, list[tuple[Any, dict]]]:
    """
    Scan a package, bind components/factories, and collect interceptor declarations.

    Returns: (component_count, factory_count, interceptor_decls)
      - interceptor_decls entries:
          (cls, meta)                        for @interceptor class
          (fn, meta)                         for @interceptor function
          ((owner_cls, fn), meta)            for @interceptor methods
    """
    package = _as_module(package_or_name)
    logging.info("Scanning in '%s'...", getattr(package, "__name__", repr(package)))

    binder = Binder(container)
    resolver = Resolver(container)

    run_plugin_hook(plugins, "before_scan", package, binder)

    comp_classes, factory_classes, interceptor_decls = _collect_decorated(
        package=package,
        exclude=exclude,
        plugins=plugins,
        binder=binder,
    )

    run_plugin_hook(plugins, "after_scan", package, binder)

    _register_component_classes(classes=comp_classes, container=container, resolver=resolver)
    _register_factory_classes(factory_classes=factory_classes, container=container, resolver=resolver)

    return len(comp_classes), len(factory_classes), interceptor_decls


# -------------------- helpers --------------------

def _as_module(package_or_name: Any) -> ModuleType:
    if isinstance(package_or_name, str):
        return importlib.import_module(package_or_name)
    if hasattr(package_or_name, "__spec__"):
        return package_or_name  # type: ignore[return-value]
    raise TypeError("package_or_name must be a module or importable package name (str).")


def _iter_package_modules(package: ModuleType) -> Iterable[str]:
    """Yield fully-qualified module names under a package (recursive)."""
    try:
        pkg_path = package.__path__  # type: ignore[attr-defined]
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
) -> Tuple[List[type], List[type], List[tuple[Any, dict]]]:
    comps: List[type] = []
    facts: List[type] = []
    interceptors: List[tuple[Any, dict]] = []

    def _collect_from_class(cls: type):
        if getattr(cls, COMPONENT_FLAG, False):
            comps.append(cls)
        elif getattr(cls, FACTORY_FLAG, False):
            facts.append(cls)

        meta_class = getattr(cls, INTERCEPTOR_META, None)
        if meta_class:
            interceptors.append((cls, dict(meta_class)))

        for _nm, fn in inspect.getmembers(cls, predicate=inspect.isfunction):
            meta_m = getattr(fn, INTERCEPTOR_META, None)
            if meta_m:
                interceptors.append(((cls, fn), dict(meta_m)))

    def _visit_module(module: ModuleType):
        for _name, obj in inspect.getmembers(module, inspect.isclass):
            run_plugin_hook(plugins, "visit_class", module, obj, binder)
            _collect_from_class(obj)

        for _name, fn in inspect.getmembers(module, predicate=inspect.isfunction):
            meta = getattr(fn, INTERCEPTOR_META, None)
            if meta:
                interceptors.append((fn, dict(meta)))

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

    return comps, facts, interceptors


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

        for attr_name, func in inspect.getmembers(fcls, predicate=inspect.isfunction):
            provided_key = getattr(func, PROVIDES_KEY, None)
            if provided_key is None:
                continue

            is_lazy = bool(getattr(func, PROVIDES_LAZY, False))
            tags = tuple(getattr(func, PROVIDES_TAGS, ()))

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

