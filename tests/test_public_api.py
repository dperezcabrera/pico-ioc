# tests/test_public_api_helper.py
from __future__ import annotations

import importlib
import os
import sys
import textwrap
from contextlib import contextmanager
from pathlib import Path
from typing import Dict


@contextmanager
def _make_pkg(tmp_path: Path, pkg_name: str, files: Dict[str, str]):
    """
    Creates a temporary package under tmp_path with given files.
    Yields the package import name and ensures cleanup from sys.modules/sys.path.
    """
    root = tmp_path / pkg_name
    root.mkdir(parents=True, exist_ok=True)

    # Ensure __init__.py exists if not provided
    if "__init__.py" not in files:
        files["__init__.py"] = ""

    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(content), encoding="utf-8")

    sys.path.insert(0, str(tmp_path))
    try:
        importlib.invalidate_caches()
        # Force fresh imports (clean any previous same-name pkg)
        for k in list(sys.modules.keys()):
            if k == pkg_name or k.startswith(pkg_name + "."):
                del sys.modules[k]
        yield pkg_name
    finally:
        # Cleanup sys.modules and sys.path
        for k in list(sys.modules.keys()):
            if k == pkg_name or k.startswith(pkg_name + "."):
                del sys.modules[k]
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))


def test_exports_components_factories_and_plugins(tmp_path: Path):
    with _make_pkg(
        tmp_path,
        "samplepkg_ok",
        {
            # package __init__ uses the helper
            "__init__.py": """
                from pico_ioc.public_api import export_public_symbols_decorated
                __getattr__, __dir__ = export_public_symbols_decorated("samplepkg_ok", include_plugins=True)
            """,
            "a_comp.py": """
                from pico_ioc import component
                @component
                class A:
                    pass

                class NotDecorated:
                    pass
            """,
            "a_factory.py": """
                from pico_ioc import factory_component, provides
                @factory_component
                class F:
                    @provides("val", lazy=True)
                    def make(self):
                        return 123
            """,
            "plugins.py": """
                from pico_ioc import plugin
                @plugin
                class MyPlugin:
                    pass
            """,
        },
    ) as pkg:
        mod = importlib.import_module(pkg)

        # Should export decorated classes
        A = getattr(mod, "A")
        F = getattr(mod, "F")
        MyPlugin = getattr(mod, "MyPlugin")

        assert A.__name__ == "A"
        assert F.__name__ == "F"
        assert MyPlugin.__name__ == "MyPlugin"

        # Should not export non-decorated classes
        dir_items = dir(mod)
        assert "NotDecorated" not in dir_items

        # __getattr__ must raise AttributeError for unknown symbol
        try:
            getattr(mod, "DoesNotExist")
        except AttributeError:
            pass
        else:
            raise AssertionError("Expected AttributeError for unknown attribute")


def test_respects___all___overrides_decorated_scan(tmp_path: Path):
    with _make_pkg(
        tmp_path,
        "samplepkg_all",
        {
            "__init__.py": """
                from pico_ioc.public_api import export_public_symbols_decorated
                __getattr__, __dir__ = export_public_symbols_decorated("samplepkg_all", include_plugins=True)
            """,
            "mod_x.py": """
                __all__ = ["PublicX"]

                PublicX = 42

                from pico_ioc import component
                @component
                class HiddenDecorated:
                    pass
            """,
        },
    ) as pkg:
        mod = importlib.import_module(pkg)
        # Only names in __all__ should be exported from mod_x
        assert getattr(mod, "PublicX") == 42
        assert "HiddenDecorated" not in dir(mod)


def test_include_also_adds_explicit_symbols(tmp_path: Path):
    with _make_pkg(
        tmp_path,
        "samplepkg_extra",
        {
            "__init__.py": """
                from pico_ioc.public_api import export_public_symbols_decorated
                __getattr__, __dir__ = export_public_symbols_decorated(
                    "samplepkg_extra",
                    include_plugins=True,
                    include_also=["samplepkg_extra.extra:EXPORTED_CONST", "samplepkg_extra.extra:ExportedClass"]
                )
            """,
            "extra.py": """
                EXPORTED_CONST = 7
                class ExportedClass: pass
                class NotListed: pass
            """,
        },
    ) as pkg:
        mod = importlib.import_module(pkg)
        assert getattr(mod, "EXPORTED_CONST") == 7
        assert getattr(mod, "ExportedClass").__name__ == "ExportedClass"
        assert "NotListed" not in dir(mod)


def test_include_plugins_false_does_not_export_plugins(tmp_path: Path):
    with _make_pkg(
        tmp_path,
        "samplepkg_noplugins",
        {
            "__init__.py": """
                from pico_ioc.public_api import export_public_symbols_decorated
                __getattr__, __dir__ = export_public_symbols_decorated("samplepkg_noplugins", include_plugins=False)
            """,
            "plugins.py": """
                from pico_ioc import plugin
                @plugin
                class P: pass
            """,
            "components.py": """
                from pico_ioc import component
                @component
                class C: pass
            """,
        },
    ) as pkg:
        mod = importlib.import_module(pkg)
        # Component exported
        assert getattr(mod, "C").__name__ == "C"
        # Plugin should NOT be exported when include_plugins=False
        assert "P" not in dir(mod)
        try:
            getattr(mod, "P")
        except AttributeError:
            pass
        else:
            raise AssertionError("Plugin should not be exported when include_plugins=False")


def test_subpackages_are_scanned(tmp_path: Path):
    with _make_pkg(
        tmp_path,
        "samplepkg_sub",
        {
            "__init__.py": """
                from pico_ioc.public_api import export_public_symbols_decorated
                __getattr__, __dir__ = export_public_symbols_decorated("samplepkg_sub", include_plugins=True)
            """,
            "sub/__init__.py": "",
            "sub/m1.py": """
                from pico_ioc import component
                @component
                class SubC: pass
            """,
            "sub/inner/__init__.py": "",
            "sub/inner/m2.py": """
                from pico_ioc import factory_component
                @factory_component
                class SubF: pass
            """,
        },
    ) as pkg:
        mod = importlib.import_module(pkg)
        assert getattr(mod, "SubC").__name__ == "SubC"
        assert getattr(mod, "SubF").__name__ == "SubF"

