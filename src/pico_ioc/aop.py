# src/pico_ioc/aop.py
import inspect
import pickle
import threading
from typing import Any, Callable, Dict, List, Tuple, Protocol, Union
from .exceptions import SerializationError

KeyT = Union[str, type]

class MethodCtx:
    __slots__ = ("instance", "cls", "method", "name", "args", "kwargs", "container", "local", "request_key")
    def __init__(self, *, instance: object, cls: type, method: Callable[..., Any], name: str, args: tuple, kwargs: dict, container: Any, request_key: Any = None):
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

class UnifiedComponentProxy:
    __slots__ = ("_target", "_creator", "_container", "_cache", "_lock")
    def __init__(self, *, container: Any, target: Any = None, object_creator: Callable[[], Any] | None = None):
        if container is None:
            raise ValueError("UnifiedComponentProxy requires a non-null container")
        if target is None and object_creator is None:
            raise ValueError("UnifiedComponentProxy requires either a target or an object_creator")
        object.__setattr__(self, "_container", container)
        object.__setattr__(self, "_target", target)
        object.__setattr__(self, "_creator", object_creator)
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
            object.__setattr__(self, "_target", tgt)
            return tgt
    
    def _scope_signature(self) -> Tuple[Any, ...]:
        container = object.__getattribute__(self, "_container")
        target = object.__getattribute__(self, "_target")
        loc = getattr(container, "_locator", None)
        if not loc:
            return ()
        if target is not None:
            t = type(target)
            for k, md in loc._metadata.items():
                typ = md.provided_type or md.concrete_class
                if isinstance(typ, type) and t is typ:
                    sc = md.scope
                    if sc == "singleton":
                        return ()
                    return (container.scopes.get_id(sc),)
        return ()
    
    def _build_wrapped(self, name: str, bound: Callable[..., Any], interceptors_cls: Tuple[type, ...]):
        container = object.__getattribute__(self, "_container")
        interceptors = [container.get(cls) for cls in interceptors_cls]
        sig = self._scope_signature()
        target = self._get_real_object()
        original_func = bound
        if hasattr(bound, '__func__'):
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
                    request_key=sig[0] if sig else None
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
                    request_key=sig[0] if sig else None
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
            cache: Dict[str, Tuple[Tuple[Any, ...], Callable[..., Any], Tuple[type, ...]]] = object.__getattribute__(self, "_cache")
            cur_sig = self._scope_signature()
            cached = cache.get(name)
            if cached is not None:
                sig, wrapped, cls_tuple = cached
                if sig == cur_sig and cls_tuple == interceptors_cls:
                    return wrapped
                    
            cached = cache.get(name)
            if cached is not None:
                sig, wrapped, cls_tuple = cached
                if sig == cur_sig and cls_tuple == interceptors_cls:
                    return wrapped
            sig, wrapped, cls_tuple = self._build_wrapped(name, attr, interceptors_cls)
            cache[name] = (sig, wrapped, cls_tuple)
            return wrapped
    
    def __setattr__(self, name, value): setattr(self._get_real_object(), name, value)
    def __delattr__(self, name): delattr(self._get_real_object(), name)
    def __str__(self): return str(self._get_real_object())
    def __repr__(self): return repr(self._get_real_object())
    def __dir__(self): return dir(self._get_real_object())
    def __len__(self): return len(self._get_real_object())
    def __getitem__(self, key): return self._get_real_object()[key]
    def __setitem__(self, key, value): self._get_real_object()[key] = value
    def __delitem__(self, key): del self._get_real_object()[key]
    def __iter__(self): return iter(self._get_real_object())
    def __reversed__(self): return reversed(self._get_real_object())
    def __contains__(self, item): return item in self._get_real_object()
    def __add__(self, other): return self._get_real_object() + other
    def __sub__(self, other): return self._get_real_object() - other
    def __mul__(self, other): return self._get_real_object() * other
    def __matmul__(self, other): return self._get_real_object() @ other
    def __truediv__(self, other): return self._get_real_object() / other
    def __floordiv__(self, other): return self._get_real_object() // other
    def __mod__(self, other): return self._get_real_object() % other
    def __divmod__(self, other): return divmod(self._get_real_object(), other)
    def __pow__(self, other, modulo=None): return pow(self._get_real_object(), other, modulo)
    def __lshift__(self, other): return self._get_real_object() << other
    def __rshift__(self, other): return self._get_real_object() >> other
    def __and__(self, other): return self._get_real_object() & other
    def __xor__(self, other): return self._get_real_object() ^ other
    def __or__(self, other): return self._get_real_object() | other
    def __radd__(self, other): return other + self._get_real_object()
    def __rsub__(self, other): return other - self._get_real_object()
    def __rmul__(self, other): return other * self._get_real_object()
    def __rmatmul__(self, other): return other @ self._get_real_object()
    def __rtruediv__(self, other): return other / self._get_real_object()
    def __rfloordiv__(self, other): return other // self._get_real_object()
    def __rmod__(self, other): return other % self._get_real_object()
    def __rdivmod__(self, other): return divmod(other, self._get_real_object())
    def __rpow__(self, other): return pow(other, self._get_real_object())
    def __rlshift__(self, other): return other << self._get_real_object()
    def __rrshift__(self, other): return other >> self._get_real_object()
    def __rand__(self, other): return other & self._get_real_object()
    def __rxor__(self, other): return other ^ self._get_real_object()
    def __ror__(self, other): return other | self._get_real_object()
    def __neg__(self): return -self._get_real_object()
    def __pos__(self): return +self._get_real_object()
    def __abs__(self): return abs(self._get_real_object())
    def __invert__(self): return ~self._get_real_object()
    def __eq__(self, other): return self._get_real_object() == other
    def __ne__(self, other): return self._get_real_object() != other
    def __lt__(self, other): return self._get_real_object() < other
    def __le__(self, other): return self._get_real_object() <= other
    def __gt__(self, other): return self._get_real_object() > other
    def __ge__(self, other): return self._get_real_object() >= other
    def __hash__(self): return hash(self._get_real_object())
    def __bool__(self): return bool(self._get_real_object())
    def __call__(self, *args, **kwargs): return self._get_real_object()(*args, **kwargs)
    def __enter__(self): return self._get_real_object().__enter__()
    def __exit__(self, exc_type, exc_val, exc_tb): return self._get_real_object().__exit__(exc_type, exc_val, exc_tb)
    
    def __reduce_ex__(self, protocol):
        o = self._get_real_object()
        try:
            data = pickle.dumps(o, protocol=protocol)
            return (pickle.loads, (data,))
        except Exception as e:
            raise SerializationError(f"Proxy target is not serializable: {e}")

