import inspect
import pickle
import threading
from typing import Any, Callable, Dict, List, Protocol, Tuple, Union

from .constants import SCOPE_SINGLETON
from .exceptions import AsyncResolutionError, SerializationError
from .proxy_protocols import _ProxyProtocolMixin

KeyT = Union[str, type]


class MethodCtx:
    __slots__ = ("instance", "cls", "method", "name", "args", "kwargs", "container", "local", "request_key")

    def __init__(
        self,
        *,
        instance: object,
        cls: type,
        method: Callable[..., Any],
        name: str,
        args: tuple,
        kwargs: dict,
        container: Any,
        request_key: Any = None,
    ):
        self.instance = instance
        self.cls = cls
        self.method = method
        self.name = name
        self.args = args
        self.kwargs = kwargs
        self.container = container
        self.local: Dict[str, Any] = {}
        self.request_key = request_key


class MethodInterceptor(Protocol):
    def invoke(self, ctx: MethodCtx, call_next: Callable[[MethodCtx], Any]) -> Any: ...


class ContainerObserver(Protocol):
    def on_resolve(self, key: KeyT, took_ms: float): ...
    def on_cache_hit(self, key: KeyT): ...


def dispatch_method(interceptors: List["MethodInterceptor"], ctx: MethodCtx) -> Any:
    idx = 0

    def call_next(next_ctx: MethodCtx) -> Any:
        nonlocal idx
        if idx >= len(interceptors):
            return next_ctx.method(*next_ctx.args, **next_ctx.kwargs)
        interceptor = interceptors[idx]
        idx += 1
        return interceptor.invoke(next_ctx, call_next)

    return call_next(ctx)


def intercepted_by(*interceptor_classes: type["MethodInterceptor"]):
    if not interceptor_classes:
        raise TypeError("intercepted_by requires at least one interceptor class")
    for ic in interceptor_classes:
        if not inspect.isclass(ic):
            raise TypeError("intercepted_by expects interceptor classes")

    def dec(fn):
        if not (inspect.isfunction(fn) or inspect.ismethod(fn) or inspect.iscoroutinefunction(fn)):
            raise TypeError("intercepted_by can only decorate callables")
        existing = list(getattr(fn, "_pico_interceptors_", []))
        for cls in interceptor_classes:
            if cls not in existing:
                existing.append(cls)
        setattr(fn, "_pico_interceptors_", tuple(existing))
        return fn

    return dec


def _gather_interceptors_for_method(target_cls: type, name: str) -> Tuple[type, ...]:
    try:
        original = getattr(target_cls, name)
    except AttributeError:
        return ()
    if inspect.ismethoddescriptor(original) or inspect.isbuiltin(original):
        return ()
    return tuple(getattr(original, "_pico_interceptors_", ()))


def health(fn):
    from .constants import PICO_META

    meta = getattr(fn, PICO_META, None)
    if meta is None:
        meta = {}
        setattr(fn, PICO_META, meta)
    meta["health_check"] = True
    return fn


class UnifiedComponentProxy(_ProxyProtocolMixin):
    __slots__ = ("_target", "_creator", "_container", "_cache", "_lock", "_component_key")

    def __init__(
        self,
        *,
        container: Any,
        target: Any = None,
        object_creator: Callable[[], Any] | None = None,
        component_key: Any = None,
    ):
        if container is None:
            raise ValueError("UnifiedComponentProxy requires a non-null container")
        if target is None and object_creator is None:
            raise ValueError("UnifiedComponentProxy requires either a target or an object_creator")

        object.__setattr__(self, "_container", container)
        object.__setattr__(self, "_target", target)
        object.__setattr__(self, "_creator", object_creator)
        object.__setattr__(self, "_component_key", component_key)
        object.__setattr__(self, "_cache", {})
        object.__setattr__(self, "_lock", threading.RLock())

    def __getstate__(self):
        o = self._get_real_object()
        try:
            data = pickle.dumps(o)
        except Exception as e:
            raise SerializationError(f"Proxy target is not serializable: {e}")
        return {"data": data}

    def __setstate__(self, state):
        object.__setattr__(self, "_container", None)
        object.__setattr__(self, "_creator", None)
        object.__setattr__(self, "_component_key", None)
        object.__setattr__(self, "_cache", {})
        object.__setattr__(self, "_lock", threading.RLock())
        try:
            obj = pickle.loads(state["data"])
        except Exception as e:
            raise SerializationError(f"Failed to restore proxy: {e}")
        object.__setattr__(self, "_target", obj)

    def _get_real_object(self) -> Any:
        tgt = object.__getattribute__(self, "_target")
        if tgt is not None:
            return tgt

        lock = object.__getattribute__(self, "_lock")
        with lock:
            tgt = object.__getattribute__(self, "_target")
            if tgt is not None:
                return tgt

            creator = object.__getattribute__(self, "_creator")
            if not callable(creator):
                raise TypeError("UnifiedComponentProxy object_creator must be callable")

            tgt = creator()
            if tgt is None:
                raise RuntimeError("UnifiedComponentProxy object_creator returned None")

            container = object.__getattribute__(self, "_container")
            if container and hasattr(container, "_run_configure_methods"):
                res = container._run_configure_methods(tgt)
                if inspect.isawaitable(res):
                    raise AsyncResolutionError(
                        f"Lazy component {type(tgt).__name__} requires async "
                        "@configure but was resolved via sync access (proxy __getattr__). "
                        "Use 'await container.aget(Component)' to force initialization."
                    )

            object.__setattr__(self, "_target", tgt)
            return tgt

    async def _async_init_if_needed(self) -> None:
        if object.__getattribute__(self, "_target") is not None:
            return

        lock = object.__getattribute__(self, "_lock")

        with lock:
            # Double-check inside lock to prevent race condition
            tgt = object.__getattribute__(self, "_target")
            if tgt is not None:
                return

            creator = object.__getattribute__(self, "_creator")
            container = object.__getattribute__(self, "_container")

            tgt = creator()
            object.__setattr__(self, "_target", tgt)

        # Run configure methods outside the lock to avoid blocking
        if container and hasattr(container, "_run_configure_methods"):
            res = container._run_configure_methods(tgt)
            if inspect.isawaitable(res):
                await res

    def _scope_signature(self) -> Tuple[Any, ...]:
        container = object.__getattribute__(self, "_container")
        key = object.__getattribute__(self, "_component_key")
        loc = getattr(container, "_locator", None)

        if not loc or key is None:
            return ()

        if key in loc._metadata:
            md = loc._metadata[key]
            sc = md.scope
            if sc == SCOPE_SINGLETON:
                return ()

            return (container.scopes.get_id(sc),)

        return ()

    def _build_wrapped(self, name: str, bound: Callable[..., Any], interceptors_cls: Tuple[type, ...]):
        container = object.__getattribute__(self, "_container")
        interceptors = [container.get(cls) for cls in interceptors_cls]
        sig = self._scope_signature()
        target = self._get_real_object()
        original_func = bound
        if hasattr(bound, "__func__"):
            original_func = bound.__func__

        if inspect.iscoroutinefunction(original_func):

            async def aw(*args, **kwargs):
                ctx = MethodCtx(
                    instance=target,
                    cls=type(target),
                    method=bound,
                    name=name,
                    args=args,
                    kwargs=kwargs,
                    container=container,
                    request_key=sig[0] if sig else None,
                )
                res = dispatch_method(interceptors, ctx)
                if inspect.isawaitable(res):
                    return await res
                return res

            return sig, aw, interceptors_cls
        else:

            def sw(*args, **kwargs):
                ctx = MethodCtx(
                    instance=target,
                    cls=type(target),
                    method=bound,
                    name=name,
                    args=args,
                    kwargs=kwargs,
                    container=container,
                    request_key=sig[0] if sig else None,
                )
                res = dispatch_method(interceptors, ctx)
                if inspect.isawaitable(res):
                    raise RuntimeError(f"Async interceptor returned awaitable on sync method: {name}")
                return res

            return sig, sw, interceptors_cls

    @property
    def __class__(self):
        return self._get_real_object().__class__

    def __getattr__(self, name: str) -> Any:
        target = self._get_real_object()
        attr = getattr(target, name)
        if not callable(attr):
            return attr

        interceptors_cls = _gather_interceptors_for_method(type(target), name)
        if not interceptors_cls:
            return attr

        lock = object.__getattribute__(self, "_lock")
        with lock:
            cache: Dict[str, Tuple[Tuple[Any, ...], Callable[..., Any], Tuple[type, ...]]] = object.__getattribute__(
                self, "_cache"
            )

            cur_sig = self._scope_signature()
            cached = cache.get(name)

            if cached is not None:
                sig, wrapped, cls_tuple = cached
                if sig == cur_sig and cls_tuple == interceptors_cls:
                    return wrapped

            sig, wrapped, cls_tuple = self._build_wrapped(name, attr, interceptors_cls)
            cache[name] = (sig, wrapped, cls_tuple)
            return wrapped

    def __setattr__(self, name, value):
        if name in ("_target", "_creator", "_container", "_cache", "_lock", "_component_key"):
            object.__setattr__(self, name, value)
        else:
            setattr(self._get_real_object(), name, value)

    def __delattr__(self, name):
        delattr(self._get_real_object(), name)
