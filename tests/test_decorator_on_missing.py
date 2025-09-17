# tests/test_decorator_on_missing.py

import types
import pico_ioc
from pico_ioc import init, scope, component, on_missing, factory_component, provides

def test_on_missing_applies_when_no_other_binding_exists():
    pkg = types.ModuleType("pkg_omc1")

    class RepoBase: ...
    @component
    @on_missing(RepoBase, priority=5)
    class InMemoryRepo(RepoBase): ...
    pkg.RepoBase = RepoBase
    pkg.InMemoryRepo = InMemoryRepo

    c = init(pkg, plugins=())
    r = c.get(RepoBase)
    assert isinstance(r, InMemoryRepo)

def test_on_missing_is_ignored_when_regular_binding_exists():
    pkg = types.ModuleType("pkg_on_missing_2")

    class Base: ...
    @component
    @on_missing(Base, priority=10)
    class DefaultImpl(Base): ...
    @component
    class RealImpl(Base): ...
    @component
    class Service:
        def __init__(self, dep: Base):
            self.dep = dep

    pkg.Base = Base
    pkg.DefaultImpl = DefaultImpl
    pkg.RealImpl = RealImpl
    pkg.Service = Service

    c = pico_ioc.init(pkg)
    svc = c.get(Service)
    assert isinstance(svc.dep, RealImpl)

def test_on_missing_selects_by_highest_priority():
    pkg = types.ModuleType("pkg_omc2")

    class RepoBase: ...
    @component
    @on_missing(RepoBase, priority=1)
    class Low(RepoBase): ...
    @component
    @on_missing(RepoBase, priority=10)
    class High(RepoBase): ...
    pkg.RepoBase = RepoBase
    pkg.Low = Low
    pkg.High = High

    c = init(pkg, plugins=())
    r = c.get(RepoBase)
    assert isinstance(r, High)

def test_on_missing_works_with_factory_provides_method():
    pkg = types.ModuleType("pkg_on_missing_3")

    class Base: ...
    @factory_component
    class F:
        def __init__(self):
            pass

        @provides(Base)
        @on_missing(Base, priority=5)
        def build_default(self) -> Base:
            class Default(Base): ...
            return Default()

    @component
    class Service:
        def __init__(self, dep: Base):
            self.dep = dep

    pkg.Base = Base
    pkg.F = F
    pkg.Service = Service

    c = pico_ioc.init(pkg)
    svc = c.get(Service)
    assert isinstance(svc.dep, Base)
    _ = c.get(Base)

def test_on_missing_is_applied_in_scope():
    pkg = types.ModuleType("pkg_omc3")

    class RepoBase: ...
    @component
    @on_missing(RepoBase, priority=1)
    class DefaultRepo(RepoBase): ...
    pkg.RepoBase = RepoBase
    pkg.DefaultRepo = DefaultRepo

    c = scope(modules=[pkg], roots=[RepoBase], strict=True, lazy=True)
    r = c.get(RepoBase)
    assert isinstance(r, DefaultRepo)
