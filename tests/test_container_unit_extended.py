# tests/test_container_unit_extended.py
import pytest

from pico_ioc.container import PicoContainer
from pico_ioc.interceptors import MethodInterceptor, ContainerInterceptor
from pico_ioc.proxy import IoCProxy

# --- Test Helpers ---

class NoArgInterceptor(MethodInterceptor):
    def __init__(self):
        self.invoked = False
    
    def __call__(self, inv, proceed):
        self.invoked = True
        return proceed()

class MyService:
    def do_work(self):
        return "done"

class ExceptionInterceptor(ContainerInterceptor):
    def __init__(self):
        self.caught = []
    
    def on_exception(self, key: any, exc: BaseException) -> None:
        self.caught.append((key, exc))

class ReplaceInterceptor(ContainerInterceptor):
    def on_after_create(self, key: any, instance: any) -> any:
        if isinstance(instance, MyService):
            return "replaced"
        return instance

# --- Tests ---

def test_build_interceptors_with_no_arg_constructor():
    container = PicoContainer(method_interceptors=[NoArgInterceptor])
    

    assert len(container._method_interceptors) == 1
    interceptor_instance = container._method_interceptors[0]
    assert isinstance(interceptor_instance, NoArgInterceptor)

    container.bind(MyService, MyService, lazy=False)
    service_proxy = container.get(MyService)
    
    assert isinstance(service_proxy, IoCProxy)
    assert interceptor_instance.invoked is False
    
    result = service_proxy.do_work()
    assert result == "done"
    assert interceptor_instance.invoked is True


def test_container_interceptor_on_exception_hook():
    def failing_provider():
        raise ValueError("Creation failed")

    interceptor = ExceptionInterceptor()
    container = PicoContainer(container_interceptors=[interceptor])
    container.bind("failing_key", failing_provider, lazy=False)

    with pytest.raises(ValueError, match="Creation failed"):
        container.get("failing_key")

    assert len(interceptor.caught) == 1
    key, exc = interceptor.caught[0]
    assert key == "failing_key"
    assert isinstance(exc, ValueError)
    assert str(exc) == "Creation failed"

def test_container_interceptor_replaces_instance_with_on_after_create():
    interceptor = ReplaceInterceptor()
    container = PicoContainer(container_interceptors=[interceptor])
    container.bind(MyService, MyService, lazy=False)

    instance = container.get(MyService)
    assert instance == "replaced"

    instance2 = container.get(MyService)
    assert instance2 == "replaced"
