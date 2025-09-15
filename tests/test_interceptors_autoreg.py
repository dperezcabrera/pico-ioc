# tests/test_interceptors_autoreg.py
import types
import logging
import pytest
from pico_ioc import (
    init, scope, component, factory_component, provides, conditional, interceptor, reset
)
from pico_ioc.interceptors import MethodInterceptor, ContainerInterceptor

class _Bag:
    def __init__(self): self.events = []
    def add(self, *e): self.events.append(tuple(e))

@pytest.fixture(autouse=True)
def clean_state():
    reset()
    yield
    reset()

def test_class_method_interceptor_activates_by_profile(caplog):
    caplog.set_level(logging.INFO)
    bag = _Bag()
    pkg = types.ModuleType("pkg_it_class_profile")
    @component
    class Svc:
        def ping(self): return "pong"
    @interceptor(kind="method", order=0, profiles=("prod",))
    class CallTracer:
        def __call__(self, inv, proceed):
            bag.add("before", inv.method_name)
            res = proceed()
            bag.add("after", inv.method_name)
            return res
    pkg.Svc = Svc
    pkg.CallTracer = CallTracer

    c = init(pkg, profiles=["prod"], reuse=False)
    assert c.get(Svc).ping() == "pong"
    assert bag.events == [("before", "ping"), ("after", "ping")]
    assert any("Interceptors activated" in r.message for r in caplog.records)

def test_provider_container_interceptor_activates_by_env(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    bag = _Bag()
    pkg = types.ModuleType("pkg_it_provider_env")
    @component
    class Svc:
        def ping(self): return "pong"
    @factory_component
    class ObsFactory:
        @provides(ContainerInterceptor)
        @interceptor(kind="container", require_env=("TRACE_ALL",))
        def build(self) -> ContainerInterceptor:
            class Trace(ContainerInterceptor):
                def on_before_create(self, k): bag.add("before", k)
                def on_after_create(self, k, inst): bag.add("after", k)
            return Trace()
    pkg.Svc = Svc
    pkg.ObsFactory = ObsFactory

    monkeypatch.delenv("TRACE_ALL", raising=False)
    c1 = init(pkg, reuse=False)
    _ = c1.get(Svc)
    assert bag.events == []

    monkeypatch.setenv("TRACE_ALL", "1")
    bag = _Bag()
    c2 = init(pkg, reuse=False)
    _ = c2.get(Svc)
    kinds = {e[0] for e in bag.events}
    assert "before" in kinds and "after" in kinds
    assert "Activated container=" in caplog.text


@pytest.mark.parametrize("label,pred,should_activate", [
    ("true", lambda: True, True),
    ("false", lambda: False, False),
    ("error", lambda: (_ for _ in ()).throw(RuntimeError("boom")), False),
])
def test_interceptor_predicate_controls_activation(label, pred, should_activate, caplog):
    caplog.set_level(logging.DEBUG)
    bag = _Bag()
    pkg = types.ModuleType(f"pkg_it_pred_{label}")
    @component
    class Svc:
        def foo(self): return "ok"
    @interceptor(kind="method", predicate=pred)
    class Recorder:
        def __call__(self, inv, proceed):
            bag.add("seen", inv.method_name)
            return proceed()
    pkg.Svc = Svc
    pkg.Recorder = Recorder

    c = init(pkg, reuse=False)
    _ = c.get(Svc).foo()
    if should_activate:
        assert ("seen", "foo") in bag.events
    else:
        assert bag.events == []
        if label == "error":
            assert any("Interceptor predicate failed" in r.message for r in caplog.records)

def test_ordering_stable_by_order_then_name():
    bag = _Bag()
    pkg = types.ModuleType("pkg_it_ordering")
    @component
    class Svc:
        def run(self): return "ok"
    @interceptor(kind="method", order=10)
    class Late:
        def __call__(self, inv, proceed):
            bag.add("late_before")
            r = proceed()
            bag.add("late_after")
            return r
    @interceptor(kind="method", order=-5)
    class Early:
        def __call__(self, inv, proceed):
            bag.add("early_before")
            r = proceed()
            bag.add("early_after")
            return r
    pkg.Svc = Svc
    pkg.Late = Late
    pkg.Early = Early

    c = init(pkg, reuse=False)
    _ = c.get(Svc).run()
    assert bag.events == [("early_before",), ("late_before",), ("late_after",), ("early_after",)]

def test_idempotent_registration_for_same_class():
    bag = _Bag()
    pkg = types.ModuleType("pkg_it_idempotent")
    @component
    class Svc:
        def a(self): return 1
    @interceptor(kind="method", order=0)
    class OnceOnly:
        def __call__(self, inv, proceed):
            bag.add("x")
            return proceed()
    pkg.Svc = Svc
    pkg.OnceOnly = OnceOnly
    pkg.OnceOnly_again = OnceOnly

    c = init(pkg, reuse=False)
    _ = c.get(Svc).a()
    assert bag.events == [("x",)]

def test_provider_wrong_return_type_logs_error(caplog):
    caplog.set_level(logging.ERROR)
    pkg = types.ModuleType("pkg_it_wrong_type")
    @factory_component
    class BadFactory:
        @provides(ContainerInterceptor)
        @interceptor(kind="container")
        def oops(self): return object()
    @component
    class Svc:
        def ping(self): return "pong"
    pkg.BadFactory = BadFactory
    pkg.Svc = Svc

    c = init(pkg, reuse=False)
    _ = c.get(Svc)
    assert any("lacks required methods; skipping" in r.message for r in caplog.records)

def test_scope_inherits_and_adds_interceptors():
    base_bag = _Bag()
    scope_bag = _Bag()
    base_pkg = types.ModuleType("pkg_it_scope_base")
    @component
    class BaseSvc:
        def ping(self): return "pong"
    @interceptor(kind="method", order=0)
    class BaseCall:
        def __call__(self, inv, proceed):
            base_bag.add("base")
            return proceed()
    base_pkg.BaseSvc = BaseSvc
    base_pkg.BaseCall = BaseCall

    base_c = init(base_pkg, reuse=False)

    spkg = types.ModuleType("pkg_it_scope_mod")
    @component
    class App:
        def __init__(self, dep: BaseSvc): self.dep = dep
        def run(self): return self.dep.ping()
    @interceptor(kind="method", order=5)
    class MoreCalls:
        def __call__(self, inv, proceed):
            scope_bag.add("scope")
            return proceed()
    spkg.App = App
    spkg.MoreCalls = MoreCalls

    s = scope(modules=[spkg], base=base_c, strict=False, roots=[App])
    _ = s.get(App).run()

    assert ("base",) in base_bag.events
    assert ("scope",) in scope_bag.events
    
def test_init_autoscan_missing_pkg_warns_by_default(caplog):
    from pico_ioc import init
    caplog.set_level("WARNING")
    c = init(__name__, auto_scan=["no_such_pkg_123"], reuse=False)
    assert any("auto_scan package not found: no_such_pkg_123" in r.message for r in caplog.records)

def test_init_autoscan_missing_pkg_raises_in_strict_mode():
    from pico_ioc import init
    with pytest.raises(ImportError):
        _ = init(__name__, auto_scan=["no_such_pkg_456"], strict_autoscan=True, reuse=False)
