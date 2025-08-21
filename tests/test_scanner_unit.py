# tests/test_scanner_unit.py
import sys
import textwrap
import logging

import pytest

from pico_ioc.container import PicoContainer
from pico_ioc.scanner import scan_and_configure


@pytest.fixture
def temp_pkg(tmp_path, monkeypatch):
    """
    Create a temporary Python package for realistic import-based scanning.
    Ensures cleanup of sys.modules so imports do not leak across tests.
    """
    base = tmp_path / "pkgx"
    base.mkdir()
    (base / "__init__.py").write_text("", encoding="utf-8")

    # Register A WITHOUT a custom name so that type-hint resolution works (key == class A).
    # Keep B with a custom name to verify named bindings and lazy behavior.
    (base / "services.py").write_text(textwrap.dedent("""
        from pico_ioc.decorators import component, factory_component, provides

        @component(lazy=False)
        class A:
            def __init__(self):
                self.tag = "A"

        @component(name="B_lazy", lazy=True)
        class B:
            def __init__(self, a: A):
                self.a = a

        @factory_component
        class ServiceFactory:
            @provides("svc_sync", lazy=False)
            def make_sync(self, a: A):
                return ("svc_sync", a.tag)

            @provides("svc_lazy", lazy=True)
            def make_lazy(self, a: A):
                return {"kind": "lazy_svc", "a": a.tag}
    """).strip(), encoding="utf-8")

    # Module that must be excluded by the filter
    (base / "skipped.py").write_text(textwrap.dedent("""
        from pico_ioc.decorators import component
        @component(name="ShouldNotAppear", lazy=False)
        class Ghost:
            pass
    """).strip(), encoding="utf-8")

    # Module that fails on import to trigger a warning
    (base / "broken.py").write_text(textwrap.dedent("""
        raise RuntimeError("boom")
    """).strip(), encoding="utf-8")

    monkeypatch.syspath_prepend(str(tmp_path))
    pkg_name = "pkgx"

    try:
        yield pkg_name, base
    finally:
        for mod in list(sys.modules.keys()):
            if mod == pkg_name or mod.startswith(pkg_name + "."):
                sys.modules.pop(mod, None)


def test_scanner_registers_components_and_factories(temp_pkg):
    pkg_name, _ = temp_pkg
    c = PicoContainer()

    scan_and_configure(pkg_name, c, exclude=None, plugins=())

    # A is bound by CLASS (since no custom name was provided)
    # B is bound by NAME (custom name), and it is lazy.
    import importlib
    services = importlib.import_module(f"{pkg_name}.services")
    A = getattr(services, "A")

    assert c.has(A)
    assert c.has("B_lazy")

    # Factory-provided keys exist
    assert c.has("svc_sync")
    assert c.has("svc_lazy")

    # svc_sync resolves A by type-hint
    svc_sync = c.get("svc_sync")
    assert svc_sync == ("svc_sync", "A")

    # svc_lazy is lazy; provider executes on-demand and resolves A by type-hint
    out = c.get("svc_lazy")
    assert isinstance(out, dict) and out["kind"] == "lazy_svc" and out["a"] == "A"

    # B_lazy depends on A; retrieving it should resolve the dependency correctly
    b = c.get("B_lazy")
    assert getattr(b, "a").tag == "A"


def test_exclude_skips_modules(temp_pkg):
    pkg_name, _ = temp_pkg
    c = PicoContainer()

    def exclude(mod: str) -> bool:
        return mod.endswith(".skipped")

    scan_and_configure(pkg_name, c, exclude=exclude, plugins=())

    assert not c.has("ShouldNotAppear")
    # Presence of at least one known key validates the rest scanned fine
    import importlib
    A = getattr(importlib.import_module(f"{pkg_name}.services"), "A")
    assert c.has(A)


def test_plugin_hooks_before_visit_after_are_called(temp_pkg):
    pkg_name, _ = temp_pkg
    c = PicoContainer()

    calls = []

    class DummyPlugin:
        def before_scan(self, package, binder):
            calls.append(("before", package.__name__))
        def visit_class(self, module, cls, binder):
            if module.__name__.startswith(pkg_name):
                calls.append(("visit", module.__name__, cls.__name__))
        def after_scan(self, package, binder):
            calls.append(("after", package.__name__))

    scan_and_configure(pkg_name, c, exclude=None, plugins=(DummyPlugin(),))

    names = [t[0] for t in calls]
    assert "before" in names
    assert "after" in names
    assert any(t[0] == "visit" and t[1].startswith(pkg_name) for t in calls)


def test_broken_module_logs_warning(temp_pkg, caplog):
    pkg_name, _ = temp_pkg
    c = PicoContainer()
    caplog.set_level(logging.WARNING)

    scan_and_configure(pkg_name, c, exclude=None, plugins=())

    msgs = [rec.message for rec in caplog.records if rec.levelno >= logging.WARNING]
    assert any("Module pkgx.broken not processed" in m and "boom" in m for m in msgs)


def test_factory_error_is_logged_and_does_not_break_scan(tmp_path, monkeypatch, caplog):
    """
    Create a package with a factory whose construction fails to ensure
    the scanner logs and continues.
    """
    base = tmp_path / "pkgf"
    base.mkdir()
    (base / "__init__.py").write_text("", encoding="utf-8")
    (base / "mod.py").write_text(textwrap.dedent("""
        from pico_ioc.decorators import component, factory_component, provides

        @component(name="Root", lazy=False)
        class Root:
            pass

        @factory_component
        class BadFactory:
            def __init__(self):
                raise RuntimeError("factory ctor failed")

            @provides("X")
            def make(self):
                return object()
    """).strip(), encoding="utf-8")

    monkeypatch.syspath_prepend(str(tmp_path))
    caplog.set_level(logging.ERROR)

    c = PicoContainer()
    scan_and_configure("pkgf", c, exclude=None, plugins=())

    msgs = [rec.message for rec in caplog.records if rec.levelno >= logging.ERROR]
    assert any("Error in factory BadFactory" in m for m in msgs)

    assert c.has("Root")
    assert not c.has("X")

