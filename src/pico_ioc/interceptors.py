from __future__ import annotations
import inspect
from typing import Any, Callable, Protocol, Sequence

class MethodCtx:
    __slots__ = ("instance", "cls", "method", "name", "args", "kwargs", "container", "tags", "qualifiers", "request_key", "local")
    def __init__(self, *, instance: object, cls: type, method: Callable[..., Any], name: str, args: tuple, kwargs: dict, container: Any, tags: set[str] | None = None, qualifiers: dict[str, Any] | None = None, request_key: Any = None):
        self.instance = instance
        self.cls = cls
        self.method = method
        self.name = name
        self.args = args
        self.kwargs = kwargs
        self.container = container
        self.tags = set(tags or ())
        self.qualifiers = dict(qualifiers or {})
        self.request_key = request_key
        self.local: dict[str, Any] = {}

class ResolveCtx:
    __slots__ = ("key", "qualifiers", "requested_by", "profiles", "local")
    def __init__(self, *, key: Any, qualifiers: dict[str, Any] | None, requested_by: Any, profiles: Sequence[str]):
        self.key = key
        self.qualifiers = dict(qualifiers or {})
        self.requested_by = requested_by
        self.profiles = tuple(profiles or ())
        self.local: dict[str, Any] = {}

class CreateCtx:
    __slots__ = ("key", "component", "provider", "profiles", "local")
    def __init__(self, *, key: Any, component: type | None, provider: Callable[[], object], profiles: Sequence[str]):
        self.key = key
        self.component = component
        self.provider = provider
        self.profiles = tuple(profiles or ())
        self.local: dict[str, Any] = {}

class MethodInterceptor(Protocol):
    def invoke(self, ctx: MethodCtx, call_next: Callable[[MethodCtx], Any]) -> Any: ...

class ContainerInterceptor(Protocol):
    def around_resolve(self, ctx: ResolveCtx, call_next: Callable[[ResolveCtx], Any]) -> Any: ...
    def around_create(self, ctx: CreateCtx, call_next: Callable[[CreateCtx], Any]) -> Any: ...

def _dispatch_method(interceptors: Sequence[MethodInterceptor], ctx: MethodCtx, i: int = 0):
    if i >= len(interceptors):
        return ctx.method(*ctx.args, **ctx.kwargs)
    cur = interceptors[i]
    return cur.invoke(ctx, lambda nxt: _dispatch_method(interceptors, nxt, i + 1))

async def _dispatch_method_async(interceptors: Sequence[MethodInterceptor], ctx: MethodCtx, i: int = 0):
    if i >= len(interceptors):
        return await ctx.method(*ctx.args, **ctx.kwargs)
    cur = interceptors[i]
    res = cur.invoke(ctx, lambda nxt: _dispatch_method_async(interceptors, nxt, i + 1))
    return await res if inspect.isawaitable(res) else res

def dispatch_method(interceptors: Sequence[MethodInterceptor], ctx: MethodCtx):
    if inspect.iscoroutinefunction(ctx.method):
        return _dispatch_method_async(interceptors, ctx, 0)
    return _dispatch_method(interceptors, ctx, 0)

def run_resolve_chain(interceptors: Sequence[ContainerInterceptor], ctx: ResolveCtx):
    def call(i: int, c: ResolveCtx):
        if i >= len(interceptors):
            return None
        return interceptors[i].around_resolve(c, lambda nxt: call(i + 1, nxt))
    return call(0, ctx)

def run_create_chain(interceptors: Sequence[ContainerInterceptor], ctx: CreateCtx):
    def call(i: int, c: CreateCtx):
        if i >= len(interceptors):
            return c.provider()
        return interceptors[i].around_create(c, lambda nxt: call(i + 1, nxt))
    return call(0, ctx)

