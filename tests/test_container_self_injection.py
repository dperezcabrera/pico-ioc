import pytest

from pico_ioc import InvalidBindingError, PicoContainer, component, init


@component
class ServiceNeedsContainer:
    def __init__(self, container: PicoContainer):
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
