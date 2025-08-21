import importlib
import inspect
import logging
import pkgutil
from typing import Any, Callable, Optional, Tuple, List

from .container import PicoContainer, Binder
from .decorators import (
    COMPONENT_FLAG,
    COMPONENT_KEY,
    COMPONENT_LAZY,
    FACTORY_FLAG,
    PROVIDES_KEY,
    PROVIDES_LAZY,
)
from .proxy import ComponentProxy
from .resolver import Resolver
from .plugins import PicoPlugin


def scan_and_configure(
    package_or_name: Any,
    container: PicoContainer,
    *,
    exclude: Optional[Callable[[str], bool]] = None,
    plugins: Tuple[PicoPlugin, ...] = (),
):
    package = importlib.import_module(package_or_name) if isinstance(package_or_name, str) else package_or_name
    logging.info(f"Scanning in '{package.__name__}'...")
    binder = Binder(container)
    resolver = Resolver(container)

    for pl in plugins:
        try:
            getattr(pl, "before_scan", lambda *a, **k: None)(package, binder)
        except Exception:
            logging.exception("Plugin before_scan failed")

    comp_classes: List[type] = []
    factory_classes: List[type] = []

    for _, name, _ in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
        if exclude and exclude(name):
            logging.info(f"Skipping module {name} (excluded)")
            continue
        try:
            module = importlib.import_module(name)
            for _, obj in inspect.getmembers(module, inspect.isclass):
                for pl in plugins:
                    try:
                        getattr(pl, "visit_class", lambda *a, **k: None)(module, obj, binder)
                    except Exception:
                        logging.exception("Plugin visit_class failed")
                if getattr(obj, COMPONENT_FLAG, False):
                    comp_classes.append(obj)
                elif getattr(obj, FACTORY_FLAG, False):
                    factory_classes.append(obj)
        except Exception as e:
            logging.warning(f"Module {name} not processed: {e}")

    for pl in plugins:
        try:
            getattr(pl, "after_scan", lambda *a, **k: None)(package, binder)
        except Exception:
            logging.exception("Plugin after_scan failed")

    # Register @component classes (bind ONLY by declared key)
    for cls in comp_classes:
        key = getattr(cls, COMPONENT_KEY, cls)
        is_lazy = bool(getattr(cls, COMPONENT_LAZY, False))

        def provider_factory(c=cls, lazy=is_lazy):
            def _factory():
                if lazy:
                    return ComponentProxy(lambda: resolver.create_instance(c))
                return resolver.create_instance(c)
            return _factory

        container.bind(key, provider_factory(), lazy=is_lazy)

    # Register @factory_component methods marked with @provides
    for fcls in factory_classes:
        try:
            finst = resolver.create_instance(fcls)
            for name, func in inspect.getmembers(fcls, predicate=inspect.isfunction):
                pk = getattr(func, PROVIDES_KEY, None)
                if pk is None:
                    continue
                is_lazy = bool(getattr(func, PROVIDES_LAZY, False))
                bound = getattr(finst, name, func.__get__(finst, fcls))

                def make_provider(m=bound, lazy=is_lazy):
                    def _factory():
                        kwargs = resolver.kwargs_for_callable(m, owner_cls=fcls)

                        def _call():
                            return m(**kwargs)

                        return ComponentProxy(lambda: _call()) if lazy else _call()
                    return _factory

                container.bind(pk, make_provider(), lazy=is_lazy)
        except Exception:
            logging.exception(f"Error in factory {fcls.__name__}")

