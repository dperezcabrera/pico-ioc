"""Lifecycle scans must not evaluate properties: third-party objects may raise from one."""

from pico_ioc import cleanup, component, configure, factory, health, init, provides


class Vendor:
    @property
    def lazy(self):
        raise RuntimeError("only available after setup")


@factory
class VendorFactory:
    @provides(Vendor)
    def make(self) -> Vendor:
        return Vendor()


@component
class Service:
    events: list = []

    @property
    def broken(self):
        raise RuntimeError("never touch me")

    @configure
    def setup(self):
        Service.events.append("configure")

    @health
    def alive(self) -> bool:
        return True

    @cleanup
    def close(self):
        Service.events.append("cleanup")


def test_container_survives_objects_with_raising_properties():
    import sys

    Service.events = []
    container = init(modules=[sys.modules[__name__]])
    assert isinstance(container.get(Vendor), Vendor)
    container.get(Service)
    assert container.health_check() == {"Service.alive": True}
    container.cleanup_all()
    assert Service.events == ["configure", "cleanup"]
