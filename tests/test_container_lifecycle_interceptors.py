# tests/test_container_lifecycle_interceptors.py
import types

def test_container_lifecycle_interceptors():
    import pico_ioc
    from pico_ioc import component, interceptor
    from pico_ioc.interceptors import ContainerInterceptor

    events = []

    @interceptor(kind="container")
    class T(ContainerInterceptor):
        def on_resolve(self, k, a, q): events.append(("res", k))
        def on_before_create(self, k): events.append(("before", k))
        def on_after_create(self, k, inst): events.append(("after", k)); return inst
        def on_exception(self, k, exc): events.append(("err", k))

    pkg = types.ModuleType("pkg_lifecycle")

    @component
    class Dep:
        pass

    @component
    class Service:
        def __init__(self, dep: Dep):
            self.dep = dep

    pkg.Dep = Dep
    pkg.Service = Service
    pkg.T = T  # make interceptor discoverable by scanner

    c = pico_ioc.init(pkg)

    _ = c.get(Service)  # force creation

    assert ("before", Service) in events
    assert ("after", Service) in events
    assert any(e[0] == "res" for e in events)


def test_container_accepts_interceptors_via_add_method():
    from pico_ioc.container import PicoContainer
    from pico_ioc.interceptors import ContainerInterceptor

    class CI(ContainerInterceptor):
        def on_resolve(self, *a, **k): pass
        def on_before_create(self, *a, **k): pass
        def on_after_create(self, *a, **k): return None
        def on_exception(self, *a, **k): pass

    c = PicoContainer()
    c.add_container_interceptor(CI())

