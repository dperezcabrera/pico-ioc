# tests/test_proxy_and_interceptors.py
import pytest
import asyncio

from pico_ioc import init, component
from pico_ioc.interceptors import MethodInterceptor


async def async_proceed():
    # A helper that simulates an async operation.
    await asyncio.sleep(0)
    return "async_result"


class AsyncOnlyInterceptor(MethodInterceptor):
    def __call__(self, inv, proceed):
        # This interceptor incorrectly returns an awaitable.
        return async_proceed()


@component
class MySyncService:
    def do_work(self):
        return "sync_result"


# Add a marker to ignore the expected warning for this specific test.
@pytest.mark.filterwarnings("ignore:coroutine .* was never awaited")
def test_iocproxy_raises_error_on_async_interceptor_with_sync_method():
    # Verifies a RuntimeError is raised for async/sync mismatch in interceptors.
    import types

    pkg = types.ModuleType("pkg_proxy_err")
    pkg.MySyncService = MySyncService

    # Use init() to ensure the full container setup is tested.
    container = init(pkg, method_interceptors=[AsyncOnlyInterceptor()])

    service_instance = container.get(MySyncService)

    with pytest.raises(RuntimeError, match="Async interceptor on sync method: do_work"):
        service_instance.do_work()
