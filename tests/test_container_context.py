# tests/test_container_context.py
import types
import pytest
from pico_ioc import init, PicoContainer

def _empty_module(name: str = "ctx_mod"):
    return types.ModuleType(name)

def test_container_id_unique():
    c1 = init(_empty_module("m1"))
    c2 = init(_empty_module("m2"))
    assert isinstance(c1.container_id, str) and c1.container_id
    assert isinstance(c2.container_id, str) and c2.container_id
    assert c1.container_id != c2.container_id

def test_as_current_context_manager():
    c = init(_empty_module("m_ctx"))
    assert PicoContainer.get_current() is None
    with c.as_current():
        cur = PicoContainer.get_current()
        assert cur is c
        assert PicoContainer.get_current_id() == c.container_id
    assert PicoContainer.get_current() is None
    assert PicoContainer.get_current_id() is None

def test_activate_and_deactivate_methods():
    c = init(_empty_module("m_ctx2"))
    token = c.activate()
    try:
        assert PicoContainer.get_current() is c
        assert PicoContainer.get_current_id() == c.container_id
    finally:
        c.deactivate(token)
    assert PicoContainer.get_current() is None

def test_all_containers_registry_contains_instances():
    c1 = init(_empty_module("m3"))
    c2 = init(_empty_module("m4"))
    reg = PicoContainer.all_containers()
    assert c1.container_id in reg and reg[c1.container_id] is c1
    assert c2.container_id in reg and reg[c2.container_id] is c2

def test_stats_contains_container_id_and_profiles():
    c = init(_empty_module("m_stats"), profiles=("dev",))
    st = c.stats()
    assert st["container_id"] == c.container_id
    assert tuple(st["profiles"]) == ("dev",)
    assert isinstance(st["total_resolves"], int)
    assert isinstance(st["cache_hits"], int)
    assert "registered_components" in st

