"""Regression tests for user-facing error contracts and observer hooks.

These pin behavior users actually hit: resolving async components through
the sync API, async @configure on the sync path, observers, and
refresh_config on containers without tree config.
"""

import pytest

from pico_ioc import DictSource, component, configuration, configure, init
from pico_ioc.exceptions import AsyncResolutionError


@component(lazy=True)
class NeedsAsyncSetup:
    def __init__(self):
        self.ready = False

    @configure
    async def setup(self):
        self.ready = True


def test_sync_access_to_async_configured_lazy_raises_actionable_error():
    container = init(modules=[__name__])
    proxy = container.get(NeedsAsyncSetup)
    with pytest.raises(AsyncResolutionError, match="aget"):
        proxy.ready


@pytest.mark.asyncio
async def test_aget_runs_async_configure():
    container = init(modules=[__name__])
    instance = await container.aget(NeedsAsyncSetup)
    assert instance.ready is True


@component
class Plain:
    pass


def test_observer_sees_resolves_and_cache_hits():
    events = []

    class Spy:
        def on_resolve(self, key, took_ms):
            events.append(("resolve", key, took_ms))

        def on_cache_hit(self, key):
            events.append(("hit", key))

    container = init(modules=[__name__], observers=[Spy()])
    container.get(Plain)
    container.get(Plain)

    resolves = [e for e in events if e[0] == "resolve" and e[1] is Plain]
    hits = [e for e in events if e[0] == "hit" and e[1] is Plain]
    assert len(resolves) == 1
    assert resolves[0][2] >= 0
    assert len(hits) >= 1


def test_refresh_config_without_tree_sources_is_empty():
    container = init(modules=[__name__])
    assert container.refresh_config() == frozenset()


def test_refresh_config_with_flat_only_config_is_empty():
    container = init(modules=[__name__], config=configuration(DictSource({})))
    assert container.refresh_config() == frozenset()


_cleanup_calls = []


@component
class Closeable:
    from pico_ioc import cleanup

    @cleanup
    def close(self):
        import threading

        _cleanup_calls.append(threading.current_thread().name)


def test_shutdown_is_idempotent_and_thread_safe():
    import threading

    _cleanup_calls.clear()
    container = init(modules=[__name__])
    container.get(Closeable)

    threads = [threading.Thread(target=container.shutdown) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    container.shutdown()
    assert len(_cleanup_calls) == 1, _cleanup_calls
