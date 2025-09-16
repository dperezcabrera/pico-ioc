# tests/test_interceptors.py
import pytest
import asyncio
import sys
import types
import logging

from pico_ioc import (
    init, scope, component, factory_component, provides, interceptor, reset,
    MethodInterceptor, ContainerInterceptor
)

# ----- Helpers & Fixtures -----

class _Bag:
    """A simple helper class to collect events during tests."""
    def __init__(self): self.events = []
    def add(self, *e): self.events.append(tuple(e))

@pytest.fixture(autouse=True)
def clean_state():
    """Ensures a clean global state for each test."""
    reset()
    yield
    reset()

# --- Method Interceptor Invocation ---

@pytest.mark.filterwarnings("ignore:coroutine .* was never awaited")
def test_async_interceptor_on_sync_method_raises_error():
    """
    Verifies that IoCProxy raises a RuntimeError when an async interceptor
    is applied to a synchronous method.
    """
    @interceptor
    class AsyncReturningInterceptor(MethodInterceptor):
        def __call__(self, inv, proceed):
            async def async_proceed():
                await asyncio.sleep(0)
                return "async_result"
            return async_proceed()

    @component
    class MySyncService:
        def do_work(self):
            return "sync_result"

    mod = sys.modules[__name__]
    mod.AsyncReturningInterceptor = AsyncReturningInterceptor
    mod.MySyncService = MySyncService

    container = init(mod, auto_exclude_caller=False)
    svc = container.get(MySyncService)

    with pytest.raises(RuntimeError, match="Async interceptor on sync method: do_work"):
        svc.do_work()

# --- Container Interceptor Lifecycle ---

def test_container_lifecycle_hooks_are_called():
    """
    Ensures that ContainerInterceptor hooks (on_resolve, on_before_create, etc.)
    are called during component resolution and creation.
    """
    events = []
    pkg = types.ModuleType("pkg_lifecycle")

    @interceptor(kind="container")
    class TrackingInterceptor(ContainerInterceptor):
        def on_resolve(self, k, a, q): events.append(("res", k))
        def on_before_create(self, k): events.append(("before", k))
        def on_after_create(self, k, inst): events.append(("after", k)); return inst
        def on_exception(self, k, exc): events.append(("err", k))
    pkg.TrackingInterceptor = TrackingInterceptor

    @component
    class Dep: pass
    @component
    class Service:
        def __init__(self, dep: Dep): self.dep = dep
    pkg.Dep, pkg.Service = Dep, Service

    c = init(pkg)
    _ = c.get(Service)

    assert ("before", Service) in events
    assert ("after", Service) in events
    assert any(e[0] == "res" for e in events)

# --- Auto-Registration and Conditional Activation ---

def test_interceptor_activates_by_profile(caplog):
    """Verifies an interceptor can be activated by matching profiles."""
    caplog.set_level(logging.INFO)
    bag = _Bag()
    pkg = types.ModuleType("pkg_it_class_profile")
    
    @component
    class Svc:
        def ping(self): return "pong"
    @interceptor(profiles=("prod",))
    class CallTracer(MethodInterceptor):
        def __call__(self, inv, proceed):
            bag.add("before", inv.method_name)
            res = proceed()
            bag.add("after", inv.method_name)
            return res
    pkg.Svc, pkg.CallTracer = Svc, CallTracer

    # Does not activate if profile doesn't match
    c_dev = init(pkg, profiles=["dev"], reuse=False)
    c_dev.get(Svc).ping()
    assert bag.events == []

    # Activates when profile matches
    c_prod = init(pkg, profiles=["prod"], reuse=False)
    c_prod.get(Svc).ping()
    assert bag.events == [("before", "ping"), ("after", "ping")]
    assert any("Interceptors activated" in r.message for r in caplog.records)

def test_interceptor_activates_by_env_var(monkeypatch, caplog):
    """Verifies an interceptor can be activated by a required environment variable."""
    caplog.set_level(logging.DEBUG)
    bag = _Bag()
    pkg = types.ModuleType("pkg_it_provider_env")
    
    @component
    class Svc: pass
    @interceptor(kind="container", require_env=("TRACE_ALL",))
    class Trace(ContainerInterceptor):
        def on_before_create(self, k): bag.add("before", k)
    pkg.Svc, pkg.Trace = Svc, Trace

    # Does not activate when env var is missing
    monkeypatch.delenv("TRACE_ALL", raising=False)
    c1 = init(pkg, reuse=False)
    _ = c1.get(Svc)
    assert bag.events == []

    # Activates when env var is present
    monkeypatch.setenv("TRACE_ALL", "1")
    bag.events.clear()
    c2 = init(pkg, reuse=False)
    _ = c2.get(Svc)
    assert ("before", Svc) in bag.events
    assert "Activated container=" in caplog.text

@pytest.mark.parametrize("label,pred,should_activate", [
    ("true_predicate", lambda: True, True),
    ("false_predicate", lambda: False, False),
    ("error_predicate", lambda: (_ for _ in ()).throw(RuntimeError("boom")), False),
])
def test_interceptor_predicate_controls_activation(label, pred, should_activate, caplog):
    """Verifies the 'predicate' function correctly controls interceptor activation."""
    caplog.set_level(logging.DEBUG)
    bag = _Bag()
    pkg = types.ModuleType(f"pkg_it_pred_{label}")
    
    @component
    class Svc:
        def foo(self): return "ok"
    @interceptor(predicate=pred)
    class Recorder(MethodInterceptor):
        def __call__(self, inv, proceed):
            bag.add("seen", inv.method_name)
            return proceed()
    pkg.Svc, pkg.Recorder = Svc, Recorder

    c = init(pkg, reuse=False)
    _ = c.get(Svc).foo()
    
    if should_activate:
        assert ("seen", "foo") in bag.events
    else:
        assert bag.events == []
        if "error" in label:
            assert any("Interceptor predicate failed" in r.message for r in caplog.records)

# --- Ordering, Scoping, and Error Handling ---

def test_interceptor_ordering_is_stable():
    """Verifies that interceptors are applied according to their 'order' attribute."""
    bag = _Bag()
    pkg = types.ModuleType("pkg_it_ordering")
    
    @component
    class Svc:
        def run(self): return "ok"
    @interceptor(order=10)
    class Late(MethodInterceptor):
        def __call__(self, inv, proceed):
            bag.add("late_before")
            r = proceed()
            bag.add("late_after")
            return r
    @interceptor(order=-5)
    class Early(MethodInterceptor):
        def __call__(self, inv, proceed):
            bag.add("early_before")
            r = proceed()
            bag.add("early_after")
            return r
    pkg.Svc, pkg.Late, pkg.Early = Svc, Late, Early

    c = init(pkg, reuse=False)
    _ = c.get(Svc).run()
    assert bag.events == [("early_before",), ("late_before",), ("late_after",), ("early_after",)]

def test_scope_inherits_and_adds_interceptors():
    """Tests that a scoped container inherits base interceptors and can add its own."""
    base_bag, scope_bag = _Bag(), _Bag()
    
    # Base container with an interceptor
    base_pkg = types.ModuleType("pkg_it_scope_base")
    @component
    class BaseSvc:
        def ping(self): return "ok"
        
    @interceptor
    class BaseInterceptor(MethodInterceptor):
        def __call__(self, inv, proceed):
            base_bag.add("base")
            return proceed()
    base_pkg.BaseSvc, base_pkg.BaseInterceptor = BaseSvc, BaseInterceptor
    base_c = init(base_pkg, reuse=False)

    # Scoped container with another interceptor
    spkg = types.ModuleType("pkg_it_scope_mod")
    @component
    class App:
        def __init__(self, dep: BaseSvc): self.dep = dep
        def run(self): return "ok"
         
    @interceptor(order=5)
    class ScopedInterceptor(MethodInterceptor):
        def __call__(self, inv, proceed):
            scope_bag.add("scope")
            return proceed()
    spkg.App, spkg.ScopedInterceptor = App, ScopedInterceptor

    s = scope(modules=[spkg], base=base_c, strict=False, roots=[App])
    _ = s.get(App)

    # Verify both interceptors are active on their respective components
    s.get(BaseSvc).ping()
    assert ("base",) in base_bag.events
    s.get(App).run()
    assert ("scope",) in scope_bag.events

def test_provider_with_wrong_return_type_logs_error(caplog):
    """
    Checks that a provider factory for an interceptor that returns an
    invalid type logs an error and is skipped.
    """
    caplog.set_level(logging.ERROR)
    pkg = types.ModuleType("pkg_it_wrong_type")
    
    @factory_component
    class BadFactory:
        @provides(ContainerInterceptor)
        @interceptor(kind="container")
        def oops(self): return object() # Incorrect type
    @component
    class Svc: pass
    pkg.BadFactory, pkg.Svc = BadFactory, Svc

    c = init(pkg, reuse=False)
    _ = c.get(Svc)
    assert any("lacks required methods; skipping" in r.message for r in caplog.records)
