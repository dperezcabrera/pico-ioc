import pytest
import sys
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

    # Components:
    # - SimpleService                          (no deps)
    # - AnotherService                         (depends on SimpleService by type)
    # - CustomNameService                      (registered by custom name)
    # - NeedsByName                            (depends by name only)
    # - NeedsNameVsType                        (name should win over type)
    # - NeedsTypeFallback                      (fallback to base type via MRO)
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

    # Factories:
    # - complex_service (lazy via LazyProxy; counter to assert laziness)
    # - fast_model      (by NAME)
    # - base_interface  (by TYPE: BaseInterface)
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
        return {"who": "fast"}  # any object; dict is convenient for identity checks

    @provides(key=BaseInterface)
    def create_base_interface(self):
        BASE_COUNTER["value"] += 1
        return {"who": "base"}
"""
    )

    # Optional module that calls init() at import-time:
    # used to test auto-exclude of the caller (to prevent re-entrancy).
    (project_root / "entry.py").write_text(
        """
import pico_ioc
import test_project

# If auto-exclude-caller is on AND _scan_and_configure() honors 'exclude',
# importing this module during scanning should NOT recurse infinitely.
ioc = pico_ioc.init(test_project)
"""
    )

    # Yield the root package name used by pico_ioc.init()
    yield "test_project"

    # Teardown: remove path, reset container, purge modules from cache
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
    """
    When a constructor parameter has a type hint and no provider is bound by name,
    the container should resolve it by TYPE.
    """
    from test_project.services.components import SimpleService, AnotherService

    container = pico_ioc.init(test_project)
    another = container.get(AnotherService)

    assert another is not None
    assert isinstance(another.child, SimpleService)


def test_components_are_singletons_by_default(test_project):
    """
    Providers bound by the scanner are singletons: get() returns the same instance.
    """
    from test_project.services.components import SimpleService

    container = pico_ioc.init(test_project)
    s1 = container.get(SimpleService)
    s2 = container.get(SimpleService)

    assert s1 is s2
    assert s1.get_id() == s2.get_id()


def test_get_unregistered_component_raises_error(test_project):
    """
    Requesting a key with no provider must raise NameError with a helpful message.
    """
    container = pico_ioc.init(test_project)

    class Unregistered: ...
    with pytest.raises(NameError, match="No provider found for key"):
        container.get(Unregistered)


def test_factory_provides_component_by_name(test_project):
    """
    A factory method annotated with @provides(key="...") is bound by NAME and is retrievable.
    """
    container = pico_ioc.init(test_project)
    svc = container.get("complex_service")

    # Proxy must behave like the real string for equality
    assert svc == "This is a complex service"


def test_factory_instantiation_is_lazy_and_singleton(test_project):
    """
    Factory methods with default lazy=True return a LazyProxy. The real object is created on first use.
    Also, container should cache the created instance (singleton per key).
    """
    from test_project.services.factories import CREATION_COUNTER

    container = pico_ioc.init(test_project)

    assert CREATION_COUNTER["value"] == 0

    proxy = container.get("complex_service")
    # Accessing attributes/methods of the proxy should trigger creation exactly once
    assert CREATION_COUNTER["value"] == 0
    up = proxy.upper()
    assert up == "THIS IS A COMPLEX SERVICE"
    assert CREATION_COUNTER["value"] == 1

    # Re-accessing via the same proxy does not create again
    _ = proxy.lower()
    assert CREATION_COUNTER["value"] == 1

    # Getting the same key again should return the same singleton instance (no extra creations)
    again = container.get("complex_service")
    assert again is proxy  # same object returned by container
    _ = again.strip()
    assert CREATION_COUNTER["value"] == 1


def test_component_with_custom_name(test_project):
    """
    A component registered by custom name is retrievable by that name,
    and NOT by its class.
    """
    from test_project.services.components import CustomNameService

    container = pico_ioc.init(test_project)
    svc = container.get("custom_name_service")
    assert isinstance(svc, CustomNameService)

    with pytest.raises(NameError):
        container.get(CustomNameService)


def test_resolution_prefers_name_over_type(test_project):
    """
    If both a NAME-bound provider and a TYPE-bound provider exist, resolution MUST
    prefer the NAME (parameter name) over the TYPE hint.
    """
    from test_project.services.components import NeedsNameVsType
    from test_project.services.factories import FAST_COUNTER, BASE_COUNTER

    container = pico_ioc.init(test_project)
    comp = container.get(NeedsNameVsType)

    # "fast_model" name must win → uses the fast provider
    assert comp.model == {"who": "fast"}
    assert FAST_COUNTER["value"] == 1
    # Base provider should NOT be used for this resolution
    assert BASE_COUNTER["value"] == 0


def test_resolution_by_name_only(test_project):
    """
    When a ctor parameter has NO type hint, the container must resolve strictly by NAME.
    """
    from test_project.services.components import NeedsByName
    from test_project.services.factories import FAST_COUNTER

    container = pico_ioc.init(test_project)
    comp = container.get(NeedsByName)

    assert comp.model == {"who": "fast"}
    assert FAST_COUNTER["value"] == 1


def test_resolution_fallback_to_type_mro(test_project):
    """
    When there is no provider for the parameter NAME nor the exact TYPE,
    the container must try TYPE's MRO and use the first available provider.
    """
    from test_project.services.components import NeedsTypeFallback
    from test_project.services.factories import BASE_COUNTER

    container = pico_ioc.init(test_project)
    comp = container.get(NeedsTypeFallback)

    # Resolved via MRO to BaseInterface provider
    assert comp.impl == {"who": "base"}
    assert BASE_COUNTER["value"] == 1


def test_missing_dependency_raises_clear_error(test_project):
    """
    If no provider exists for NAME nor TYPE nor MRO, resolution must raise NameError.
    """
    from test_project.services.components import MissingDep

    container = pico_ioc.init(test_project)
    with pytest.raises(NameError, match="No provider found for key"):
        container.get(MissingDep)


@pytest.mark.skipif(
    not hasattr(pico_ioc, "init"),
    reason="init not available"
)
def test_auto_exclude_caller_prevents_reentrant_scan(test_project):
    """
    Smoke test: importing a module that calls pico_ioc.init(root) at import-time
    should not cause re-entrant scans if init() auto-excludes the caller AND
    _scan_and_configure honors the 'exclude' predicate.
    """
    # If the library correctly auto-excludes the caller and passes 'exclude'
    # into the scanner (which must skip excluded modules), this import should be safe.
    __import__("test_project.entry")

