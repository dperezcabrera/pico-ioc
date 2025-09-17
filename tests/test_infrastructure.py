import pytest
import asyncio
import sys
import types
import logging

from pico_ioc import (
    init, scope, component, factory_component, provides, infrastructure, reset,
    MethodInterceptor, ContainerInterceptor, Select
)

class _Bag:
    def __init__(self): self.events = []
    def add(self, *e): self.events.append(tuple(e))


def test_infrastructure_registers_method_interceptor_and_mutations():
    import pico_ioc
    from pico_ioc import component, infrastructure, Select

    calls = []

    pkg = types.ModuleType("pkg_infra_smoke")

    @component(tags=("http",))
    class Service:
        def ping(self) -> str:
            return "ok"

    @infrastructure(order=10, profiles=())
    class InfraA:
        def configure(self, infra):
            sel = Select().has_tag("http")
            class It:
                def invoke(self, ctx, call_next):
                    calls.append(("before", ctx.name))
                    res = call_next(ctx)
                    calls.append(("after", ctx.name))
                    return res
            infra.intercept.add(interceptor=It(), where=sel)
            infra.mutate.add_tags(Service, ("extra",))

    pkg.Service = Service
    pkg.InfraA = InfraA

    c = pico_ioc.init(pkg)
    s = c.get(Service)
    assert s.ping() == "ok"
    assert ("before", "ping") in calls and ("after", "ping") in calls

    provs = c.get_providers()
    assert Service in provs
    assert "extra" in set(provs[Service].get("tags", ()))


def test_infrastructure_registers_container_interceptor():
    import pico_ioc
    from pico_ioc import component, infrastructure, Select
    events = []

    pkg = types.ModuleType("pkg_infra_container")

    @component
    class A:
        pass

    @infrastructure(order=5)
    class InfraB:
        def configure(self, infra):
            sel = Select().class_name("A")
            class CI:
                def around_resolve(self, ctx, call_next):
                    events.append(("res", ctx.key))
                    return call_next(ctx)
                def around_create(self, ctx, call_next):
                    events.append(("before", ctx.key))
                    inst = call_next(ctx)
                    events.append(("after", ctx.key))
                    return inst
            infra.intercept.add(interceptor=CI(), where=sel)

    pkg.A = A
    pkg.InfraB = InfraB

    c = pico_ioc.init(pkg)
    _ = c.get(A)
    kinds = [e[0] for e in events]
    assert "before" in kinds and "after" in kinds


@pytest.mark.filterwarnings("ignore:coroutine .* was never awaited")
def test_async_interceptor_on_sync_method_raises_error():
    @component
    class MySyncService:
        def do_work(self):
            return "sync_result"

    @infrastructure
    class AsyncReturningInfra:
        def configure(self, infra):
            class AsyncReturningInterceptor(MethodInterceptor):
                def invoke(self, ctx, call_next):
                    async def async_result():
                        await asyncio.sleep(0)
                        return "async_result"
                    return async_result()
            sel = Select().class_name("MySyncService")
            infra.intercept.add(interceptor=AsyncReturningInterceptor(), where=sel)

    mod = sys.modules[__name__]
    mod.MySyncService = MySyncService
    mod.AsyncReturningInfra = AsyncReturningInfra

    container = init(mod, auto_exclude_caller=False)
    svc = container.get(MySyncService)

    with pytest.raises(RuntimeError, match="Async interceptor on sync method: do_work"):
        svc.do_work()


def test_container_lifecycle_hooks_are_called():
    events = []
    pkg = types.ModuleType("pkg_lifecycle")

    @component
    class Dep: pass

    @component
    class Service:
        def __init__(self, dep: Dep): self.dep = dep

    pkg.Dep, pkg.Service = Dep, Service

    @infrastructure(order=5)
    class TrackingInfra:
        def configure(self, infra):
            class TrackingInterceptor(ContainerInterceptor):
                def around_resolve(self, ctx, call_next):
                    events.append(("res", ctx.key))
                    return call_next(ctx)
                def around_create(self, ctx, call_next):
                    events.append(("before", ctx.key))
                    inst = call_next(ctx)
                    events.append(("after", ctx.key))
                    return inst
            infra.intercept.add(interceptor=TrackingInterceptor(), where=Select().class_name(".*"))

    pkg.TrackingInfra = TrackingInfra

    c = init(pkg)
    _ = c.get(Service)

    assert ("before", Service) in events
    assert ("after", Service) in events
    assert any(e[0] == "res" for e in events)


def test_interceptor_activates_by_profile(caplog):
    caplog.set_level(logging.INFO)
    bag = _Bag()
    pkg = types.ModuleType("pkg_it_class_profile")

    @component
    class Svc:
        def ping(self): return "pong"
    pkg.Svc = Svc

    @infrastructure(profiles=("prod",))
    class CallTracerInfra:
        def configure(self, infra):
            class CallTracer(MethodInterceptor):
                def invoke(self, ctx, call_next):
                    bag.add("before", ctx.name)
                    res = call_next(ctx)
                    bag.add("after", ctx.name)
                    return res
            infra.intercept.add(interceptor=CallTracer(), where=Select().class_name("Svc"))
    pkg.CallTracerInfra = CallTracerInfra

    c_dev = init(pkg, profiles=["dev"], reuse=False)
    c_dev.get(Svc).ping()
    assert bag.events == []

    c_prod = init(pkg, profiles=["prod"], reuse=False)
    c_prod.get(Svc).ping()
    assert bag.events == [("before", "ping"), ("after", "ping")]


def test_interceptor_activates_by_env_var(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    bag = _Bag()
    pkg = types.ModuleType("pkg_it_provider_env")

    @component
    class Svc: pass
    pkg.Svc = Svc

    @infrastructure(require_env=("TRACE_ALL",))
    class TraceInfra:
        def configure(self, infra):
            class Trace(ContainerInterceptor):
                def around_resolve(self, ctx, call_next):
                    return call_next(ctx)
                def around_create(self, ctx, call_next):
                    bag.add("before", ctx.key)
                    return call_next(ctx)
            infra.intercept.add(interceptor=Trace(), where=Select().class_name("Svc"))
    pkg.TraceInfra = TraceInfra

    monkeypatch.delenv("TRACE_ALL", raising=False)
    c1 = init(pkg, reuse=False)
    _ = c1.get(Svc)
    assert bag.events == []

    monkeypatch.setenv("TRACE_ALL", "1")
    bag.events.clear()
    c2 = init(pkg, reuse=False)
    _ = c2.get(Svc)
    assert ("before", Svc) in bag.events


@pytest.mark.parametrize("label,pred,should_activate", [
    ("true_predicate", lambda: True, True),
    ("false_predicate", lambda: False, False),
    ("error_predicate", lambda: (_ for _ in ()).throw(RuntimeError("boom")), False),
])
def test_interceptor_predicate_controls_activation(label, pred, should_activate, caplog):
    caplog.set_level(logging.DEBUG)
    bag = _Bag()
    pkg = types.ModuleType(f"pkg_it_pred_{label}")

    @component
    class Svc:
        def foo(self): return "ok"
    pkg.Svc = Svc

    @infrastructure(predicate=pred)
    class RecorderInfra:
        def configure(self, infra):
            class Recorder(MethodInterceptor):
                def invoke(self, ctx, call_next):
                    bag.add("seen", ctx.name)
                    return call_next(ctx)
            infra.intercept.add(interceptor=Recorder(), where=Select().class_name("Svc"))
    pkg.RecorderInfra = RecorderInfra

    c = init(pkg, reuse=False)
    _ = c.get(Svc).foo()

    if should_activate:
        assert ("seen", "foo") in bag.events
    else:
        assert bag.events == []


def test_interceptor_ordering_is_stable():
    bag = _Bag()
    pkg = types.ModuleType("pkg_it_ordering")

    @component
    class Svc:
        def run(self): return "ok"
    pkg.Svc = Svc

    @infrastructure(order=10)
    class LateInfra:
        def configure(self, infra):
            class Late(MethodInterceptor):
                def invoke(self, ctx, call_next):
                    bag.add("late_before")
                    r = call_next(ctx)
                    bag.add("late_after")
                    return r
            infra.intercept.add(interceptor=Late(), where=Select().class_name("Svc"))
    pkg.LateInfra = LateInfra

    @infrastructure(order=-5)
    class EarlyInfra:
        def configure(self, infra):
            class Early(MethodInterceptor):
                def invoke(self, ctx, call_next):
                    bag.add("early_before")
                    r = call_next(ctx)
                    bag.add("early_after")
                    return r
            infra.intercept.add(interceptor=Early(), where=Select().class_name("Svc"))
    pkg.EarlyInfra = EarlyInfra

    c = init(pkg, reuse=False)
    _ = c.get(Svc).run()
    assert bag.events == [("early_before",), ("late_before",), ("late_after",), ("early_after",)]


def test_scope_inherits_and_adds_interceptors():
    base_bag, scope_bag = _Bag(), _Bag()

    base_pkg = types.ModuleType("pkg_it_scope_base")

    @component
    class BaseSvc:
        def ping(self): return "ok"
    base_pkg.BaseSvc = BaseSvc

    @infrastructure
    class BaseInfra:
        def configure(self, infra):
            class BaseInterceptor(MethodInterceptor):
                def invoke(self, ctx, call_next):
                    base_bag.add("base")
                    return call_next(ctx)
            infra.intercept.add(interceptor=BaseInterceptor(), where=Select().class_name(".*"))
    base_pkg.BaseInfra = BaseInfra

    base_c = init(base_pkg, reuse=False)

    spkg = types.ModuleType("pkg_it_scope_mod")

    @component
    class App:
        def __init__(self, dep: BaseSvc): self.dep = dep
        def run(self): return "ok"
    spkg.App = App

    @infrastructure(order=5)
    class ScopedInfra:
        def configure(self, infra):
            class ScopedInterceptor(MethodInterceptor):
                def invoke(self, ctx, call_next):
                    scope_bag.add("scope")
                    return call_next(ctx)
            infra.intercept.add(interceptor=ScopedInterceptor(), where=Select().class_name("App"))
    spkg.ScopedInfra = ScopedInfra

    s = scope(modules=[spkg], base=base_c, strict=False, roots=[App])
    _ = s.get(App)
    s.get(BaseSvc).ping()
    assert ("base",) in base_bag.events
    s.get(App).run()
    assert ("scope",) in scope_bag.events


def test_provider_with_wrong_return_type_is_ignored_for_container_interceptor():
    bag = _Bag()
    pkg = types.ModuleType("pkg_it_wrong_type")

    @component
    class Svc: pass
    pkg.Svc = Svc

    @infrastructure
    class BadInfra:
        def configure(self, infra):
            class NotAContainer:
                def something(self): pass
            try:
                infra.intercept.add(interceptor=NotAContainer(), where=Select().class_name("Svc"))
            except Exception as e:
                bag.add("error", str(type(e)))
    pkg.BadInfra = BadInfra

    c = init(pkg, reuse=False)
    _ = c.get(Svc)
    assert bag.events == []

