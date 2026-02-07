import contextvars

import pytest

from pico_ioc.decorators import cleanup
from pico_ioc.exceptions import ScopeError
from pico_ioc.scope import ContextVarScope, ScopedCaches, ScopeManager


@pytest.fixture
def scope_manager():
    sm = ScopeManager()
    return sm

@pytest.fixture
def scoped_caches():
    return ScopedCaches()

def test_singleton_scope_is_always_same(scoped_caches, scope_manager):
    c1 = scoped_caches.for_scope(scope_manager, "singleton")
    c2 = scoped_caches.for_scope(scope_manager, "singleton")
    assert c1 is c2
    c1.put("key", "value")
    assert c2.get("key") == "value"

def test_prototype_scope_container_is_sentinel(scoped_caches, scope_manager):
    c1 = scoped_caches.for_scope(scope_manager, "prototype")
    c2 = scoped_caches.for_scope(scope_manager, "prototype")
    assert c1 is c2
    c1.put("key", "value")
    assert c2.get("key") is None

def test_request_scope_different_ids(scoped_caches, scope_manager):
    scope_name = "request"
    
    t1 = scope_manager.activate(scope_name, "req-1")
    c1 = scoped_caches.for_scope(scope_manager, scope_name)
    c1.put("a", 1)
    scope_manager.deactivate(scope_name, t1)

    t2 = scope_manager.activate(scope_name, "req-2")
    c2 = scoped_caches.for_scope(scope_manager, scope_name)
    c2.put("a", 2)
    scope_manager.deactivate(scope_name, t2)

    t1_again = scope_manager.activate(scope_name, "req-1")
    c1_again = scoped_caches.for_scope(scope_manager, scope_name)
    scope_manager.deactivate(scope_name, t1_again)

    assert c1 is not c2
    assert c1 is c1_again
    assert c1.get("a") == 1
    assert c2.get("a") == 2

def test_scoped_caches_no_limit_growth(scoped_caches, scope_manager):
    scope_name = "request"
    
    for i in range(10):
        sid = f"id-{i}"
        token = scope_manager.activate(scope_name, sid)
        scoped_caches.for_scope(scope_manager, scope_name)
        scope_manager.deactivate(scope_name, token)
    
    bucket = scoped_caches._by_scope[scope_name]
    assert len(bucket) == 10
    assert "id-0" in bucket
    assert "id-9" in bucket

def test_explicit_cleanup_removes_entry(scoped_caches, scope_manager):
    scope_name = "request"
    sid = "id-to-remove"
    
    t = scope_manager.activate(scope_name, sid)
    c = scoped_caches.for_scope(scope_manager, scope_name)
    c.put("key", "val")
    scope_manager.deactivate(scope_name, t)
    
    assert sid in scoped_caches._by_scope[scope_name]
    
    scoped_caches.cleanup_scope(scope_name, sid)
    
    assert sid not in scoped_caches._by_scope[scope_name]

def test_access_scope_without_active_id_raises_security_error(scoped_caches, scope_manager):
    scope_name = "request"
    
    # No activamos el scope
    with pytest.raises(ScopeError) as e:
        scoped_caches.for_scope(scope_manager, scope_name)
    
    assert "No active scope ID found" in str(e.value)

def test_custom_scope_registration():
    sm = ScopeManager()
    sm.register_scope("tenant")
    assert "tenant" in sm.names()
    
    token = sm.activate("tenant", "t-1")
    assert sm.get_id("tenant") == "t-1"
    sm.deactivate("tenant", token)
    assert sm.get_id("tenant") is None

def test_cannot_register_reserved_scopes():
    sm = ScopeManager()
    with pytest.raises(ScopeError):
        sm.register_scope("singleton")
    with pytest.raises(ScopeError):
        sm.register_scope("prototype")

def test_cleanup_triggers_lifecycle_methods():
    class CompliantComponent:
        def __init__(self):
            self.cleaned = False
        
        @cleanup
        def shutdown(self):
            self.cleaned = True
    
    obj = CompliantComponent()
    
    caches = ScopedCaches()
    sm = ScopeManager()
    
    t = sm.activate("request", "req-1")
    container = caches.for_scope(sm, "request")
    container.put("my-comp", obj)
    sm.deactivate("request", t)
    
    assert obj.cleaned is False
    caches.cleanup_scope("request", "req-1")
    assert obj.cleaned is True
