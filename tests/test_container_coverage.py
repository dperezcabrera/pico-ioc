import contextvars

import pytest

from pico_ioc import ComponentFactory, PicoContainer, ScopedCaches, ScopeManager, health
from pico_ioc.exceptions import AsyncResolutionError
from pico_ioc.locator import ComponentLocator


def test_container_ashutdown():
    c = PicoContainer(ComponentFactory(), ScopedCaches(), ScopeManager())

    async def run():
        await c.ashutdown()
        assert c.container_id not in PicoContainer.all_containers()

    import asyncio

    asyncio.run(run())


def test_export_graph_no_locator():
    c = PicoContainer(ComponentFactory(), ScopedCaches(), ScopeManager())
    with pytest.raises(RuntimeError, match="No locator attached"):
        c.export_graph("out.dot")


def test_resolve_args_edge_cases():
    c = PicoContainer(ComponentFactory(), ScopedCaches(), ScopeManager())
    assert c._resolve_args(()) == {}

    locator = ComponentLocator({}, {})
    c.attach_locator(locator)
    assert c._resolve_args(()) == {}


def test_info_logging(caplog):
    c = PicoContainer(ComponentFactory(), ScopedCaches(), ScopeManager())
    with caplog.at_level("INFO"):
        c.info("test message")
    assert "test message" in caplog.text


def test_scope_context_manager():
    c = PicoContainer(ComponentFactory(), ScopedCaches(), ScopeManager())

    with c.scope("request", "req-1"):
        assert c.scopes.get_id("request") == "req-1"

    assert c.scopes.get_id("request") is None


def test_health_check_exception():
    c = PicoContainer(ComponentFactory(), ScopedCaches(), ScopeManager())

    class Unhealthy:
        # FIX: Use decorator
        @health
        def check(self):
            raise ValueError("fail")

    obj = Unhealthy()
    c._caches._singleton.put("key", obj)

    res = c.health_check()
    assert res["key.check"] is False
