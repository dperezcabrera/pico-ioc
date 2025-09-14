# tests/test_on_missing_blackbox.py

import types
import pico_ioc
from pico_ioc import component, on_missing, factory_component, provides

def test_on_missing_binds_when_absent():
    """
    When only a default implementation is present, resolving Base picks that default.
    """
    pkg = types.ModuleType("pkg_on_missing_1")

    class Base: ...
    @component
    @on_missing(Base, priority=10)
    class DefaultImpl(Base): ...
    @component
    class Service:
        def __init__(self, dep: Base):
            self.dep = dep

    # expose in module
    pkg.Base = Base
    pkg.DefaultImpl = DefaultImpl
    pkg.Service = Service

    c = pico_ioc.init(pkg)
    svc = c.get(Service)
    assert isinstance(svc.dep, DefaultImpl), "Service.dep should resolve to DefaultImpl via @on_missing"

def test_on_missing_is_ignored_if_regular_impl_exists():
    """
    If a regular implementation exists, defaults are ignored and Base aliases to the regular one.
    """
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
    assert isinstance(svc.dep, RealImpl), "Default must not override an active regular implementation"

def test_on_missing_with_factory_provides_method():
    """
    Default provided via @factory_component + @provides(Base) with @on_missing on the method (or its owner).
    """
    pkg = types.ModuleType("pkg_on_missing_3")

    class Base: ...
    @factory_component
    class F:
        def __init__(self):  # no deps
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
    # The factory-produced instance is an anonymous inner class named "Default"
    assert isinstance(svc.dep, Base), "Service.dep should resolve to Base via factory @on_missing"
    # sanity: Base must be bound (alias added) thanks to apply_defaults
    _ = c.get(Base)

