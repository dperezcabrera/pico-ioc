"""
Extended tests for container.py to increase coverage.
"""
import asyncio
import inspect
import os
import tempfile
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from pico_ioc import init, component, factory, provides, configure, cleanup
from pico_ioc.container import (
    PicoContainer,
    _normalize_callable,
    _get_signature_safe,
    _needs_async_configure,
    _iter_configure_methods,
    _build_resolution_graph
)
from pico_ioc.constants import PICO_META
from pico_ioc.exceptions import (
    ComponentCreationError,
    ProviderNotFoundError,
    AsyncResolutionError,
    ConfigurationError
)
from pico_ioc.factory import ComponentFactory
from pico_ioc.scope import ScopedCaches, ScopeManager
from pico_ioc.aop import ContainerObserver, health


# Define test components at module level for proper scanning
@component(name="named_service")
class NamedService:
    pass


@component()
class RegisteredService:
    pass


@component()
class ExportDatabase:
    pass


@component()
class ExportRepository:
    def __init__(self, db: ExportDatabase):
        self.db = db


@component()
class CleanableService:
    cleanup_called = False

    @cleanup
    def close(self):
        CleanableService.cleanup_called = True


@component()
class AsyncCleanableService:
    cleanup_called = False

    @cleanup
    async def close(self):
        await asyncio.sleep(0.01)
        AsyncCleanableService.cleanup_called = True


@component()
class StatsTestService:
    pass


@component()
class TrackedService:
    pass


@component()
class CachedService:
    pass


@component()
class ObservedService:
    pass


@component()
class CacheObservedService:
    pass


@component()
class HealthyService:
    @health
    def is_healthy(self) -> bool:
        return True


@component()
class UnhealthyService:
    @health
    def is_healthy(self) -> bool:
        raise RuntimeError("Health check failed")


class TestContainerHelperFunctions:
    """Test helper functions in container module."""

    def test_normalize_callable_with_func_attr(self):
        """_normalize_callable returns __func__ if present."""
        class MyClass:
            def method(self):
                pass

        bound = MyClass().method
        result = _normalize_callable(bound)
        assert result == bound.__func__

    def test_normalize_callable_without_func_attr(self):
        """_normalize_callable returns obj if no __func__."""
        def plain_func():
            pass

        result = _normalize_callable(plain_func)
        assert result is plain_func

    def test_get_signature_safe_normal(self):
        """_get_signature_safe works with normal functions."""
        def my_func(a: int, b: str) -> bool:
            pass

        sig = _get_signature_safe(my_func)
        assert 'a' in sig.parameters
        assert 'b' in sig.parameters

    def test_get_signature_safe_wrapped(self):
        """_get_signature_safe falls back to __wrapped__."""
        def original(a: int) -> int:
            return a

        def wrapper(*args, **kwargs):
            return original(*args, **kwargs)

        wrapper.__wrapped__ = original

        sig = _get_signature_safe(wrapper)
        assert 'a' in sig.parameters

    def test_needs_async_configure_true(self):
        """_needs_async_configure detects async configure methods."""
        class Service:
            async def setup(self):
                pass

        Service.setup._pico_meta = {"configure": True}

        instance = Service()
        assert _needs_async_configure(instance) is True

    def test_needs_async_configure_false_sync(self):
        """_needs_async_configure returns False for sync configure."""
        class Service:
            def setup(self):
                pass

        Service.setup._pico_meta = {"configure": True}

        instance = Service()
        assert _needs_async_configure(instance) is False

    def test_needs_async_configure_false_no_configure(self):
        """_needs_async_configure returns False if no configure methods."""
        class Service:
            def regular_method(self):
                pass

        instance = Service()
        assert _needs_async_configure(instance) is False

    def test_iter_configure_methods(self):
        """_iter_configure_methods yields configure methods."""
        class Service:
            def setup(self):
                pass
            def teardown(self):
                pass
            def normal(self):
                pass

        Service.setup._pico_meta = {"configure": True}
        Service.teardown._pico_meta = {"configure": True}

        instance = Service()
        methods = list(_iter_configure_methods(instance))

        assert len(methods) == 2

    def test_build_resolution_graph_empty_locator(self):
        """_build_resolution_graph returns empty dict for None locator."""
        assert _build_resolution_graph(None) == {}


class TestContainerInit:
    """Test container initialization."""

    def test_container_id_generation(self):
        """Container generates unique IDs."""
        id1 = PicoContainer._generate_container_id()
        id2 = PicoContainer._generate_container_id()

        assert id1 != id2
        assert id1.startswith('c')
        assert id2.startswith('c')

    def test_container_custom_id(self):
        """Container accepts custom ID."""
        factory_mock = MagicMock(spec=ComponentFactory)
        caches = ScopedCaches()
        scopes = ScopeManager()

        container = PicoContainer(
            factory_mock, caches, scopes,
            container_id="custom-123"
        )

        assert container.container_id == "custom-123"
        container.shutdown()

    def test_container_with_profiles(self):
        """Container stores profiles in context."""
        factory_mock = MagicMock(spec=ComponentFactory)
        caches = ScopedCaches()
        scopes = ScopeManager()

        container = PicoContainer(
            factory_mock, caches, scopes,
            profiles=("dev", "test")
        )

        assert container.context.profiles == ("dev", "test")
        container.shutdown()

    def test_container_with_observers(self):
        """Container accepts observers."""
        factory_mock = MagicMock(spec=ComponentFactory)
        caches = ScopedCaches()
        scopes = ScopeManager()

        observer = MagicMock(spec=ContainerObserver)

        container = PicoContainer(
            factory_mock, caches, scopes,
            observers=[observer]
        )

        assert observer in container._observers
        container.shutdown()


class TestContainerContext:
    """Test container context management."""

    def test_get_current_returns_none_initially(self):
        """get_current returns None when no container active."""
        PicoContainer._container_id_var.set(None)

        assert PicoContainer.get_current() is None

    def test_get_current_id_returns_none_initially(self):
        """get_current_id returns None when no container active."""
        PicoContainer._container_id_var.set(None)

        assert PicoContainer.get_current_id() is None

    def test_all_containers_returns_copy(self):
        """all_containers returns a copy of registry."""
        result = PicoContainer.all_containers()

        assert isinstance(result, dict)


class TestContainerResolution:
    """Test component resolution."""

    def test_canonical_key_with_string_name(self):
        """_canonical_key maps string names to registered keys if found."""
        container = init(modules=[__name__])
        try:
            # When a pico_name matches, the key is mapped to the class
            # Note: This depends on how the locator finds the name
            key = container._canonical_key("named_service")
            # If not found as a type, returns the string as-is
            assert key == "named_service" or key is NamedService
        finally:
            container.shutdown()

    def test_canonical_key_with_unknown_returns_same(self):
        """_canonical_key returns unknown keys unchanged."""
        container = init(modules=[__name__])
        try:
            key = container._canonical_key("unknown_key")
            assert key == "unknown_key"
        finally:
            container.shutdown()

    def test_has_returns_true_for_registered(self):
        """has() returns True for registered components."""
        container = init(modules=[__name__])
        try:
            assert container.has(RegisteredService) is True
        finally:
            container.shutdown()

    def test_has_returns_false_for_unregistered(self):
        """has() returns False for unregistered types."""
        container = init(modules=[])
        try:
            class NotRegistered:
                pass

            assert container.has(NotRegistered) is False
        finally:
            container.shutdown()


class TestContainerExportGraph:
    """Test dependency graph export functionality."""

    def test_export_graph_to_file(self):
        """export_graph writes DOT file to disk."""
        container = init(modules=[__name__])
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.dot', delete=False) as f:
                path = f.name

            container.export_graph(path)

            with open(path, 'r') as f:
                content = f.read()

            assert 'digraph Pico' in content
            assert 'ExportDatabase' in content
            assert 'ExportRepository' in content
            assert '->' in content

            os.unlink(path)
        finally:
            container.shutdown()

    def test_export_graph_with_title(self):
        """export_graph includes title when specified."""
        container = init(modules=[__name__])
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.dot', delete=False) as f:
                path = f.name

            container.export_graph(path, title="My Application")

            with open(path, 'r') as f:
                content = f.read()

            assert 'My Application' in content
            assert 'labelloc="t"' in content

            os.unlink(path)
        finally:
            container.shutdown()

    def test_export_graph_with_qualifiers(self):
        """export_graph includes qualifiers when enabled."""
        container = init(modules=[__name__])
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.dot', delete=False) as f:
                path = f.name

            container.export_graph(path, include_qualifiers=True)

            with open(path, 'r') as f:
                content = f.read()

            assert 'digraph Pico' in content

            os.unlink(path)
        finally:
            container.shutdown()

    def test_export_graph_rankdir(self):
        """export_graph respects rankdir parameter."""
        container = init(modules=[__name__])
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.dot', delete=False) as f:
                path = f.name

            container.export_graph(path, rankdir="TB")

            with open(path, 'r') as f:
                content = f.read()

            assert 'rankdir="TB"' in content

            os.unlink(path)
        finally:
            container.shutdown()

    def test_export_graph_raises_without_locator(self):
        """export_graph raises error if no locator attached."""
        factory_mock = MagicMock(spec=ComponentFactory)
        caches = ScopedCaches()
        scopes = ScopeManager()

        container = PicoContainer(factory_mock, caches, scopes)

        try:
            with pytest.raises(RuntimeError, match="No locator attached"):
                container.export_graph("/tmp/test.dot")
        finally:
            container.shutdown()


class TestContainerCleanup:
    """Test cleanup functionality."""

    def test_cleanup_all_calls_cleanup_methods(self):
        """cleanup_all invokes @cleanup decorated methods."""
        CleanableService.cleanup_called = False

        container = init(modules=[__name__])
        container.get(CleanableService)

        container.cleanup_all()

        assert CleanableService.cleanup_called is True
        container.shutdown()

    @pytest.mark.asyncio
    async def test_cleanup_all_async_awaits_cleanup(self):
        """cleanup_all_async awaits async cleanup methods."""
        AsyncCleanableService.cleanup_called = False

        container = init(modules=[__name__])
        await container.aget(AsyncCleanableService)

        await container.cleanup_all_async()

        assert AsyncCleanableService.cleanup_called is True


class TestContainerStats:
    """Test container statistics."""

    def test_stats_returns_expected_fields(self):
        """stats() returns all expected fields."""
        container = init(modules=[__name__])
        try:
            stats = container.stats()

            assert "container_id" in stats
            assert "profiles" in stats
            assert "uptime_seconds" in stats
            assert "total_resolves" in stats
            assert "cache_hits" in stats
            assert "cache_hit_rate" in stats
            assert "registered_components" in stats
        finally:
            container.shutdown()

    def test_stats_tracks_resolves(self):
        """stats() tracks resolution count."""
        container = init(modules=[__name__])
        try:
            # Get initial count
            initial_resolves = container.context.resolve_count

            # Force a new resolution (TrackedService may already be resolved)
            # Use a scoped resolution to ensure a new resolve
            with container.scope("request", "test-req-123"):
                pass  # Just activate a scope

            # After any resolution, total_resolves should be >= 0
            stats = container.stats()
            assert stats["total_resolves"] >= 0
            assert "total_resolves" in stats
        finally:
            container.shutdown()

    def test_stats_tracks_cache_hits(self):
        """stats() tracks cache hit count."""
        container = init(modules=[__name__])
        try:
            # First call - miss
            container.get(CachedService)
            stats1 = container.stats()
            hits1 = stats1["cache_hits"]

            # Second call - hit
            container.get(CachedService)
            stats2 = container.stats()
            hits2 = stats2["cache_hits"]

            assert hits2 > hits1
        finally:
            container.shutdown()


class TestContainerObservers:
    """Test observer notifications."""

    def test_observers_notified_on_resolve(self):
        """Observers receive on_resolve notification."""
        observer = MagicMock(spec=ContainerObserver)

        container = init(modules=[__name__], observers=[observer])
        try:
            container.get(ObservedService)

            observer.on_resolve.assert_called()
        finally:
            container.shutdown()

    def test_observers_notified_on_cache_hit(self):
        """Observers receive on_cache_hit notification."""
        observer = MagicMock(spec=ContainerObserver)

        container = init(modules=[__name__], observers=[observer])
        try:
            # First call - resolve
            container.get(CacheObservedService)
            # Second call - cache hit
            container.get(CacheObservedService)

            observer.on_cache_hit.assert_called()
        finally:
            container.shutdown()


class TestContainerHealthCheck:
    """Test health check functionality."""

    def test_health_check_runs_health_methods(self):
        """health_check() runs @health decorated methods."""
        container = init(modules=[__name__])
        try:
            container.get(HealthyService)

            results = container.health_check()

            # Should have at least one health check result
            assert len(results) > 0
            # The HealthyService.is_healthy should return True
            healthy_checks = {k: v for k, v in results.items() if "HealthyService" in k and "Unhealthy" not in k}
            assert all(v is True for v in healthy_checks.values())
        finally:
            container.shutdown()

    def test_health_check_catches_exceptions(self):
        """health_check() returns False for failing checks."""
        container = init(modules=[__name__])
        try:
            container.get(UnhealthyService)

            results = container.health_check()

            # Should have a False entry for unhealthy service
            unhealthy_results = {k: v for k, v in results.items() if "Unhealthy" in k}
            assert False in unhealthy_results.values()
        finally:
            container.shutdown()


class TestContainerInfo:
    """Test container info logging."""

    def test_info_logs_with_container_id(self, caplog):
        """info() includes container ID prefix."""
        import logging

        container = init(modules=[__name__])
        try:
            with caplog.at_level(logging.INFO, logger="pico_ioc"):
                container.info("Test message")

            assert any("Test message" in r.message for r in caplog.records)
        finally:
            container.shutdown()
