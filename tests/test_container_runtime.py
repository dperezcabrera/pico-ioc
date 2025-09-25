import pytest
import asyncio
from pico_ioc import init, component, PicoContainer, ScopeError

@component
class SimpleA:
    pass

@component
class SimpleB:
    pass

@component
class NeedsSimpleA:
    def __init__(self, a: SimpleA):
        self.a = a

class RedisCache:
    pass

class InMemoryCache:
    pass

@component(name="Cache")
class ProdCache(RedisCache):
    pass

@component(name="Cache")
class DevCache(InMemoryCache):
    pass

@component
class AsyncService:
    def __init__(self):
        self.container_id = PicoContainer.get_current_id()

def test_container_id_uniqueness():
    c1 = init(modules=[__name__])
    c2 = init(modules=[__name__])
    assert c1.container_id != c2.container_id
    c1.shutdown()
    c2.shutdown()

def test_container_context_isolation():
    c1 = init(modules=[__name__], profiles=("prod",), container_id="test-prod")
    c2 = init(modules=[__name__], profiles=("dev",), container_id="test-dev")
    with c1.as_current():
        assert PicoContainer.get_current_id() == c1.container_id
        service1 = c1.get(NeedsSimpleA)
    with c2.as_current():
        assert PicoContainer.get_current_id() == c2.container_id
        service2 = c2.get(NeedsSimpleA)
    assert service1 is not service2
    c1.shutdown()
    c2.shutdown()

def test_nested_context_managers():
    c1 = init(modules=[__name__])
    c2 = init(modules=[__name__])
    with c1.as_current():
        assert PicoContainer.get_current() is c1
        with c2.as_current():
            assert PicoContainer.get_current() is c2
        assert PicoContainer.get_current() is c1
    c1.shutdown()
    c2.shutdown()

def test_container_stats():
    container = init(modules=[__name__])
    with container.as_current():
        container.get(SimpleA)
        container.get(SimpleA)
        container.get(SimpleB)
    stats = container.stats()
    assert stats["total_resolves"] == 2
    assert stats["cache_hits"] == 1
    assert stats["cache_hit_rate"] == 1 / 3
    container.shutdown()

def test_container_shutdown_cleanup():
    container = init(modules=[__name__], container_id="test-shutdown")
    assert "test-shutdown" in PicoContainer.all_containers()
    container.shutdown()
    assert "test-shutdown" not in PicoContainer.all_containers()

async def async_helper_function():
    current = PicoContainer.get_current()
    if not current:
        raise RuntimeError("No active container context")
    service = await current.aget(AsyncService)
    return service

@pytest.mark.asyncio
async def test_async_context_preservation():
    container = init(modules=[__name__])
    result_service = None
    with container.as_current():
        result_service = await async_helper_function()
    assert result_service is not None
    assert result_service.container_id == container.container_id
    container.shutdown()

