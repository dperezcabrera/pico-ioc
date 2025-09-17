import types
import sys
import pytest

import pico_ioc
from pico_ioc import component, factory_component, provides, init, infrastructure
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

    assert isinstance(a, ComponentProxy)
    assert not isinstance(b, ComponentProxy) and isinstance(b, B)


def test_factory_provides_lazy_and_eager_resolve_kwargs_and_alias_via_init():
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

    container = init(m)

    svc = container.get(Service)
    assert isinstance(svc, ComponentProxy)
    named = container.get("svc_eager")
    assert not isinstance(named, ComponentProxy)
    assert isinstance(named, Service)
    assert isinstance(named.dep, Dep)


def test_scan_and_configure_counts_and_infrastructure_decls_collected():
    from pico_ioc.infra import Infra

    m = make_module("pkg_scanner_counts", {})

    @component
    class A:
        pass

    @factory_component
    class F:
        @provides("foo")
        def p(self):
            return "foo"

    @infrastructure(order=-1)
    class Trace:
        def configure(self, infra: Infra):
            pass

    m.A = A
    m.F = F
    m.Trace = Trace

    c = PicoContainer()
    comps, facts, decls = scan_and_configure(m, c)

    assert comps == 1
    assert facts == 1
    assert any(isinstance(obj, type) and obj.__name__ == "Trace" for obj, _ in decls)


def test_factory_unique_key_shape_and_lazy_proxy_direct_read():
    m = make_module("pkg_scanner_fact_key", {})

    class Base:
        pass

    @component
    class Dep:
        pass

    @factory_component
    class F:
        @provides(Base, lazy=True)
        def make_lazy(self, dep: Dep):
            class Impl(Base):
                def __init__(self, d):
                    self.d = d
            return Impl(dep)

    m.Base = Base
    m.Dep = Dep
    m.F = F

    c = PicoContainer()
    comps, facts, decls = scan_and_configure(m, c)
    assert comps >= 1 and facts == 1

    unique_key = (Base, "F.make_lazy")
    inst = c.get(unique_key)
    assert isinstance(inst, ComponentProxy)

