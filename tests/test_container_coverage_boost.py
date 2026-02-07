"""
Additional tests to boost container.py coverage to 90%+.
Tests edge cases and less common code paths.
"""
import asyncio
import inspect
import os
import tempfile
from typing import Any, Dict, List, Type
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pico_ioc import cleanup, component, configure, factory, init, provides
from pico_ioc.aop import MethodCtx, MethodInterceptor, UnifiedComponentProxy, intercepted_by
from pico_ioc.constants import PICO_META
from pico_ioc.container import (
    PicoContainer,
    _build_resolution_graph,
    _get_signature_safe,
    _iter_configure_methods,
    _needs_async_configure,
)
from pico_ioc.exceptions import AsyncResolutionError, ProviderNotFoundError
from pico_ioc.factory import ComponentFactory, ProviderMetadata
from pico_ioc.locator import ComponentLocator
from pico_ioc.scope import ScopedCaches, ScopeManager

# ============================================================
# Helper function tests - don't need container
# ============================================================

class TestGetSignatureSafeEdgeCases:
    """Test _get_signature_safe edge cases."""

    def test_signature_with_wrapped_attribute(self):
        """Function with __wrapped__ falls back to wrapped signature."""
        def original(x: int, y: str) -> bool:
            return True

        class BadCallable:
            def __call__(self):
                pass

        bad = BadCallable()
        bad.__wrapped__ = original

        sig = _get_signature_safe(bad)
        assert 'x' in sig.parameters
        assert 'y' in sig.parameters

    def test_signature_normal_function(self):
        """Normal function returns signature directly."""
        def normal_func(a: int, b: str = "default") -> None:
            pass

        sig = _get_signature_safe(normal_func)
        assert 'a' in sig.parameters
        assert 'b' in sig.parameters

    def test_signature_raises_when_no_wrapped(self):
        """_get_signature_safe raises when signature fails and no __wrapped__."""
        class BadObj:
            """Object that can't be introspected."""
            pass

        bad = BadObj()
        # Should raise since no __wrapped__ and signature fails
        with pytest.raises((ValueError, TypeError)):
            _get_signature_safe(bad)


class TestNeedsAsyncConfigure:
    """Test _needs_async_configure helper."""

    def test_needs_async_configure_detects_async(self):
        """_needs_async_configure returns True for async configure methods."""
        class Service:
            async def setup(self):
                pass

        Service.setup._pico_meta = {"configure": True}

        instance = Service()
        assert _needs_async_configure(instance) is True

    def test_needs_async_configure_false_for_sync(self):
        """_needs_async_configure returns False for sync configure."""
        class Service:
            def setup(self):
                pass

        Service.setup._pico_meta = {"configure": True}

        instance = Service()
        assert _needs_async_configure(instance) is False

    def test_needs_async_configure_false_no_configure(self):
        """Returns False when no configure methods exist."""
        class Service:
            def regular(self):
                pass

        instance = Service()
        assert _needs_async_configure(instance) is False


class TestIterConfigureMethods:
    """Test _iter_configure_methods helper."""

    def test_iter_configure_methods_yields_all(self):
        """_iter_configure_methods yields all configure methods."""
        class Service:
            def setup1(self):
                pass
            def setup2(self):
                pass
            def regular(self):
                pass

        Service.setup1._pico_meta = {"configure": True}
        Service.setup2._pico_meta = {"configure": True}

        instance = Service()
        methods = list(_iter_configure_methods(instance))

        assert len(methods) == 2

    def test_iter_configure_methods_empty(self):
        """_iter_configure_methods yields nothing for no configure methods."""
        class Service:
            def regular(self):
                pass

        instance = Service()
        methods = list(_iter_configure_methods(instance))

        assert len(methods) == 0


class TestBuildResolutionGraph:
    """Test _build_resolution_graph."""

    def test_build_resolution_graph_none_locator(self):
        """Returns empty dict for None locator."""
        result = _build_resolution_graph(None)
        assert result == {}

    def test_build_resolution_graph_with_mock_locator(self):
        """_build_resolution_graph works with mock locator."""
        mock_md = MagicMock()
        mock_md.provided_type = str
        mock_md.concrete_class = str
        mock_md.primary = True

        mock_locator = MagicMock()
        mock_locator._metadata = {str: mock_md}
        mock_locator.dependency_keys_for_static.return_value = []
        mock_locator.find_key_by_name.return_value = None

        result = _build_resolution_graph(mock_locator)
        assert isinstance(result, dict)

    def test_build_resolution_graph_maps_dependencies(self):
        """_build_resolution_graph maps dependencies correctly."""
        mock_md = MagicMock()
        mock_md.provided_type = int
        mock_md.concrete_class = int
        mock_md.primary = True

        mock_locator = MagicMock()
        mock_locator._metadata = {int: mock_md}
        mock_locator.dependency_keys_for_static.return_value = ["named_dep"]
        mock_locator.find_key_by_name.return_value = str

        result = _build_resolution_graph(mock_locator)
        assert int in result
        assert str in result[int]


class TestContainerInit:
    """Test container initialization."""

    def test_container_id_generation_unique(self):
        """Container generates unique IDs."""
        id1 = PicoContainer._generate_container_id()
        id2 = PicoContainer._generate_container_id()

        assert id1 != id2
        assert id1.startswith('c')

    def test_container_custom_id(self):
        """Container accepts custom ID."""
        factory_mock = MagicMock(spec=ComponentFactory)
        caches = ScopedCaches()
        scopes = ScopeManager()

        container = PicoContainer(
            factory_mock, caches, scopes,
            container_id="my-custom-id"
        )

        assert container.container_id == "my-custom-id"
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


class TestContainerContext:
    """Test container context management."""

    def test_get_current_returns_none(self):
        """get_current returns None when no container active."""
        PicoContainer._container_id_var.set(None)
        assert PicoContainer.get_current() is None

    def test_get_current_id_returns_none(self):
        """get_current_id returns None when no container active."""
        PicoContainer._container_id_var.set(None)
        assert PicoContainer.get_current_id() is None

    def test_all_containers_returns_dict(self):
        """all_containers returns a dict."""
        result = PicoContainer.all_containers()
        assert isinstance(result, dict)


class TestContainerRegistryManagement:
    """Test container registry management."""

    def test_shutdown_removes_from_registry(self):
        """shutdown() removes container from registry."""
        container = init(modules=[])
        cid = container.container_id

        assert cid in PicoContainer._container_registry

        container.shutdown()

        assert cid not in PicoContainer._container_registry

    @pytest.mark.asyncio
    async def test_ashutdown_removes_from_registry(self):
        """ashutdown() removes container from registry."""
        container = init(modules=[])
        cid = container.container_id

        assert cid in PicoContainer._container_registry

        await container.ashutdown()

        assert cid not in PicoContainer._container_registry


class TestScopeContextManager:
    """Test container.scope() context manager."""

    def test_scope_context_manager_activates_deactivates(self):
        """scope() context manager properly activates/deactivates scope."""
        container = init(modules=[])
        try:
            assert container.scopes.get_id("request") is None

            with container.scope("request", "test-id"):
                assert container.scopes.get_id("request") == "test-id"

            assert container.scopes.get_id("request") is None
        finally:
            container.shutdown()


class TestExportGraphWithoutLocator:
    """Test export_graph error handling."""

    def test_export_graph_raises_without_locator(self):
        """export_graph raises if no locator attached."""
        factory_mock = MagicMock(spec=ComponentFactory)
        caches = ScopedCaches()
        scopes = ScopeManager()

        container = PicoContainer(factory_mock, caches, scopes)

        try:
            with pytest.raises(RuntimeError, match="No locator attached"):
                container.export_graph("/tmp/test.dot")
        finally:
            container.shutdown()


class TestCanonicalKeyUnknown:
    """Test _canonical_key with unknown keys."""

    def test_canonical_key_unknown_returns_same(self):
        """_canonical_key returns unknown key unchanged."""
        container = init(modules=[])
        try:
            key = container._canonical_key("unknown_string_key")
            assert key == "unknown_string_key"
        finally:
            container.shutdown()


class TestContainerActivateDeactivate:
    """Test container activate/deactivate."""

    def test_activate_sets_context_var(self):
        """activate() sets the container ID context var."""
        container = init(modules=[])
        try:
            token = container.activate()
            assert PicoContainer._container_id_var.get() == container.container_id
            container.deactivate(token)
        finally:
            container.shutdown()

    def test_as_current_context_manager(self):
        """as_current() context manager works correctly."""
        container = init(modules=[])
        try:
            with container.as_current() as c:
                assert c is container
                assert PicoContainer.get_current() is container
        finally:
            container.shutdown()


class TestContainerStats:
    """Test container stats."""

    def test_stats_returns_all_fields(self):
        """stats() returns all expected fields."""
        container = init(modules=[])
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

    def test_stats_cache_hit_rate_zero_when_empty(self):
        """cache_hit_rate is 0.0 when no resolves."""
        container = init(modules=[])
        try:
            stats = container.stats()
            # No resolves means 0 hit rate
            assert stats["cache_hit_rate"] == 0.0
        finally:
            container.shutdown()


class TestContainerInfo:
    """Test container info logging."""

    def test_info_logs_message(self, caplog):
        """info() logs a message."""
        import logging

        container = init(modules=[])
        try:
            with caplog.at_level(logging.INFO, logger="pico_ioc"):
                container.info("Test info message")

            assert any("Test info message" in r.message for r in caplog.records)
        finally:
            container.shutdown()


class TestCleanupAllAsync:
    """Test cleanup_all_async."""

    @pytest.mark.asyncio
    async def test_cleanup_all_async_runs(self):
        """cleanup_all_async executes without error."""
        container = init(modules=[])
        try:
            await container.cleanup_all_async()
        finally:
            PicoContainer._container_registry.pop(container.container_id, None)


class TestHasMethod:
    """Test has() method."""

    def test_has_returns_false_for_unknown(self):
        """has() returns False for unknown keys."""
        container = init(modules=[])
        try:
            class UnknownClass:
                pass

            assert container.has(UnknownClass) is False
            assert container.has("unknown_key") is False
        finally:
            container.shutdown()


class TestAttachLocator:
    """Test attach_locator."""

    def test_attach_locator_sets_locator(self):
        """attach_locator() sets the _locator attribute."""
        factory_mock = MagicMock(spec=ComponentFactory)
        caches = ScopedCaches()
        scopes = ScopeManager()

        container = PicoContainer(factory_mock, caches, scopes)

        assert container._locator is None

        mock_locator = MagicMock(spec=ComponentLocator)
        # Mock the _metadata attribute that shutdown() iterates
        mock_locator._metadata = {}
        container.attach_locator(mock_locator)

        assert container._locator is mock_locator
        container.shutdown()


class TestActivateDeactivateScope:
    """Test scope activation/deactivation."""

    def test_activate_scope_delegates_to_scopes(self):
        """activate_scope() delegates to scopes manager."""
        container = init(modules=[])
        try:
            token = container.activate_scope("request", "req-123")
            assert container.scopes.get_id("request") == "req-123"

            container.deactivate_scope("request", token)
            assert container.scopes.get_id("request") is None
        finally:
            container.shutdown()


class TestBuildResolutionGraphMethod:
    """Test build_resolution_graph method."""

    def test_build_resolution_graph_with_no_locator(self):
        """build_resolution_graph returns empty for no locator."""
        factory_mock = MagicMock(spec=ComponentFactory)
        caches = ScopedCaches()
        scopes = ScopeManager()

        container = PicoContainer(factory_mock, caches, scopes)

        graph = container.build_resolution_graph()
        assert graph == {}

        container.shutdown()


# ============================================================
# Additional tests for uncovered lines - using mocks
# ============================================================

class TestBuildResolutionGraphIssubclassException:
    """Test _build_resolution_graph handles issubclass exceptions."""

    def test_handles_non_type_provided_type(self):
        """_build_resolution_graph handles non-type provided_type."""
        mock_md = MagicMock()
        mock_md.provided_type = "not_a_type"  # String, not type
        mock_md.concrete_class = "also_not_type"
        mock_md.primary = True

        mock_locator = MagicMock()
        mock_locator._metadata = {"key": mock_md}
        mock_locator.dependency_keys_for_static.return_value = [int]
        mock_locator.find_key_by_name.return_value = None

        # Should not raise - just continues
        result = _build_resolution_graph(mock_locator)
        assert isinstance(result, dict)


class TestCanonicalKeyWithTypeNotFound:
    """Test _canonical_key with type that has no subclass match."""

    def test_canonical_key_unknown_type_returns_same(self):
        """_canonical_key returns unknown type unchanged."""
        container = init(modules=[])
        try:
            class SomeRandomClass:
                pass

            key = container._canonical_key(SomeRandomClass)
            assert key is SomeRandomClass
        finally:
            container.shutdown()


class TestExportGraphWritesFile:
    """Test export_graph file writing."""

    def test_export_graph_writes_dot_file(self):
        """export_graph writes valid DOT file."""
        container = init(modules=[])
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.dot', delete=False) as f:
                path = f.name

            container.export_graph(path)

            with open(path) as f:
                content = f.read()

            assert 'digraph Pico' in content
            os.unlink(path)
        finally:
            container.shutdown()

    def test_export_graph_with_title(self):
        """export_graph includes title when specified."""
        container = init(modules=[])
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.dot', delete=False) as f:
                path = f.name

            container.export_graph(path, title="My App")

            with open(path) as f:
                content = f.read()

            assert 'My App' in content
            os.unlink(path)
        finally:
            container.shutdown()


class TestContainerRepr:
    """Test container __repr__."""

    def test_container_repr(self):
        """Container has a useful repr."""
        container = init(modules=[])
        try:
            r = repr(container)
            assert "PicoContainer" in r or "container" in r.lower()
        finally:
            container.shutdown()
