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
        # Will resolve by TYPE because there is no provider bound by the name "simple_service"
        self.child = simple_service

@component(name="custom_name_service")
class CustomNameService:
    pass

@component
class NeedsByName:
    def __init__(self, fast_model):
        # Will resolve by NAME, since there will be a provider bound to "fast_model"
        self.model = fast_model

@component
class NeedsNameVsType:
    def __init__(self, fast_model: BaseInterface):
        # There will be providers for BOTH the name "fast_model" and the base type.
        # NAME must win over TYPE.
        self.model = fast_model

@component
class NeedsTypeFallback:
    def __init__(self, impl: SubInterface):
        # There will NOT be a provider for the name "impl" nor for SubInterface directly,
        # but there will be one for BaseInterface → must fallback via MRO.
        self.impl = impl

@component
class MissingDep:
    def __init__(self, missing):
        # No provider by name nor type: must raise on resolution.
        self.missing = missing
"""
    )

    # Factories
    (package_dir / "factories.py").write_text(
        """
from pico_ioc import factory_component, provides
from .components import BaseInterface

# Used to assert lazy instantiation
CREATION_COUNTER = {"value": 0}
FAST_COUNTER = {"value": 0}
BASE_COUNTER = {"value": 0}

@factory_component
class ServiceFactory:
    @provides(key="complex_service")
    def create_complex_service(self):
        # Increment ONLY when the real object is created (not when proxy is returned)
        CREATION_COUNTER["value"] += 1
        return "This is a complex service"

    @provides(key="fast_model")
    def create_fast_model(self):
        FAST_COUNTER["value"] += 1
        return {"who": "fast"}

    @provides(key=BaseInterface)
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

# This runs at import-time when the scanner imports this module.
# init() returns the (global) container set by the outer scan,
# then get() is attempted while scanning is still in progress -> guard should raise.
ioc = pico_ioc.init(test_project)
ioc.get(SimpleService)  # should raise RuntimeError due to re-entrant access during scan
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


# --- Test Suite ---

def test_simple_component_retrieval(test_project):
    """A plain component registered by class can be retrieved by its class key."""
    from test_project.services.components import SimpleService

    container = pico_ioc.init(test_project)
    service = container.get(SimpleService)

    assert service is not None
    assert isinstance(service, SimpleService)


def test_dependency_injection_by_type_hint(test_project):
    """Type-hinted dependency resolves by TYPE when no NAME-bound provider exists."""
    from test_project.services.components import SimpleService, AnotherService

    container = pico_ioc.init(test_project)
    another = container.get(AnotherService)

    assert another is not None
    assert isinstance(another.child, SimpleService)


def test_components_are_singletons_by_default(test_project):
    """Providers registered by the scanner behave as singletons."""
    from test_project.services.components import SimpleService

    container = pico_ioc.init(test_project)
    s1 = container.get(SimpleService)
    s2 = container.get(SimpleService)

    assert s1 is s2
    assert s1.get_id() == s2.get_id()


def test_get_unregistered_component_raises_error(test_project):
    """Requesting an unknown key raises NameError."""
    container = pico_ioc.init(test_project)

    class Unregistered: ...
    with pytest.raises(NameError, match="No provider found for key"):
        container.get(Unregistered)


def test_factory_provides_component_by_name(test_project):
    """Factory-provided component is retrievable by key; proxy behaves like real value."""
    container = pico_ioc.init(test_project)
    svc = container.get("complex_service")
    assert svc == "This is a complex service"


def test_factory_instantiation_is_lazy_and_singleton(test_project):
    """LazyProxy creates real object on first use and remains singleton per key."""
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
    """Component registered by custom name is retrievable by that name, not by class."""
    from test_project.services.components import CustomNameService

    container = pico_ioc.init(test_project)
    svc = container.get("custom_name_service")
    assert isinstance(svc, CustomNameService)

    with pytest.raises(NameError):
        container.get(CustomNameService)


def test_resolution_prefers_name_over_type(test_project):
    """If NAME and TYPE providers exist, NAME must win."""
    from test_project.services.components import NeedsNameVsType
    from test_project.services.factories import FAST_COUNTER, BASE_COUNTER

    container = pico_ioc.init(test_project)
    comp = container.get(NeedsNameVsType)

    assert comp.model == {"who": "fast"}
    assert FAST_COUNTER["value"] == 1
    assert BASE_COUNTER["value"] == 0


def test_resolution_by_name_only(test_project):
    """Ctor param without type hint resolves strictly by NAME."""
    from test_project.services.components import NeedsByName
    from test_project.services.factories import FAST_COUNTER

    container = pico_ioc.init(test_project)
    comp = container.get(NeedsByName)

    assert comp.model == {"who": "fast"}
    assert FAST_COUNTER["value"] == 1


def test_resolution_fallback_to_type_mro(test_project):
    """If neither NAME nor exact TYPE match, fallback via TYPE MRO."""
    from test_project.services.components import NeedsTypeFallback
    from test_project.services.factories import BASE_COUNTER

    container = pico_ioc.init(test_project)
    comp = container.get(NeedsTypeFallback)

    assert comp.impl == {"who": "base"}
    assert BASE_COUNTER["value"] == 1


def test_missing_dependency_raises_clear_error(test_project):
    """Missing dep across NAME/TYPE/MRO raises NameError."""
    from test_project.services.components import MissingDep

    container = pico_ioc.init(test_project)
    with pytest.raises(NameError, match="No provider found for key"):
        container.get(MissingDep)


def test_reentrant_access_is_blocked_and_container_still_initializes(test_project, caplog):
    """
    Importing a module that calls init() and then container.get() at import-time should:
      - raise a RuntimeError from the guard (caught as a warning by the scanner),
      - NOT prevent the container from finishing initialization,
      - allow normal component retrieval afterwards.
    """
    caplog.set_level(logging.INFO)

    container = pico_ioc.init(test_project)

    assert any(
        "re-entrant container access during scan" in rec.message
        for rec in caplog.records
    ), "Expected a warning about re-entrant access during scan"

    from test_project.services.components import SimpleService
    svc = container.get(SimpleService)
    assert isinstance(svc, SimpleService)

