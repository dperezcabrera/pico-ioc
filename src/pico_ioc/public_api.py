# pico_ioc/public_api.py

from __future__ import annotations
import importlib
import inspect
import pkgutil
import sys
from types import ModuleType
from typing import Dict, Iterable, Optional, Tuple

from .decorators import COMPONENT_FLAG, FACTORY_FLAG, PLUGIN_FLAG


def export_public_symbols_decorated(
    *packages: str,
    include_also: Optional[Iterable[str]] = None,
    include_plugins: bool = True,
):
    index: Dict[str, Tuple[str, str]] = {}

    def _collect(m: ModuleType):
        names = getattr(m, "__all__", None)
        if isinstance(names, (list, tuple, set)):
            for n in names:
                if hasattr(m, n):
                    index.setdefault(n, (m.__name__, n))
            return

        for n, obj in m.__dict__.items():
            if not inspect.isclass(obj):
                continue
            is_component = getattr(obj, COMPONENT_FLAG, False)
            is_factory = getattr(obj, FACTORY_FLAG, False)
            is_plugin = include_plugins and getattr(obj, PLUGIN_FLAG, False)
            if is_component or is_factory or is_plugin:
                index.setdefault(n, (m.__name__, n))

    for pkg_name in packages:
        try:
            base = importlib.import_module(pkg_name)
        except Exception:
            continue
        if hasattr(base, "__path__"):
            prefix = base.__name__ + "."
            for _, modname, _ in pkgutil.walk_packages(base.__path__, prefix):
                try:
                    m = importlib.import_module(modname)
                except Exception:
                    continue
                _collect(m)
        else:
            _collect(base)

    for qual in tuple(include_also or ()):
        modname, _, attr = qual.partition(":")
        if modname and attr:
            try:
                m = importlib.import_module(modname)
                if hasattr(m, attr):
                    index.setdefault(attr, (m.__name__, attr))
            except Exception:
                pass

    def __getattr__(name: str):
        try:
            modname, attr = index[name]
        except KeyError as e:
            raise AttributeError(f"module has no attribute {name!r}") from e
        mod = sys.modules.get(modname) or importlib.import_module(modname)
        return getattr(mod, attr)

    def __dir__():
        return sorted(index.keys())

    return __getattr__, __dir__

