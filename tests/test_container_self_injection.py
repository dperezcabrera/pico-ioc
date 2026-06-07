import pytest

from pico_ioc import InvalidBindingError, PicoContainer, component, init


@component
class ServiceNeedsContainer:
    def __init__(self, container: PicoContainer):
        self.container = container


@component
class Dependency:
    value = 7


@component
class ServiceNeedsOptionalPep604:
    """Optional deps written with PEP 604 ``T | None`` must still be injected
    when a provider exists (regression: on Python 3.11-3.13 ``get_origin``
    returns ``types.UnionType`` rather than ``typing.Union``, so the unwrap
    was skipped and the dep silently resolved to its ``None`` default)."""

    def __init__(self, dep: Dependency | None = None, container: PicoContainer | None = None):
        self.dep = dep
        self.container = container


class TestContainerSelfInjection:
    def test_container_is_injectable(self):
        try:
            container = init(modules=[__name__])
        except InvalidBindingError as e:
            pytest.fail(f"init() failed validation: {e}")

        assert container is not None
        service = container.get(ServiceNeedsContainer)
        assert service is not None
        assert isinstance(service.container, PicoContainer)

    def test_injected_container_is_self(self):
        container = init(modules=[__name__])

        service = container.get(ServiceNeedsContainer)

        assert service.container is container

    def test_pep604_optional_dependency_is_injected(self):
        container = init(modules=[__name__])

        service = container.get(ServiceNeedsOptionalPep604)

        assert service.dep is not None, "'Dependency | None' must be injected, not left as None"
        assert service.dep.value == 7
        assert service.container is container, "'PicoContainer | None' must inject the container"
