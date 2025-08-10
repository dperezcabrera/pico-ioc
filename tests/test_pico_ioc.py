import pytest
import sys
import logging
import pico_ioc

# --- Test Environment Setup Fixture ---

@pytest.fixture
def test_project(tmp_path):
    """
    Creates a fake project in a temporary directory so the pico_ioc scanner
    can find components/factories via import.
    """
    project_root = tmp_path / "test_project"
    project_root.mkdir()

    # Make the temp root importable
    sys.path.insert(0, str(tmp_path))

    # Turn 'test_project' into a real package
    (project_root / "__init__.py").touch()

    # Create the package 'services'
    package_dir = project_root / "services"
    package_dir.mkdir()
    (package_dir / "__init__.py").touch()

    # Components
    (package_dir / "components.py").write_text(
        """
from pico_ioc import component

class BaseInterface: ...
class SubInterface(BaseInterface): ...

@component
class SimpleService:
    def get_id(self):
        return id(self)

@component
class AnotherService:
    def __init__(self, simple_service: SimpleService):
        self.child = simple_service

@component(name="custom_name_service")
class CustomNameService:
    pass

@component
class NeedsByName:
    def __init__(self, fast_model):
        self.model = fast_model

@component
class NeedsNameVsType:
    def __init__(self, fast_model: BaseInterface):
        self.model = fast_model

@component
class NeedsTypeFallback:
    def __init__(self, impl: SubInterface):
        self.impl = impl

@component(lazy=True)
class MissingDep:
    def __init__(self, missing):
        self.missing = missing
"""
    )

    # Factories
    (package_dir / "factories.py").write_text(
        """
from pico_ioc import factory_component, provides
from .components import BaseInterface

CREATION_COUNTER = {"value": 0}
FAST_COUNTER = {"value": 0}
BASE_COUNTER = {"value": 0}

@factory_component
class ServiceFactory:
    @provides(key="complex_service", lazy=True)
    def create_complex_service(self):
        CREATION_COUNTER["value"] += 1
        return "This is a complex service"

    @provides(key="fast_model")  # eager by default; instantiated once
    def create_fast_model(self):
        FAST_COUNTER["value"] += 1
        return {"who": "fast"}

    @provides(key=BaseInterface, lazy=True)  # only when requested via MRO
    def create_base_interface(self):
        BASE_COUNTER["value"] += 1
        return {"who": "base"}
"""
    )

    # Module that triggers re-entrant access: init() + get() at import-time
    (project_root / "entry.py").write_text(
        """
import pico_ioc
import test_project
from test_project.services.components import SimpleService

ioc = pico_ioc.init(test_project)
ioc.get(SimpleService)  # should raise during scan; import is caught/logged by scanner
"""
    )

    # Yield root package name used by pico_ioc.init()
    yield "test_project"

    # Teardown
    sys.path.pop(0)
    pico_ioc._container = None
    mods_to_del = [m for m in list(sys.modules.keys()) if m == "test_project" or m.startswith("test_project.")]
    for m in mods_to_del:
        sys.modules.pop(m, None)


# --- Core behavior tests ---

def test_simple_component_retrieval(test_project):
    from test_project.services.components import SimpleService
    container = pico_ioc.init(test_project)
    service = container.get(SimpleService)
    assert service is not None
    assert isinstance(service, SimpleService)


def test_dependency_injection_by_type_hint(test_project):
    from test_project.services.components import SimpleService, AnotherService
    container = pico_ioc.init(test_project)
    another = container.get(AnotherService)
    assert another is not None
    assert isinstance(another.child, SimpleService)


def test_components_are_singletons_by_default(test_project):
    from test_project.services.components import SimpleService
    container = pico_ioc.init(test_project)
    s1 = container.get(SimpleService)
    s2 = container.get(SimpleService)
    assert s1 is s2
    assert s1.get_id() == s2.get_id()


def test_get_unregistered_component_raises_error(test_project):
    container = pico_ioc.init(test_project)
    class Unregistered: ...
    with pytest.raises(NameError, match="No provider found for key"):
        container.get(Unregistered)


def test_factory_provides_component_by_name(test_project):
    container = pico_ioc.init(test_project)
    svc = container.get("complex_service")
    assert svc == "This is a complex service"


def test_factory_instantiation_is_lazy_and_singleton(test_project):
    from test_project.services.factories import CREATION_COUNTER
    container = pico_ioc.init(test_project)
    assert CREATION_COUNTER["value"] == 0
    proxy = container.get("complex_service")
    assert CREATION_COUNTER["value"] == 0
    up = proxy.upper()
    assert up == "THIS IS A COMPLEX SERVICE"
    assert CREATION_COUNTER["value"] == 1
    _ = proxy.lower()
    assert CREATION_COUNTER["value"] == 1
    again = container.get("complex_service")
    assert again is proxy
    _ = again.strip()
    assert CREATION_COUNTER["value"] == 1


def test_component_with_custom_name(test_project):
    from test_project.services.components import CustomNameService
    container = pico_ioc.init(test_project)
    svc = container.get("custom_name_service")
    assert isinstance(svc, CustomNameService)
    with pytest.raises(NameError):
        container.get(CustomNameService)


def test_resolution_prefers_name_over_type(test_project):
    from test_project.services.components import NeedsNameVsType
    from test_project.services.factories import FAST_COUNTER, BASE_COUNTER
    container = pico_ioc.init(test_project)
    comp = container.get(NeedsNameVsType)
    assert comp.model == {"who": "fast"}
    assert FAST_COUNTER["value"] == 1  # created once by factory
    assert BASE_COUNTER["value"] == 0  # still lazy


def test_resolution_by_name_only(test_project):
    from test_project.services.components import NeedsByName
    from test_project.services.factories import FAST_COUNTER
    container = pico_ioc.init(test_project)
    comp = container.get(NeedsByName)
    assert comp.model == {"who": "fast"}
    assert FAST_COUNTER["value"] == 1  # reused singleton


def test_resolution_fallback_to_type_mro(test_project):
    from test_project.services.components import NeedsTypeFallback
    from test_project.services.factories import BASE_COUNTER
    container = pico_ioc.init(test_project)
    comp = container.get(NeedsTypeFallback)
    assert comp.impl == {"who": "base"}
    assert BASE_COUNTER["value"] == 1  # created on demand via MRO


def test_missing_dependency_raises_clear_error(test_project):
    from test_project.services.components import MissingDep
    container = pico_ioc.init(test_project)
    proxy = container.get(MissingDep)  # returns ComponentProxy
    with pytest.raises(NameError, match="No provider found for key"):
        _ = bool(proxy)


def test_reentrant_access_is_blocked_and_container_still_initializes(test_project, caplog):
    caplog.set_level(logging.INFO)
    container = pico_ioc.init(test_project)
    # The scanner logs a warning including the RuntimeError text thrown by get()
    assert any(
        "re-entrant container access during scan" in rec.message
        for rec in caplog.records
    ), "Expected a warning about re-entrant access during scan"
    from test_project.services.components import SimpleService
    svc = container.get(SimpleService)
    assert isinstance(svc, SimpleService)


# --- Plugin & Binder smoke test ---

def test_plugin_hooks_and_binder(test_project):
    """
    Verifies that a plugin can observe classes during scan, bind a value via Binder,
    and see lifecycle hooks firing in order.
    """
    calls = []

    class MyPlugin:
        def before_scan(self, package, binder):
            calls.append("before_scan")

        def visit_class(self, module, cls, binder):
            # As an example, bind a marker when we see a specific class name
            if cls.__name__ == "SimpleService" and not binder.has("marker"):
                binder.bind("marker", lambda: {"ok": True}, lazy=False)

        def after_scan(self, package, binder):
            calls.append("after_scan")

        def after_bind(self, container, binder):
            calls.append("after_bind")

        def before_eager(self, container, binder):
            calls.append("before_eager")

        def after_ready(self, container, binder):
            calls.append("after_ready")

    container = pico_ioc.init(test_project, plugins=(MyPlugin(),))

    # Order is not strictly enforced between middle hooks, but all should be present.
    for expected in ["before_scan", "after_scan", "after_bind", "before_eager", "after_ready"]:
        assert expected in calls

    # Marker bound by plugin should be retrievable
    assert container.get("marker") == {"ok": True}

