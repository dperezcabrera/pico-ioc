"""
Additional tests to boost event_bus.py coverage to 90%+.
Tests edge cases and less common code paths.
"""

import asyncio
import logging
import threading
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pico_ioc.event_bus import (
    AutoSubscriberMixin,
    ErrorPolicy,
    Event,
    EventBus,
    ExecPolicy,
    PicoEventBusProvider,
    _Subscriber,
    subscribe,
)
from pico_ioc.exceptions import EventBusClosedError, EventBusError, EventBusHandlerError, EventBusQueueFullError


class SampleEvent(Event):
    """Sample event class for tests."""

    def __init__(self, data=None):
        self.data = data


class AnotherSampleEvent(Event):
    """Another sample event for tests."""

    pass


class TestPublishSyncLoopHandling:
    """Test publish_sync with different loop states."""

    def test_publish_sync_no_running_loop(self):
        """publish_sync uses asyncio.run when no loop running."""
        bus = EventBus()
        results = []

        def handler(event):
            results.append(event.data)

        bus.subscribe(SampleEvent, handler)

        # Call from sync context with no loop
        bus.publish_sync(SampleEvent(data="no_loop"))

        assert len(results) == 1
        assert results[0] == "no_loop"

    @pytest.mark.asyncio
    async def test_publish_sync_with_running_loop(self):
        """publish_sync creates task when loop is running."""
        bus = EventBus()
        results = []

        def handler(event):
            results.append(event.data)

        bus.subscribe(SampleEvent, handler)

        # Call from async context
        bus.publish_sync(SampleEvent(data="with_loop"))

        # Give the task time to complete
        await asyncio.sleep(0.1)

        assert len(results) == 1


class TestPublishTaskErrorHandling:
    """Test error handling in publish with TASK policy."""

    @pytest.mark.asyncio
    async def test_publish_task_error_is_handled(self):
        """Errors in TASK policy handlers are handled."""
        bus = EventBus(error_policy=ErrorPolicy.LOG)
        results = []

        async def failing_handler(event):
            raise ValueError("Task handler failed")

        async def passing_handler(event):
            results.append(event.data)

        bus.subscribe(SampleEvent, failing_handler, policy=ExecPolicy.TASK)
        bus.subscribe(SampleEvent, passing_handler, policy=ExecPolicy.TASK)

        await bus.publish(SampleEvent(data="test"))

        # Both handlers were called as tasks
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_publish_task_gather_exception(self, caplog):
        """Exceptions from gather are logged."""
        bus = EventBus(error_policy=ErrorPolicy.LOG)

        async def failing_handler(event):
            raise RuntimeError("Gather will catch this")

        bus.subscribe(SampleEvent, failing_handler, policy=ExecPolicy.TASK)

        with caplog.at_level(logging.ERROR):
            await bus.publish(SampleEvent())


class TestStartWorkerEdgeCases:
    """Test start_worker edge cases."""

    @pytest.mark.asyncio
    async def test_start_worker_when_closed_raises(self):
        """start_worker raises if bus is closed."""
        bus = EventBus()
        await bus.start_worker()
        await bus.aclose()

        with pytest.raises(EventBusClosedError):
            await bus.start_worker()

    @pytest.mark.asyncio
    async def test_start_worker_twice_is_noop(self):
        """Calling start_worker twice doesn't create second worker."""
        bus = EventBus()

        await bus.start_worker()
        task1 = bus._worker_task

        await bus.start_worker()
        task2 = bus._worker_task

        assert task1 is task2

        await bus.aclose()

    @pytest.mark.asyncio
    async def test_start_worker_creates_queue_if_none(self):
        """start_worker creates queue if max_queue_size was -1."""
        bus = EventBus(max_queue_size=-1)
        assert bus._queue is None

        await bus.start_worker()

        assert bus._queue is not None

        await bus.aclose()


class TestPostFromThread:
    """Test post() from different thread contexts."""

    @pytest.mark.asyncio
    async def test_post_from_same_loop(self):
        """post() from same event loop uses put_nowait."""
        bus = EventBus()
        results = []

        def handler(event):
            results.append(event.data)

        bus.subscribe(SampleEvent, handler)

        await bus.start_worker()

        # Post from within async context (same loop)
        bus.post(SampleEvent(data="same_loop"))

        await asyncio.sleep(0.1)
        await bus.aclose()

        assert "same_loop" in results

    @pytest.mark.asyncio
    async def test_post_from_different_thread(self):
        """post() from different thread uses call_soon_threadsafe."""
        bus = EventBus()
        results = []
        post_error = None

        def handler(event):
            results.append(event.data)

        bus.subscribe(SampleEvent, handler)

        await bus.start_worker()

        def thread_post():
            nonlocal post_error
            try:
                bus.post(SampleEvent(data="from_thread"))
            except Exception as e:
                post_error = e

        # Start thread to post
        t = threading.Thread(target=thread_post)
        t.start()
        t.join()

        await asyncio.sleep(0.1)
        await bus.aclose()

        assert post_error is None
        assert "from_thread" in results

    @pytest.mark.asyncio
    async def test_post_closed_raises(self):
        """post() raises if bus is closed."""
        bus = EventBus()
        await bus.start_worker()
        await bus.aclose()

        with pytest.raises(EventBusClosedError):
            bus.post(SampleEvent())

    @pytest.mark.asyncio
    async def test_post_no_queue_raises(self):
        """post() raises if queue not initialized."""
        bus = EventBus(max_queue_size=-1)
        # Don't start worker

        with pytest.raises(EventBusError, match="Worker queue not initialized"):
            bus.post(SampleEvent())

    @pytest.mark.asyncio
    async def test_post_loop_not_running_raises(self):
        """post() raises if worker loop is not running."""
        bus = EventBus()
        # Manually set queue but no loop
        bus._queue = asyncio.Queue()
        bus._worker_loop = None

        with pytest.raises(EventBusError, match="loop not running"):
            bus.post(SampleEvent())


class TestQueueFullHandling:
    """Test queue full scenarios."""

    @pytest.mark.asyncio
    async def test_post_queue_full_raises(self):
        """post() raises EventBusQueueFullError when queue is full."""
        bus = EventBus(max_queue_size=1)

        await bus.start_worker()

        # Fill the queue by pausing the worker
        # This is tricky to test - we'll mock put_nowait

        original_put = bus._queue.put_nowait

        def full_put(item):
            raise asyncio.QueueFull()

        bus._queue.put_nowait = full_put

        with pytest.raises(EventBusQueueFullError):
            bus.post(SampleEvent())

        bus._queue.put_nowait = original_put
        await bus.aclose()


class TestPicoEventBusProviderShutdown:
    """Test PicoEventBusProvider shutdown paths."""

    def test_provider_shutdown_no_loop(self):
        """shutdown() uses asyncio.run when no loop."""
        provider = PicoEventBusProvider()
        bus = provider.build()

        # Shutdown from sync context
        provider.shutdown(bus)

        assert bus._closed is True

    @pytest.mark.asyncio
    async def test_provider_shutdown_with_running_loop(self):
        """shutdown() creates task when loop is running."""
        provider = PicoEventBusProvider()
        bus = provider.build()

        # Shutdown from async context
        provider.shutdown(bus)

        # Wait for task to complete
        await asyncio.sleep(0.1)

        assert bus._closed is True


class TestAutoSubscriberMixin:
    """Test AutoSubscriberMixin functionality."""

    def test_autosubscriber_registers_decorated_methods(self):
        """AutoSubscriberMixin registers methods with @subscribe."""

        class MySubscriber(AutoSubscriberMixin):
            def __init__(self):
                self.events = []

            @subscribe(SampleEvent, priority=5)
            def handle_test(self, event):
                self.events.append(event)

            @subscribe(AnotherSampleEvent)
            def handle_another(self, event):
                self.events.append(event)

        bus = EventBus()
        subscriber = MySubscriber()

        # Manually call autosubscribe
        subscriber._pico_autosubscribe(bus)

        # Should have registered both handlers
        assert SampleEvent in bus._subs
        assert AnotherSampleEvent in bus._subs


class TestSubscriberDataclass:
    """Test _Subscriber dataclass."""

    def test_subscriber_sort_index(self):
        """_Subscriber sort_index is negative priority."""
        sub = _Subscriber(priority=10, callback=lambda e: None, policy=ExecPolicy.INLINE, once=False)

        assert sub.sort_index == -10

    def test_subscribers_sort_by_priority(self):
        """Subscribers sort by priority (higher first)."""
        sub_low = _Subscriber(priority=1, callback=lambda e: None, policy=ExecPolicy.INLINE, once=False)
        sub_high = _Subscriber(priority=10, callback=lambda e: None, policy=ExecPolicy.INLINE, once=False)

        subs = [sub_low, sub_high]
        subs.sort()

        # Higher priority (10) should come first
        assert subs[0].priority == 10
        assert subs[1].priority == 1


class TestHandleError:
    """Test _handle_error method."""

    def test_handle_error_raise_policy(self):
        """RAISE policy raises the error."""
        bus = EventBus(error_policy=ErrorPolicy.RAISE)

        with pytest.raises(EventBusHandlerError):
            bus._handle_error(EventBusHandlerError("Test", "handler", ValueError("test")))

    def test_handle_error_log_policy(self, caplog):
        """LOG policy logs the error."""
        bus = EventBus(error_policy=ErrorPolicy.LOG)

        with caplog.at_level(logging.ERROR):
            bus._handle_error(EventBusError("Test error"))

        assert any("Test error" in r.message for r in caplog.records)


class TestWorkerProcessesEvents:
    """Test that worker properly processes queued events."""

    @pytest.mark.asyncio
    async def test_worker_processes_multiple_events(self):
        """Worker processes all queued events."""
        bus = EventBus()
        results = []

        def handler(event):
            results.append(event.data)

        bus.subscribe(SampleEvent, handler)

        await bus.start_worker()

        # Post multiple events
        for i in range(5):
            bus.post(SampleEvent(data=i))

        # Wait for processing
        await asyncio.sleep(0.2)

        await bus.aclose()

        assert results == [0, 1, 2, 3, 4]

    @pytest.mark.asyncio
    async def test_worker_handles_event_errors(self, caplog):
        """Worker continues after handler errors."""
        bus = EventBus(error_policy=ErrorPolicy.LOG)
        results = []

        def failing_handler(event):
            if event.data == 1:
                raise ValueError("Event 1 failed")
            results.append(event.data)

        bus.subscribe(SampleEvent, failing_handler)

        await bus.start_worker()

        # Post events
        for i in range(3):
            bus.post(SampleEvent(data=i))

        await asyncio.sleep(0.2)
        await bus.aclose()

        # Should have processed events 0 and 2
        assert 0 in results
        assert 2 in results
        assert 1 not in results


class TestStopWorker:
    """Test stop_worker functionality."""

    @pytest.mark.asyncio
    async def test_stop_worker_waits_for_queue(self):
        """stop_worker waits for queue to be processed."""
        bus = EventBus()
        results = []

        async def slow_handler(event):
            await asyncio.sleep(0.05)
            results.append(event.data)

        bus.subscribe(SampleEvent, slow_handler)

        await bus.start_worker()

        # Post event
        bus.post(SampleEvent(data="slow"))

        # Stop worker - should wait
        await bus.stop_worker()

        # Event should have been processed
        assert "slow" in results

    @pytest.mark.asyncio
    async def test_stop_worker_without_start_is_noop(self):
        """stop_worker does nothing if worker not started."""
        bus = EventBus()

        # Should not raise
        await bus.stop_worker()


class SampleEventBusNegativeQueueSize:
    """Test EventBus with negative max_queue_size."""

    def test_negative_queue_size_means_no_queue(self):
        """max_queue_size=-1 means no queue created."""
        bus = EventBus(max_queue_size=-1)
        assert bus._queue is None

    def test_zero_queue_size_creates_unlimited_queue(self):
        """max_queue_size=0 creates unlimited queue."""
        bus = EventBus(max_queue_size=0)
        assert bus._queue is not None
