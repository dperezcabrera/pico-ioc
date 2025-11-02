import pytest
import contextvars
from collections import OrderedDict
from typing import Any

from pico_ioc.scope import (
    ContextVarScope,
    ComponentContainer,
    _NoCacheContainer,
    ScopeManager,
    ScopedCaches,
    ScopeProtocol,
)
from pico_ioc.exceptions import ScopeError
from pico_ioc.decorators import cleanup


class MockCleanup:
    def __init__(self):
        self.closed = False

    @cleanup
    def close(self):
        self.closed = True

class MockScope(ScopeProtocol):
    def __init__(self):
        self._id = None

    def get_id(self) -> Any | None:
        return self._id

    def set_id(self, val):
        self._id = val


@pytest.fixture
def test_var():
    return contextvars.ContextVar("test_var", default="default")

@pytest.fixture
def context_scope(test_var):
    return ContextVarScope(test_var)

@pytest.fixture
def scope_manager():
    return ScopeManager()

@pytest.fixture
def scoped_caches():
    return ScopedCaches(max_scopes_per_type=3)


def test_context_var_scope_get_id_default(context_scope):
    assert context_scope.get_id() == "default"

def test_context_var_scope_activate_deactivate(test_var, context_scope):
    assert test_var.get() == "default"
    
    token = context_scope.activate("new_value")
    assert test_var.get() == "new_value"
    assert context_scope.get_id() == "new_value"
    
    context_scope.deactivate(token)
    assert test_var.get() == "default"
    assert context_scope.get_id() == "default"

def test_component_container_put_get_items():
    container = ComponentContainer()
    obj1 = object()
    obj2 = object()
    
    container.put("key1", obj1)
    container.put("key2", obj2)
    
    assert container.get("key1") is obj1
    assert container.get("key2") is obj2
    
    items = container.items()
    assert ("key1", obj1) in items
    assert ("key2", obj2) in items
    assert len(items) == 2

def test_component_container_get_missing():
    container = ComponentContainer()
    assert container.get("missing_key") is None

def test_no_cache_container_put_get_items():
    container = _NoCacheContainer()
    obj1 = object()
    
    container.put("key1", obj1)
    
    assert container.get("key1") is None
    assert container.items() == []

def test_scope_manager_defaults(scope_manager):
    assert scope_manager.get_id("request") is None
    assert scope_manager.get_id("session") is None
    assert scope_manager.get_id("transaction") is None
    names = scope_manager.names()
    assert "request" in names
    assert "session" in names
    assert "transaction" in names
    assert "singleton" not in names
    assert "prototype" not in names

def test_scope_manager_register_custom_scope(scope_manager):
    scope_manager.register_scope("custom")
    assert "custom" in scope_manager.names()
    assert isinstance(scope_manager._scopes["custom"], ContextVarScope)

def test_scope_manager_register_errors(scope_manager):
    with pytest.raises(ScopeError, match="non-empty string"):
        scope_manager.register_scope("")
        
    with pytest.raises(ScopeError, match="reserved scope"):
        scope_manager.register_scope("singleton")
        
    with pytest.raises(ScopeError, match="reserved scope"):
        scope_manager.register_scope("prototype")

def test_scope_manager_get_id_reserved(scope_manager):
    assert scope_manager.get_id("singleton") is None
    assert scope_manager.get_id("prototype") is None

def test_scope_manager_activate_deactivate_default(scope_manager):
    assert scope_manager.get_id("request") is None
    token = scope_manager.activate("request", "req-123")
    assert scope_manager.get_id("request") == "req-123"
    scope_manager.deactivate("request", token)
    assert scope_manager.get_id("request") is None

def test_scope_manager_activate_unknown_scope_raises(scope_manager):
    with pytest.raises(ScopeError, match="Unknown scope: unknown"):
        scope_manager.activate("unknown", "id")

def test_scope_manager_deactivate_unknown_scope_raises(scope_manager):
    with pytest.raises(ScopeError, match="Unknown scope: unknown"):
        scope_manager.deactivate("unknown", None)

def test_scope_manager_activate_deactivate_reserved(scope_manager):
    token_s = scope_manager.activate("singleton", "id")
    assert token_s is None
    scope_manager.deactivate("singleton", None)
    
    token_p = scope_manager.activate("prototype", "id")
    assert token_p is None
    scope_manager.deactivate("prototype", None)

def test_scope_manager_signatures(scope_manager):
    assert scope_manager.signature(("request", "session")) == (None, None)
    assert scope_manager.signature_all() == (None, None, None, None)
    
    t1 = scope_manager.activate("request", "r1")
    t2 = scope_manager.activate("session", "s1")
    
    assert scope_manager.signature(("request", "session")) == ("r1", "s1")
    assert scope_manager.signature_all() == ("r1", "s1", None, None)
    
    scope_manager.deactivate("request", t1)
    scope_manager.deactivate("session", t2)
    
    assert scope_manager.signature_all() == (None, None, None, None)

def test_scoped_caches_for_scope_singleton(scoped_caches, scope_manager):
    c1 = scoped_caches.for_scope(scope_manager, "singleton")
    c2 = scoped_caches.for_scope(scope_manager, "singleton")
    assert c1 is c2
    assert c1 is scoped_caches._singleton

def test_scoped_caches_for_scope_prototype(scoped_caches, scope_manager):
    c1 = scoped_caches.for_scope(scope_manager, "prototype")
    c2 = scoped_caches.for_scope(scope_manager, "prototype")
    assert c1 is c2
    assert c1 is scoped_caches._no_cache
    assert isinstance(c1, _NoCacheContainer)

def test_scoped_caches_for_scope_custom_id(scoped_caches, scope_manager):
    t1 = scope_manager.activate("request", "req-1")
    c1 = scoped_caches.for_scope(scope_manager, "request")
    c1_again = scoped_caches.for_scope(scope_manager, "request")
    scope_manager.deactivate("request", t1)
    
    assert c1 is c1_again
    assert isinstance(c1, ComponentContainer)
    
    t2 = scope_manager.activate("request", "req-2")
    c2 = scoped_caches.for_scope(scope_manager, "request")
    scope_manager.deactivate("request", t2)
    
    assert c1 is not c2

def test_scoped_caches_lru_eviction(scoped_caches, scope_manager):
    scope_name = "request"
    assert scoped_caches._max == 3
    
    t1 = scope_manager.activate(scope_name, "id-1")
    c1 = scoped_caches.for_scope(scope_manager, scope_name)
    scope_manager.deactivate(scope_name, t1)
    
    t2 = scope_manager.activate(scope_name, "id-2")
    c2 = scoped_caches.for_scope(scope_manager, scope_name)
    scope_manager.deactivate(scope_name, t2)
    
    t3 = scope_manager.activate(scope_name, "id-3")
    c3 = scoped_caches.for_scope(scope_manager, scope_name)
    scope_manager.deactivate(scope_name, t3)
    
    bucket = scoped_caches._by_scope[scope_name]
    assert len(bucket) == 3
    assert list(bucket.keys()) == ["id-1", "id-2", "id-3"] 
    
    t4 = scope_manager.activate(scope_name, "id-4")
    c4 = scoped_caches.for_scope(scope_manager, scope_name)
    scope_manager.deactivate(scope_name, t4)
    
    assert len(bucket) == 3
    assert list(bucket.keys()) == ["id-2", "id-3", "id-4"]
    assert "id-1" not in bucket

def test_scoped_caches_lru_reordering(scoped_caches, scope_manager):
    scope_name = "request"
    
    t1 = scope_manager.activate(scope_name, "id-1"); scoped_caches.for_scope(scope_manager, scope_name); scope_manager.deactivate(scope_name, t1)
    t2 = scope_manager.activate(scope_name, "id-2"); scoped_caches.for_scope(scope_manager, scope_name); scope_manager.deactivate(scope_name, t2)
    t3 = scope_manager.activate(scope_name, "id-3"); scoped_caches.for_scope(scope_manager, scope_name); scope_manager.deactivate(scope_name, t3)
    
    bucket = scoped_caches._by_scope[scope_name]
    assert list(bucket.keys()) == ["id-1", "id-2", "id-3"]

    t1_again = scope_manager.activate(scope_name, "id-1")
    scoped_caches.for_scope(scope_manager, scope_name)
    scope_manager.deactivate(scope_name, t1_again)

    assert list(bucket.keys()) == ["id-2", "id-3", "id-1"]
    
    t4 = scope_manager.activate(scope_name, "id-4")
    c4 = scoped_caches.for_scope(scope_manager, scope_name)
    scope_manager.deactivate(scope_name, t4)

    assert list(bucket.keys()) == ["id-3", "id-1", "id-4"] 
    assert "id-2" not in bucket

def test_scoped_caches_all_items(scoped_caches, scope_manager):
    singleton_obj = object()
    scoped_obj_1 = object()
    scoped_obj_2 = object()
    
    c_singleton = scoped_caches.for_scope(scope_manager, "singleton")
    c_singleton.put("s_key", singleton_obj)
    
    t1 = scope_manager.activate("request", "r1")
    c_req1 = scoped_caches.for_scope(scope_manager, "request")
    c_req1.put("r_key1", scoped_obj_1)
    scope_manager.deactivate("request", t1)
    
    t2 = scope_manager.activate("session", "s1")
    c_sess1 = scoped_caches.for_scope(scope_manager, "session")
    c_sess1.put("s_key1", scoped_obj_2)
    scope_manager.deactivate("session", t2)
    
    all_items = list(scoped_caches.all_items())
    assert len(all_items) == 3
    found_items = set(all_items)
    assert ("s_key", singleton_obj) in found_items
    assert ("r_key1", scoped_obj_1) in found_items
    assert ("s_key1", scoped_obj_2) in found_items

def test_scoped_caches_shrink(scoped_caches, scope_manager):
    scope_name = "request"
    
    t1 = scope_manager.activate(scope_name, "id-1"); scoped_caches.for_scope(scope_manager, scope_name); scope_manager.deactivate(scope_name, t1)
    t2 = scope_manager.activate(scope_name, "id-2"); scoped_caches.for_scope(scope_manager, scope_name); scope_manager.deactivate(scope_name, t2)
    t3 = scope_manager.activate(scope_name, "id-3"); scoped_caches.for_scope(scope_manager, scope_name); scope_manager.deactivate(scope_name, t3)
    
    bucket = scoped_caches._by_scope[scope_name]
    assert len(bucket) == 3
    
    scoped_caches.shrink(scope_name, 2)
    
    assert len(bucket) == 2
    assert list(bucket.keys()) == ["id-2", "id-3"]

def test_scoped_caches_cleanup_scope(scoped_caches, scope_manager):
    scope_name = "request"
    obj1 = MockCleanup()
    obj2 = MockCleanup()
    
    t1 = scope_manager.activate(scope_name, "id-1")
    c1 = scoped_caches.for_scope(scope_manager, scope_name)
    c1.put("obj1", obj1)
    scope_manager.deactivate(scope_name, t1)
    
    t2 = scope_manager.activate(scope_name, "id-2")
    c2 = scoped_caches.for_scope(scope_manager, scope_name)
    c2.put("obj2", obj2)
    scope_manager.deactivate(scope_name, t2)
    
    assert obj1.closed is False
    assert obj2.closed is False
    assert "id-1" in scoped_caches._by_scope[scope_name]
    assert "id-2" in scoped_caches._by_scope[scope_name]
    
    scoped_caches.cleanup_scope(scope_name, "id-1")
    
    assert obj1.closed is True
    assert obj2.closed is False
    assert "id-1" not in scoped_caches._by_scope[scope_name]
    assert "id-2" in scoped_caches._by_scope[scope_name]
