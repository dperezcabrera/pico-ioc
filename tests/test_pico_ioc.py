# tests/test_pico_ioc.py

import pytest
import sys
import pico_ioc

# --- Test Environment Setup Fixture ---

@pytest.fixture
def test_project(tmp_path):
    """
    Creates a fake project structure in a temporary directory
    so that the pico_ioc scanner can find the components.
    """
    project_root = tmp_path / "test_project"
    project_root.mkdir()
    
    # Add the root directory to the Python path so modules can be imported
    sys.path.insert(0, str(tmp_path))

    # >>> THE LINE THAT FIXES THE PROBLEM <<<
    # Turn 'test_project' into a regular package.
    (project_root / "__init__.py").touch()

    # Create the package and modules with test components
    package_dir = project_root / "services"
    package_dir.mkdir()
    
    # __init__.py file to turn 'services' into a sub-package
    (package_dir / "__init__.py").touch()

    # Module with simple components and components with dependencies
    (package_dir / "components.py").write_text("""
from pico_ioc import component

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
""")

    # Module with a component factory
    (package_dir / "factories.py").write_text("""
from pico_ioc import factory_component, provides

# To test that instantiation is lazy
CREATION_COUNTER = {"value": 0}

@factory_component
class ServiceFactory:
    @provides(name="complex_service")
    def create_complex_service(self):
        CREATION_COUNTER["value"] += 1
        return "This is a complex service"
""")
    
    # Return the root package name for init() to use
    yield "test_project"
    
    sys.path.pop(0)

    # Reset the global pico_ioc container to isolate tests.
    pico_ioc._container = None

    # Purge the temporary package from the module cache so each test starts
    # with a fresh module state (e.g., CREATION_COUNTER resets to 0).
    mods_to_del = [
        m for m in list(sys.modules.keys())
        if m == "test_project" or m.startswith("test_project.")
    ]
    for m in mods_to_del:
        sys.modules.pop(m, None)


# --- Test Suite ---

def test_simple_component_retrieval(test_project):
    """Verifies that a simple component can be registered and retrieved."""
    # Import the TEST classes after the fixture has created them
    from test_project.services.components import SimpleService
    
    container = pico_ioc.init(test_project)
    service = container.get(SimpleService)
    
    assert service is not None
    assert isinstance(service, SimpleService)

def test_dependency_injection(test_project):
    """Verifies that a dependency is correctly injected into another component."""
    from test_project.services.components import SimpleService, AnotherService

    container = pico_ioc.init(test_project)
    another_service = container.get(AnotherService)

    assert another_service is not None
    assert hasattr(another_service, "child")
    assert isinstance(another_service.child, SimpleService)

def test_components_are_singletons_by_default(test_project):
    """Verifies that get() always returns the same instance for a component."""
    from test_project.services.components import SimpleService

    container = pico_ioc.init(test_project)
    service1 = container.get(SimpleService)
    service2 = container.get(SimpleService)

    assert service1 is service2
    assert service1.get_id() == service2.get_id()

def test_get_unregistered_component_raises_error(test_project):
    """Verifies that requesting an unregistered component raises a NameError."""
    container = pico_ioc.init(test_project)
    
    class UnregisteredClass:
        pass

    with pytest.raises(NameError, match="No provider found for key"):
        container.get(UnregisteredClass)

def test_factory_provides_component(test_project):
    """Verifies that a component created by a factory can be retrieved."""
    container = pico_ioc.init(test_project)
    
    service = container.get("complex_service")
    
    # The object is a proxy, but it should delegate the comparison
    assert service == "This is a complex service"

def test_factory_instantiation_is_lazy(test_project):
    """
    Verifies that a factory's @provides method is only executed
    when the object is first accessed.
    """
    # Import the counter from the test factory
    from test_project.services.factories import CREATION_COUNTER
    
    container = pico_ioc.init(test_project)
    
    # Initially, the counter must be 0 because nothing has been created yet
    assert CREATION_COUNTER["value"] == 0
    
    # We get the proxy, but this should NOT trigger the creation
    service_proxy = container.get("complex_service")
    assert CREATION_COUNTER["value"] == 0
    
    # Now we access an attribute of the real object (through the proxy)
    # This SHOULD trigger the creation
    result = service_proxy.upper() # .upper() is called on the real string
    
    assert CREATION_COUNTER["value"] == 1
    assert result == "THIS IS A COMPLEX SERVICE"
    
    # If we access it again, the counter should not increment
    _ = service_proxy.lower()
    assert CREATION_COUNTER["value"] == 1

def test_component_with_custom_name(test_project):
    """Verifies that a component with a custom name can be registered and retrieved."""
    from test_project.services.components import CustomNameService
    
    container = pico_ioc.init(test_project)
    
    # We get the service using its custom name
    service = container.get("custom_name_service")
    assert isinstance(service, CustomNameService)
    
    # Verify that requesting it by its class fails, as it was registered by name
    with pytest.raises(NameError):
        container.get(CustomNameService)
