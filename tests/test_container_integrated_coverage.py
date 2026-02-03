"""
Integrated tests to boost container.py coverage to 95%+.
These tests use real registered components to cover edge cases.
"""
import asyncio
import tempfile
import os
import pytest
from typing import List, Dict, Any, Type, Protocol

from pico_ioc import init, component, factory, provides, configure, cleanup
from pico_ioc.container import PicoContainer
from pico_ioc.aop import intercepted_by, MethodInterceptor, MethodCtx
from pico_ioc.exceptions import AsyncResolutionError, ProviderNotFoundError


# ============================================================
# Module-level components for integrated tests
# ============================================================

# --- Simple services ---

@component()
class SimpleService:
    """Simple service for basic tests."""
    def value(self) -> str:
        return "simple"


@component(name="named_alpha")
class NamedAlpha:
    """Named service A."""
    def name(self) -> str:
        return "alpha"


@component(name="named_beta")
class NamedBeta:
    """Named service B."""
    def name(self) -> str:
        return "beta"


# --- Request-scoped service with sync configure ---

@component(scope="request")
class RequestScopedService:
    """Request-scoped service with sync configure."""
    setup_count: int = 0

    @configure
    def setup(self):
        RequestScopedService.setup_count += 1


# --- Factory class ---

@factory
class TestServiceFactory:
    """Factory that creates services."""

    @provides
    def create_string_service(self) -> str:
        return "factory_created"


# --- Service with qualifiers for export_graph tests ---

@component(qualifiers={"env:prod"})
class ProdConfig:
    """Production config with qualifier."""
    pass


@component(qualifiers={"env:dev"})
class DevConfig:
    """Development config with qualifier."""
    pass


# ============================================================
# Integrated Tests
# ============================================================

class TestRequestScopedWithSyncConfigure:
    """Test request-scoped services with sync configure - covers lines 242-246."""

    def test_get_request_scoped_sync_configure(self):
        """get() handles request-scoped service with sync @configure."""
        RequestScopedService.setup_count = 0

        container = init(modules=[__name__])
        try:
            with container.scope("request", "req-1"):
                service = container.get(RequestScopedService)
                assert service is not None

            # Setup should have been called
            assert RequestScopedService.setup_count >= 1
        finally:
            container.shutdown()

    def test_multiple_request_scopes_call_configure_each_time(self):
        """Each request scope creates new instance and calls configure."""
        RequestScopedService.setup_count = 0

        container = init(modules=[__name__])
        try:
            with container.scope("request", "req-1"):
                s1 = container.get(RequestScopedService)

            with container.scope("request", "req-2"):
                s2 = container.get(RequestScopedService)

            # Configure should have been called twice (different scopes)
            assert RequestScopedService.setup_count >= 2
        finally:
            container.shutdown()


class TestExportGraphWithOptions:
    """Test export_graph with various options - covers lines 425-429."""

    def test_export_graph_with_scopes(self):
        """export_graph includes scope info when include_scopes=True."""
        container = init(modules=[__name__])
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.dot', delete=False) as f:
                path = f.name

            container.export_graph(path, include_scopes=True)

            with open(path, 'r') as f:
                content = f.read()

            assert 'digraph Pico' in content
            # Should contain scope info
            assert 'scope=' in content

            os.unlink(path)
        finally:
            container.shutdown()

    def test_export_graph_with_qualifiers(self):
        """export_graph includes qualifier info when include_qualifiers=True."""
        container = init(modules=[__name__])
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.dot', delete=False) as f:
                path = f.name

            container.export_graph(path, include_qualifiers=True)

            with open(path, 'r') as f:
                content = f.read()

            assert 'digraph Pico' in content
            # Should contain qualifier info for ProdConfig/DevConfig
            assert 'env' in content.lower() or '⟨' in content

            os.unlink(path)
        finally:
            container.shutdown()

    def test_export_graph_with_both_options(self):
        """export_graph works with both scopes and qualifiers."""
        container = init(modules=[__name__])
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.dot', delete=False) as f:
                path = f.name

            container.export_graph(path, include_scopes=True, include_qualifiers=True)

            with open(path, 'r') as f:
                content = f.read()

            assert 'digraph Pico' in content

            os.unlink(path)
        finally:
            container.shutdown()


class TestFactoryClassIteration:
    """Test factory class iteration during cleanup."""

    def test_container_iterates_factory_classes(self):
        """cleanup_all iterates factory classes."""
        container = init(modules=[__name__])
        try:
            # Get something from the factory
            result = container.get(str)
            assert result == "factory_created"

            # Now cleanup should iterate factory classes
            container.cleanup_all()
        finally:
            container.shutdown()


class TestResolutionWithNamedKey:
    """Test resolution using pico_name."""

    def test_resolve_by_name(self):
        """Container resolves components by their pico_name."""
        container = init(modules=[__name__])
        try:
            # NamedAlpha has name="named_alpha"
            service = container.get("named_alpha")
            assert isinstance(service, NamedAlpha)
        finally:
            container.shutdown()

class TestStatsCacheHitRate:
    """Test stats cache hit rate calculation."""

    def test_stats_with_cache_hits(self):
        """stats() shows correct cache hit rate after multiple resolves."""
        container = init(modules=[__name__])
        try:
            # First resolve - miss
            container.get(SimpleService)
            # Second resolve - hit
            container.get(SimpleService)
            # Third resolve - hit
            container.get(SimpleService)

            stats = container.stats()

            assert stats["cache_hits"] >= 2
            assert stats["cache_hit_rate"] > 0.0
        finally:
            container.shutdown()


class TestProviderNotFoundReRaise:
    """Test ProviderNotFoundError re-raise - covers line 191."""

    def test_provider_not_found_propagates(self):
        """ProviderNotFoundError is properly re-raised."""
        container = init(modules=[])
        try:
            class UnknownService:
                pass

            with pytest.raises(ProviderNotFoundError):
                container.get(UnknownService)
        finally:
            container.shutdown()


class TestCanonicalKeyBranches:
    """Test _canonical_key with different inputs."""

    def test_canonical_key_with_type(self):
        """_canonical_key works with type keys."""
        container = init(modules=[__name__])
        try:
            # Should resolve type to itself
            key = container._canonical_key(SimpleService)
            assert key is SimpleService
        finally:
            container.shutdown()

    def test_canonical_key_unknown_string(self):
        """_canonical_key returns unknown string as-is."""
        container = init(modules=[__name__])
        try:
            key = container._canonical_key("nonexistent_name")
            assert key == "nonexistent_name"
        finally:
            container.shutdown()


# ============================================================
# Async Tests
# ============================================================

class TestAsyncOperations:
    """Test async container operations."""

    @pytest.mark.asyncio
    async def test_aget_on_normal_singleton(self):
        """aget() works on normal singletons."""
        container = init(modules=[__name__])
        try:
            service = await container.aget(SimpleService)
            assert service is not None
            assert service.value() == "simple"
        finally:
            await container.ashutdown()

    @pytest.mark.asyncio
    async def test_aget_returns_cached_service(self):
        """aget() returns cached service on second call."""
        container = init(modules=[__name__])
        try:
            # First call - creates and caches
            service1 = await container.aget(SimpleService)
            # Second call - returns cached
            service2 = await container.aget(SimpleService)

            assert service1 is service2
        finally:
            await container.ashutdown()

    @pytest.mark.asyncio
    async def test_ashutdown_completes(self):
        """ashutdown() completes cleanup properly."""
        container = init(modules=[__name__])

        # Resolve some services
        await container.aget(SimpleService)

        # ashutdown should complete
        await container.ashutdown()

        assert container.container_id not in PicoContainer._container_registry


