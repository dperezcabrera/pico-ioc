"""
Tests for bugs fixed in v2.2.1:
1. DOT graph export - incorrect variable reference
2. Race condition in async lazy proxy
3. Silent cleanup failures now logged
"""

import asyncio
import logging
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from pico_ioc import cleanup, component, configure, init
from pico_ioc.aop import UnifiedComponentProxy
from pico_ioc.constants import PICO_META
from pico_ioc.scope import ComponentContainer, ScopedCaches, ScopeManager


# Define components at module level for proper scanning
@component()
class GraphServiceA:
    pass


@component()
class GraphServiceB:
    def __init__(self, a: GraphServiceA):
        self.a = a


@component()
class GraphDatabase:
    pass


@component()
class GraphCache:
    pass


@component()
class GraphRepository:
    def __init__(self, db: GraphDatabase, cache: GraphCache):
        self.db = db
        self.cache = cache


@component()
class GraphService:
    def __init__(self, repo: GraphRepository):
        self.repo = repo


class TestDotGraphExportFix:
    """Test that export_graph produces correct DOT syntax."""

    def test_dot_graph_edges_use_correct_variable(self):
        """Verify edges use {cid} not {child} - the v2.2.1 fix."""
        container = init(modules=[__name__])
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".dot", delete=False) as f:
                path = f.name

            container.export_graph(path)

            with open(path) as f:
                dot_output = f.read()

            # Should contain valid edge syntax
            assert "->" in dot_output
            # Should NOT contain literal {child} which was the bug
            assert "{child}" not in dot_output
            # Should reference actual node IDs
            assert "GraphServiceA" in dot_output
            assert "GraphServiceB" in dot_output

            os.unlink(path)
        finally:
            container.shutdown()

    def test_dot_graph_with_multiple_dependencies(self):
        """Test DOT export with complex dependency tree."""
        container = init(modules=[__name__])
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".dot", delete=False) as f:
                path = f.name

            container.export_graph(path)

            with open(path) as f:
                dot_output = f.read()

            # Count edges - should have multiple
            edge_count = dot_output.count("->")
            assert edge_count >= 3

            # Verify no malformed syntax
            lines = dot_output.split("\n")
            for line in lines:
                if "->" in line:
                    # Each edge line should not have unresolved variables
                    assert "{child}" not in line
                    assert "{cid}" not in line

            os.unlink(path)
        finally:
            container.shutdown()


class TestAsyncProxyRaceConditionFix:
    """Test the race condition fix in _async_init_if_needed."""

    @pytest.mark.asyncio
    async def test_concurrent_async_init_creates_single_instance(self):
        """Multiple concurrent awaits should create only one instance."""
        creation_count = 0

        def creator():
            nonlocal creation_count
            creation_count += 1
            return {"id": creation_count}

        container = MagicMock()
        container._run_configure_methods = MagicMock(return_value=None)

        proxy = UnifiedComponentProxy(container=container, target=None, object_creator=creator, component_key="test")

        # Simulate concurrent access
        async def access_proxy():
            await proxy._async_init_if_needed()
            return proxy._get_real_object()

        # Run multiple concurrent accesses
        results = await asyncio.gather(*[access_proxy() for _ in range(10)])

        # All results should be the same object
        first = results[0]
        for r in results[1:]:
            assert r is first

        # Creator should only be called once
        assert creation_count == 1

    @pytest.mark.asyncio
    async def test_async_init_with_async_configure(self):
        """Test that async configure methods are properly awaited."""
        configure_called = False

        def creator():
            return MagicMock()

        async def async_configure_result():
            nonlocal configure_called
            await asyncio.sleep(0.01)
            configure_called = True

        container = MagicMock()
        # Return an awaitable from _run_configure_methods
        container._run_configure_methods = MagicMock(return_value=async_configure_result())

        proxy = UnifiedComponentProxy(container=container, target=None, object_creator=creator, component_key="test")

        await proxy._async_init_if_needed()

        # Configure should have been awaited
        assert configure_called

    @pytest.mark.asyncio
    async def test_async_init_skips_if_already_initialized(self):
        """Fast path: skip initialization if target already exists."""
        creator = MagicMock(return_value={"test": True})

        container = MagicMock()

        proxy = UnifiedComponentProxy(
            container=container,
            target={"existing": True},  # Already has target
            object_creator=creator,
            component_key="test",
        )

        await proxy._async_init_if_needed()

        # Creator should NOT be called since target already exists
        creator.assert_not_called()


class TestCleanupLoggingFix:
    """Test that cleanup failures are now logged instead of silently ignored."""

    def test_cleanup_object_logs_exception(self, caplog):
        """Verify cleanup method exceptions are logged at WARNING level."""

        class FailingService:
            def close(self):
                raise RuntimeError("Connection refused")

        # Mark close as a cleanup method
        FailingService.close._pico_meta = {"cleanup": True}

        caches = ScopedCaches()
        service = FailingService()

        with caplog.at_level(logging.WARNING, logger="pico_ioc.scope"):
            caches._cleanup_object(service)

        # Should log the failure
        assert any("Cleanup method" in record.message for record in caplog.records)
        assert any("failed" in record.message.lower() for record in caplog.records)

    def test_cleanup_container_processes_all_items(self):
        """Multiple objects in container should all be processed."""
        caches = ScopedCaches()
        container = ComponentContainer()

        # Add multiple items
        container.put("s1", {"name": "service1"})
        container.put("s2", {"name": "service2"})

        cleanup_calls = []
        original_cleanup = caches._cleanup_object

        def tracking_cleanup(obj):
            cleanup_calls.append(obj)
            original_cleanup(obj)

        caches._cleanup_object = tracking_cleanup

        caches._cleanup_container(container)

        # Both objects should have been processed
        assert len(cleanup_calls) == 2

    def test_cleanup_scope_removes_entry_and_cleans(self):
        """cleanup_scope should remove bucket entry and run cleanup."""
        caches = ScopedCaches()
        scope_name = "request"
        scope_id = "req-123"

        # Manually add a scoped container
        container = ComponentContainer()
        container.put("key", {"data": "test"})
        caches._by_scope[scope_name] = {scope_id: container}

        # Cleanup should remove the entry
        caches.cleanup_scope(scope_name, scope_id)

        # Entry should be removed
        assert scope_id not in caches._by_scope.get(scope_name, {})


class TestScopedCachesEdgeCases:
    """Additional tests for ScopedCaches coverage."""

    def test_for_scope_singleton_returns_same_container(self):
        """Singleton scope always returns the same container."""
        caches = ScopedCaches()
        scopes = ScopeManager()

        c1 = caches.for_scope(scopes, "singleton")
        c2 = caches.for_scope(scopes, "singleton")

        assert c1 is c2

    def test_for_scope_prototype_returns_no_cache(self):
        """Prototype scope returns a no-op container."""
        caches = ScopedCaches()
        scopes = ScopeManager()

        container = caches.for_scope(scopes, "prototype")

        # Should be the _NoCacheContainer
        container.put("key", "value")
        assert container.get("key") is None  # No caching
        assert container.items() == []

    def test_all_items_iterates_all_caches(self):
        """all_items should yield from singleton and all scoped caches."""
        caches = ScopedCaches()

        # Add to singleton
        caches._singleton.put("singleton_key", "singleton_val")

        # Add to scoped
        scoped_container = ComponentContainer()
        scoped_container.put("scoped_key", "scoped_val")
        caches._by_scope["request"] = {"req-1": scoped_container}

        items = list(caches.all_items())

        assert ("singleton_key", "singleton_val") in items
        assert ("scoped_key", "scoped_val") in items

    def test_shrink_does_nothing_for_singleton(self):
        """shrink() should be no-op for singleton scope."""
        caches = ScopedCaches()
        caches._singleton.put("key", "value")

        caches.shrink("singleton", 0)

        # Singleton should be unaffected
        assert caches._singleton.get("key") == "value"

    def test_shrink_does_nothing_for_prototype(self):
        """shrink() should be no-op for prototype scope."""
        caches = ScopedCaches()

        # Should not raise
        caches.shrink("prototype", 0)

    def test_shrink_removes_oldest_entries(self):
        """shrink() should remove entries beyond keep limit."""
        caches = ScopedCaches()

        # Add multiple scope entries
        for i in range(5):
            container = ComponentContainer()
            container.put(f"key_{i}", f"value_{i}")
            caches._by_scope.setdefault("request", {})[f"req-{i}"] = container

        assert len(caches._by_scope["request"]) == 5

        # Shrink to keep only 2
        caches.shrink("request", 2)

        assert len(caches._by_scope["request"]) == 2


class TestScopeManagerEdgeCases:
    """Additional tests for ScopeManager coverage."""

    def test_get_id_returns_none_for_singleton(self):
        """get_id for singleton always returns None."""
        sm = ScopeManager()
        assert sm.get_id("singleton") is None

    def test_get_id_returns_none_for_prototype(self):
        """get_id for prototype always returns None."""
        sm = ScopeManager()
        assert sm.get_id("prototype") is None

    def test_activate_returns_none_for_singleton(self):
        """activate() for singleton is no-op."""
        sm = ScopeManager()
        result = sm.activate("singleton", "any-id")
        assert result is None

    def test_deactivate_does_nothing_for_singleton(self):
        """deactivate() for singleton is no-op."""
        sm = ScopeManager()
        # Should not raise
        sm.deactivate("singleton", None)

    def test_names_excludes_reserved(self):
        """names() should not include singleton or prototype."""
        sm = ScopeManager()
        names = sm.names()

        assert "singleton" not in names
        assert "prototype" not in names
        assert "request" in names
        assert "session" in names

    def test_signature_returns_tuple_of_ids(self):
        """signature() returns tuple of scope IDs for given names."""
        sm = ScopeManager()

        # Activate some scopes
        sm.activate("request", "req-1")
        sm.activate("session", "sess-1")

        sig = sm.signature(("request", "session"))

        assert sig == ("req-1", "sess-1")

    def test_signature_all_returns_all_scope_ids(self):
        """signature_all() returns IDs for all registered scopes."""
        sm = ScopeManager()

        sm.activate("request", "req-1")

        sig = sm.signature_all()

        # Should have entries for all scopes (even if None)
        assert len(sig) == len(sm.names())
