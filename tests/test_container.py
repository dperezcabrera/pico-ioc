import pytest
import types
from typing import Protocol

from pico_ioc import _state, init, component
from pico_ioc.container import PicoContainer, Binder
from pico_ioc.interceptors import MethodInterceptor, ContainerInterceptor
from pico_ioc.proxy import IoCProxy


class MyService:
    def do_work(self):
        return "done"

class NoArgInterceptor(MethodInterceptor):
    def __init__(self):
        self.invoked = False
    def invoke(self, ctx, call_next):
        self.invoked = True
        return call_next(ctx)

class ExceptionInterceptor(ContainerInterceptor):
    def __init__(self):
        self.caught = []
    def around_resolve(self, ctx, call_next):
        return call_next(ctx)
    def around_create(self, ctx, call_next):
        try:
            return call_next(ctx)
        except BaseException as exc:
            self.caught.append((ctx.key, exc))
            raise

class ReplaceInterceptor(ContainerInterceptor):
    def around_resolve(self, ctx, call_next):
        return call_next(ctx)
    def around_create(self, ctx, call_next):
        inst = call_next(ctx)
        return "replaced" if isinstance(inst, MyService) else inst

class ServiceProtocol(Protocol):
    def x(self) -> str: ...

@component
class ServiceA:
    def x(self) -> str: return "a"

@component
class ServiceB:
    def x(self) -> str: return "b"


class TestPicoContainerCore:
    def test_bind_and_get_caches_singleton(self):
        c = PicoContainer(providers={})
        calls = {"n": 0}
        def provider():
            calls["n"] += 1
            return object()
        c.bind("k", provider, lazy=False)
        a = c.get("k")
        b = c.get("k")
        assert a is b
        assert calls["n"] == 1
        assert c.has("k") is True

    def test_missing_key_raises_nameerror(self):
        c = PicoContainer(providers={})
        with pytest.raises(NameError):
            _ = c.get("nope")

    def test_eager_instantiate_all_instantiates_only_non_lazy(self):
        c = PicoContainer(providers={})
        calls = {"eager": 0, "lazy": 0}
        def eager_p():
            calls["eager"] += 1
            return "eager"
        def lazy_p():
            calls["lazy"] += 1
            return "lazy"
        c.bind("eager_key", eager_p, lazy=False)
        c.bind("lazy_key", lazy_p, lazy=True)
        c.eager_instantiate_all()
        assert calls["eager"] == 1
        assert c._singletons["eager_key"] == "eager"
        assert calls["lazy"] == 0
        assert "lazy_key" not in c._singletons
        assert c.get("lazy_key") == "lazy"
        assert calls["lazy"] == 1

    def test_has_reports_correctly(self):
        c = PicoContainer(providers={})
        c.bind("k", lambda: "v", lazy=False)
        assert c.has("k") is True
        _ = c.get("k")
        assert c.has("k") is True
        assert c.has("nope") is False


class TestContainerGetAll:
    def test_get_all_finds_protocol_implementations(self):
        pkg = types.ModuleType("pkg_get_all")
        pkg.ServiceA = ServiceA
        pkg.ServiceB = ServiceB
        pkg.ServiceProtocol = ServiceProtocol
        c = init(pkg)
        items = c.get_all(ServiceProtocol)
        assert len(items) == 2
        assert {i.x() for i in items} == {"a", "b"}


class TestContainerInterceptors:
    def test_method_interceptor_creates_proxy_and_is_invoked(self):
        container = PicoContainer(providers={})
        interceptor = NoArgInterceptor()
        container.add_method_interceptor(interceptor)
        container.bind(MyService, MyService, lazy=False)
        service_proxy = container.get(MyService)
        assert isinstance(service_proxy, IoCProxy)
        assert interceptor.invoked is False
        result = service_proxy.do_work()
        assert result == "done"
        assert interceptor.invoked is True

    def test_container_interceptor_on_exception_hook(self):
        def failing_provider():
            raise ValueError("Creation failed")
        interceptor = ExceptionInterceptor()
        container = PicoContainer(providers={})
        container.add_container_interceptor(interceptor)
        container.bind("failing_key", failing_provider, lazy=False)
        with pytest.raises(ValueError, match="Creation failed"):
            container.get("failing_key")
        assert len(interceptor.caught) == 1
        key, exc = interceptor.caught[0]
        assert key == "failing_key"
        assert isinstance(exc, ValueError)

    def test_container_interceptor_replaces_instance_with_on_after_create(self):
        container = PicoContainer(providers={})
        container.add_container_interceptor(ReplaceInterceptor())
        container.bind(MyService, MyService, lazy=False)
        instance = container.get(MyService)
        assert instance == "replaced"
        assert container.get(MyService) == "replaced"


class TestContainerStateGuards:
    def test_reentrant_guard_raises_during_scan_only(self):
        c = PicoContainer(providers={})
        c.bind("x", lambda: object(), lazy=False)
        tok_scan = _state._scanning.set(True)
        try:
            with pytest.raises(RuntimeError, match="re-entrant container access during scan"):
                _ = c.get("x")
        finally:
            _state._scanning.reset(tok_scan)

    def test_access_allowed_when_resolving_even_if_scanning(self):
        c = PicoContainer(providers={})
        c.bind("y", lambda: object(), lazy=False)
        tok_scan = _state._scanning.set(True)
        tok_res = _state._resolving.set(True)
        try:
            instance = c.get("y")
            assert instance is not None
        finally:
            _state._resolving.reset(tok_res)
            _state._scanning.reset(tok_scan)


class TestBinder:
    def test_binder_proxies_bind_has_get(self):
        c = PicoContainer(providers={})
        b = Binder(c)
        made = object()
        b.bind("key", lambda: made, lazy=False)
        assert b.has("key") is True
        assert c.has("key") is True
        assert b.get("key") is made

