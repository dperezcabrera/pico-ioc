import types
import sys
import pytest

import pico_ioc
from pico_ioc import component, factory_component, provides, init
from pico_ioc.proxy import ComponentProxy
from pico_ioc.container import PicoContainer
from pico_ioc.scanner import scan_and_configure


def make_module(name: str, ns: dict) -> types.ModuleType:
    m = types.ModuleType(name)
    for k, v in ns.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


def test_register_component_classes_lazy_and_eager():
    # module with two components, one lazy and one eager
    m = make_module("pkg_scanner_comp", {})

    @component(lazy=True)
    class A:
        pass

    @component(lazy=False)
    class B:
        pass

    m.A = A
    m.B = B

    c = PicoContainer()
    comps, facts, decls = scan_and_configure(m, c)
    assert comps == 2 and facts == 0

    a = c.get(A)
    b = c.get(B)

    assert isinstance(a, ComponentProxy), "lazy=True must return ComponentProxy instance"
    assert not isinstance(b, ComponentProxy) and isinstance(b, B), "lazy=False must return concrete instance"


def test_factory_provides_lazy_and_eager_resolve_kwargs_and_alias_via_init():
    # module with a dependency + factory that provides a service (lazy/eager)
    m = make_module("pkg_scanner_factory", {})

    class Dep:
        pass

    @component
    class DepImpl(Dep):
        pass

    class Service:
        def __init__(self, dep: Dep):
            self.dep = dep

    @factory_component
    class F:
        @provides(Service, lazy=True)
        def build_lazy(self, dep: Dep) -> Service:
            return Service(dep)

        @provides("svc_eager", lazy=False)
        def build_eager_named(self, dep: Dep):
            return Service(dep)

    m.Dep = Dep
    m.DepImpl = DepImpl
    m.Service = Service
    m.F = F

    # Use full bootstrap so policy creates alias base->impl for Service
    container = init(m)

    # Base type alias should point to the factory product and keep laziness
    svc = container.get(Service)
    assert isinstance(svc, ComponentProxy), "factory lazy=True should surface as ComponentProxy via alias"
    # Named binding remains direct and eager
    named = container.get("svc_eager")
    assert not isinstance(named, ComponentProxy)
    assert isinstance(named, Service)
    assert isinstance(named.dep, Dep), "kwargs resolution must inject Dep implementation"


def test_scan_and_configure_counts_and_interceptor_decls_collected():
    # minimal check that the scanner returns counts and interceptor decls list
    from pico_ioc.decorators import interceptor
    from pico_ioc.interceptors import MethodInterceptor

    m = make_module("pkg_scanner_counts", {})

    @component
    class A: pass

    @factory_component
    class F:
        @provides("foo")
        def p(self): return "foo"

    @interceptor(kind="method", order=-1)
    class Trace(MethodInterceptor):
        def __call__(self, inv, proceed):
            return proceed()

    m.A = A
    m.F = F
    m.Trace = Trace

    c = PicoContainer()
    comps, facts, decls = scan_and_configure(m, c)

    assert comps == 1
    assert facts == 1
    # at least one interceptor declaration found
    assert any(isinstance(obj, type) and obj.__name__ == "Trace" for obj, _ in decls)


def test_factory_unique_key_shape_and_lazy_proxy_direct_read():
    # read the composite key directly to assert proxy/eager behavior without policy alias
    m = make_module("pkg_scanner_fact_key", {})

    class Base: ...

    @component
    class Dep: ...

    @factory_component
    class F:
        @provides(Base, lazy=True)
        def make_lazy(self, dep: Dep):
            class Impl(Base):
                def __init__(self, d): self.d = d
            return Impl(dep)

    m.Base = Base
    m.Dep = Dep
    m.F = F

    c = PicoContainer()
    comps, facts, decls = scan_and_configure(m, c)
    assert comps >= 1 and facts == 1

    # compute the composite key: (Base, "F.make_lazy")
    unique_key = (Base, "F.make_lazy")
    inst = c.get(unique_key)
    assert isinstance(inst, ComponentProxy), "lazy=True provider must return ComponentProxy via unique key"

