# pico_ioc/interceptors.py
from __future__ import annotations
from typing import Any, Callable, Protocol, Sequence
import inspect

class Invocation:
    __slots__ = ("target", "method_name", "call", "args", "kwargs", "is_async")

    def __init__(self, target: object, method_name: str, call: Callable[..., Any],
                 args: tuple, kwargs: dict):
        self.target = target
        self.method_name = method_name
        self.call = call
        self.args = args
        self.kwargs = kwargs
        self.is_async = inspect.iscoroutinefunction(call)

class MethodInterceptor(Protocol):
    def __call__(self, inv: Invocation, proceed: Callable[[], Any]) -> Any: ...

async def _chain_async(interceptors: Sequence[MethodInterceptor], inv: Invocation, i: int = 0):
    if i >= len(interceptors):
        return await inv.call(*inv.args, **inv.kwargs)
    cur = interceptors[i]
    async def next_step():
        return await _chain_async(interceptors, inv, i + 1)
    res = cur(inv, next_step)
    return await res if inspect.isawaitable(res) else res

def _chain_sync(interceptors: Sequence[MethodInterceptor], inv: Invocation, i: int = 0):
    if i >= len(interceptors):
        return inv.call(*inv.args, **inv.kwargs)
    cur = interceptors[i]
    return cur(inv, lambda: _chain_sync(interceptors, inv, i + 1))

def dispatch(interceptors: Sequence[MethodInterceptor], inv: Invocation):
    if inv.is_async:
        # return a coroutine that the caller will await
        return _chain_async(interceptors, inv, 0)
    # return the final value directly for sync methods
    res = _chain_sync(interceptors, inv, 0)
    return res


class ContainerInterceptor(Protocol):
    def on_resolve(self, key: Any, annotation: Any, qualifiers: tuple[str, ...] | tuple()) -> None: ...
    def on_before_create(self, key: Any) -> None: ...
    def on_after_create(self, key: Any, instance: Any) -> Any: ...
    def on_exception(self, key: Any, exc: BaseException) -> None: ...

