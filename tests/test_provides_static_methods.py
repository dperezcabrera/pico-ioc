# tests/test_provides_static_methods.py
import types

from pico_ioc.api import component, factory, init, provides


class Service:
    pass

class Dep:
    pass

class Impl(Service):
    def __init__(self, dep: Dep) -> None:
        self.dep = dep

def build_module_with_staticmethod_provides():
    m = types.ModuleType("factory_staticmethod_provides")

    @component
    class MyDep(Dep):
        pass

    @factory
    class MyFactory:
        @staticmethod
        @provides(Service)
        def build(dep: Dep) -> Service:
            return Impl(dep)

    setattr(m, "MyDep", MyDep)
    setattr(m, "MyFactory", MyFactory)
    return m

def test_factory_staticmethod_provides_binds_and_injects():
    mod = build_module_with_staticmethod_provides()
    pico = init(mod)
    s = pico.get(Service)
    assert isinstance(s, Impl)
    assert isinstance(s.dep, Dep)

