import contextvars

import pytest

from pico_ioc import cleanup
from pico_ioc.exceptions import ScopeError
from pico_ioc.scope import ComponentContainer, ScopedCaches, ScopeManager


def test_scope_manager_validation():
    manager = ScopeManager()

    with pytest.raises(ScopeError, match="non-empty"):
        manager.register_scope("")

    with pytest.raises(ScopeError, match="reserved"):
        manager.register_scope("singleton")

    manager.register_scope("request")
    manager.register_scope("request")


def test_scope_manager_reserved_interactions():
    manager = ScopeManager()

    assert manager.get_id("singleton") is None
    assert manager.activate("singleton", "id") is None
    assert manager.deactivate("singleton", None) is None


def test_scope_manager_unknown_scope():
    manager = ScopeManager()

    with pytest.raises(ScopeError, match="Unknown scope"):
        manager.deactivate("unknown_scope", None)

    with pytest.raises(ScopeError, match="Unknown scope"):
        manager.activate("unknown_scope", "id")


def test_scoped_caches_shrink():
    caches = ScopedCaches()
    manager = ScopeManager()

    caches.shrink("singleton", 10)

    scope_name = "request"
    manager.activate(scope_name, "req1")

    c1 = caches.for_scope(manager, scope_name)

    caches._by_scope[scope_name] = {"req1": ComponentContainer(), "req2": ComponentContainer()}

    caches.shrink(scope_name, 1)
    assert len(caches._by_scope[scope_name]) == 1


def test_cleanup_container_exceptions():
    caches = ScopedCaches()
    container = ComponentContainer()

    class BrokenCleanup:
        @cleanup
        def cleanup(self):
            raise ValueError("Boom")

    obj = BrokenCleanup()
    container.put("key", obj)

    caches._cleanup_container(container)
