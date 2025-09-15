# tests/test_proxy_and_interceptors.py
import pytest
import asyncio
import types

from pico_ioc import init, component, interceptor
from pico_ioc.interceptors import MethodInterceptor


async def async_proceed():
    await asyncio.sleep(0)
    return "async_result"


@interceptor
class AsyncOnlyInterceptor(MethodInterceptor):
    def __call__(self, inv, proceed):
        # Always returns an awaitable even for sync methods
        return async_proceed()


@component
class MySyncService:
    def do_work(self):
        return "sync_result"


@pytest.mark.filterwarnings("ignore:coroutine .* was never awaited")
def test_iocproxy_raises_error_on_async_interceptor_with_sync_method():
    # Package to scan must contain both the component and the interceptor
    pkg = types.ModuleType("pkg_proxy_err")
    pkg.MySyncService = MySyncService
    pkg.AsyncOnlyInterceptor = AsyncOnlyInterceptor

    container = init(pkg)
    svc = container.get(MySyncService)

    with pytest.raises(RuntimeError, match=r"Async interceptor on sync method: do_work"):
        svc.do_work()

