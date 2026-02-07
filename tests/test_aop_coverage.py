import inspect
import pickle
import threading

import pytest

from pico_ioc.aop import (
    MethodCtx,
    MethodInterceptor,
    UnifiedComponentProxy,
    _gather_interceptors_for_method,
    intercepted_by,
)
from pico_ioc.exceptions import AsyncResolutionError, SerializationError


def test_intercepted_by_validation():
    with pytest.raises(TypeError, match="requires at least one"):
        intercepted_by()

    with pytest.raises(TypeError, match="expects interceptor classes"):
        intercepted_by("not_a_class")

    decorator = intercepted_by(MethodInterceptor)
    with pytest.raises(TypeError, match="only decorate callables"):
        decorator("not_callable")


def test_proxy_init_validation():
    with pytest.raises(ValueError, match="non-null container"):
        UnifiedComponentProxy(container=None)

    with pytest.raises(ValueError, match="requires either a target"):
        UnifiedComponentProxy(container="stub")


def test_proxy_creator_errors():
    proxy = UnifiedComponentProxy(container="stub", object_creator="not_callable")
    with pytest.raises(TypeError, match="must be callable"):
        getattr(proxy, "any_attr")

    proxy = UnifiedComponentProxy(container="stub", object_creator=lambda: None)
    with pytest.raises(RuntimeError, match="returned None"):
        getattr(proxy, "any_attr")


def test_proxy_async_error_on_sync_access():
    async def async_configure(obj):
        pass

    class ContainerMock:
        def _run_configure_methods(self, obj):
            return async_configure(obj)

    proxy = UnifiedComponentProxy(container=ContainerMock(), object_creator=lambda: "target")

    with pytest.raises(AsyncResolutionError):
        str(proxy)


def test_proxy_serialization_error():
    class Unpicklable:
        def __getstate__(self):
            raise ValueError("No pickle")

    proxy = UnifiedComponentProxy(container="stub", target=Unpicklable())

    with pytest.raises(SerializationError):
        pickle.dumps(proxy)

    with pytest.raises(SerializationError):
        proxy.__setstate__({"data": b"bad_data"})


def test_gather_interceptors_edge_cases():
    assert _gather_interceptors_for_method(str, "non_existent") == ()
    assert _gather_interceptors_for_method(list, "append") == ()
