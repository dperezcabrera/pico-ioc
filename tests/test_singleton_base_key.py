"""Regression tests for issue #20: singleton identity when resolving by base class."""

from abc import ABC

from pico_ioc import component, init


class Base(ABC):
    pass


@component(primary=True, lazy=True)
class PrimaryImpl(Base):
    pass


@component(lazy=True)
class OtherImpl(Base):
    pass


@component(lazy=True)
class Consumer:
    def __init__(self, dep: Base):
        self.dep = dep


def _container():
    return init(modules=[__name__])


def test_get_by_base_class_twice_returns_same_instance():
    container = _container()
    assert container.get(Base) is container.get(Base)


def test_get_by_base_class_and_by_concrete_class_share_the_singleton():
    container = _container()
    by_base = container.get(Base)
    assert container.get(PrimaryImpl) is by_base


def test_injected_dependency_is_the_same_singleton():
    container = _container()
    assert container.get(Consumer).dep is container.get(Base)


def test_non_primary_impl_keeps_its_own_singleton():
    container = _container()
    assert container.get(OtherImpl) is container.get(OtherImpl)
    assert container.get(OtherImpl) is not container.get(Base)


def test_has_resolves_base_class():
    container = _container()
    assert container.has(Base)
