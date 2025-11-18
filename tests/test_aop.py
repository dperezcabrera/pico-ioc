import pytest
import inspect
from typing import List, Any, Callable

from pico_ioc import init, component
from pico_ioc.aop import MethodInterceptor, MethodCtx, intercepted_by


class CallLogger:
    def __init__(self):
        self.messages: List[str] = []

    def log(self, msg: str):
        self.messages.append(msg)

    def clear(self):
        self.messages.clear()


@component(scope="singleton")
class LoggingInterceptor(MethodInterceptor):
    def __init__(self, logger: CallLogger):
        self.logger = logger

    def invoke(self, ctx: MethodCtx, call_next: Callable[[MethodCtx], Any]) -> Any:
        self.logger.log(f"Entering method: {ctx.name}")
        
        ctx.kwargs["name"] = ctx.kwargs.get("name", "").upper()

        original_func = ctx.method
        if hasattr(original_func, '__func__'):
            original_func = original_func.__func__
        
        is_async = inspect.iscoroutinefunction(original_func)

        if is_async:
            async def async_wrapper():
                result_coro = call_next(ctx)
                result = await result_coro
                
                modified_result = f"{result} - Intercepted!"
                self.logger.log(f"Exiting method: {ctx.name}")
                return modified_result
            
            return async_wrapper()
        else:
            result = call_next(ctx)
            
            modified_result = f"{result} - Intercepted!"
            self.logger.log(f"Exiting method: {ctx.name}")
            return modified_result


@component
class MyService:
    @intercepted_by(LoggingInterceptor)
    def greet(self, name: str) -> str:
        return f"Hello {name}"

    @intercepted_by(LoggingInterceptor)
    async def async_greet(self, name: str) -> str:
        return f"Async Hello {name}"


@component
class UnrelatedService:
    def greet(self, name: str) -> str:
        return f"Hello {name}"


@pytest.fixture
def container():
    c = init(
        modules=[__name__],
        overrides={
            CallLogger: CallLogger()
        }
    )
    yield c
    c.shutdown()


def test_aop_intercepts_sync_call(container):
    service = container.get(MyService)
    logger = container.get(CallLogger)
    
    result = service.greet(name="World")
    
    assert result == "Hello WORLD - Intercepted!"
    assert logger.messages == [
        "Entering method: greet",
        "Exiting method: greet"
    ]


@pytest.mark.asyncio
async def test_aop_intercepts_async_call(container):
    service = await container.aget(MyService)
    logger = await container.aget(CallLogger)
    
    logger.clear()
    
    result = await service.async_greet(name="AsyncWorld")
    
    assert result == "Async Hello ASYNCWORLD - Intercepted!"
    assert logger.messages == [
        "Entering method: async_greet",
        "Exiting method: async_greet"
    ]


def test_aop_does_not_intercept_unrelated_call(container):
    service = container.get(UnrelatedService)
    logger = container.get(CallLogger)

    logger.clear()
    
    result = service.greet(name="World")
    
    assert result == "Hello World"
    assert logger.messages == []
