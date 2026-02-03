"""
Extended tests for event_bus.py to increase coverage.
"""
import asyncio
import pytest
from unittest.mock import MagicMock, patch
import threading
import logging

from pico_ioc.event_bus import (
    EventBus, subscribe, ExecPolicy, ErrorPolicy, Event, AutoSubscriberMixin
)
from pico_ioc.exceptions import EventBusClosedError, EventBusError


class MyEvent(Event):
    """Test event class."""
    def __init__(self, data=None):
        self.data = data


class AnotherEvent(Event):
    """Another test event class."""
    pass


class TestEventBusBasics:
    """Test basic EventBus functionality."""

    def test_eventbus_default_init(self):
        """EventBus initializes with default settings."""
        bus = EventBus()

        assert bus._error_policy == ErrorPolicy.LOG
        assert bus._default_policy == ExecPolicy.INLINE

    def test_eventbus_custom_policies(self):
        """EventBus accepts custom default policies."""
        bus = EventBus(
            error_policy=ErrorPolicy.RAISE,
            default_exec_policy=ExecPolicy.TASK
        )

        assert bus._error_policy == ErrorPolicy.RAISE
        assert bus._default_policy == ExecPolicy.TASK

    def test_subscribe_adds_handler(self):
        """subscribe() adds handler for event type."""
        bus = EventBus()
        called = []

        def handler(event):
            called.append(event)

        bus.subscribe(MyEvent, handler)

        assert MyEvent in bus._subs
        assert len(bus._subs[MyEvent]) == 1

    def test_unsubscribe_removes_handler(self):
        """unsubscribe() removes the handler."""
        bus = EventBus()
        called = []

        def handler(event):
            called.append(event)

        bus.subscribe(MyEvent, handler)
        assert len(bus._subs[MyEvent]) == 1

        bus.unsubscribe(MyEvent, handler)
        assert len(bus._subs[MyEvent]) == 0

    def test_subscribe_same_handler_twice_ignored(self):
        """Subscribing same handler twice is ignored."""
        bus = EventBus()

        def handler(event):
            pass

        bus.subscribe(MyEvent, handler)
        bus.subscribe(MyEvent, handler)

        assert len(bus._subs[MyEvent]) == 1


class TestEventBusPublish:
    """Test event publishing functionality."""

    @pytest.mark.asyncio
    async def test_publish_calls_all_handlers(self):
        """publish() calls all subscribed handlers."""
        bus = EventBus()
        results = []

        def handler1(event):
            results.append(("h1", event.data))

        def handler2(event):
            results.append(("h2", event.data))

        bus.subscribe(MyEvent, handler1)
        bus.subscribe(MyEvent, handler2)

        await bus.publish(MyEvent(data=42))

        assert len(results) == 2
        assert ("h1", 42) in results
        assert ("h2", 42) in results

    @pytest.mark.asyncio
    async def test_publish_respects_priority(self):
        """publish() calls handlers in priority order."""
        bus = EventBus()
        order = []

        def low_priority(event):
            order.append("low")

        def high_priority(event):
            order.append("high")

        # Higher priority number = higher priority (called first)
        bus.subscribe(MyEvent, low_priority, priority=1)
        bus.subscribe(MyEvent, high_priority, priority=10)

        await bus.publish(MyEvent())

        # Higher priority number is called first
        assert order == ["high", "low"]

    @pytest.mark.asyncio
    async def test_publish_with_once_removes_after_first(self):
        """publish() removes once=True handlers after first call."""
        bus = EventBus()
        call_count = 0

        def once_handler(event):
            nonlocal call_count
            call_count += 1

        bus.subscribe(MyEvent, once_handler, once=True)

        await bus.publish(MyEvent())
        await bus.publish(MyEvent())

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_publish_different_event_types(self):
        """publish() only calls handlers for matching event type."""
        bus = EventBus()
        my_calls = []
        another_calls = []

        def my_handler(event):
            my_calls.append(event)

        def another_handler(event):
            another_calls.append(event)

        bus.subscribe(MyEvent, my_handler)
        bus.subscribe(AnotherEvent, another_handler)

        await bus.publish(MyEvent())

        assert len(my_calls) == 1
        assert len(another_calls) == 0


class TestEventBusErrorHandling:
    """Test error handling in EventBus."""

    @pytest.mark.asyncio
    async def test_error_policy_log_continues(self, caplog):
        """LOG policy logs error and continues."""
        bus = EventBus(error_policy=ErrorPolicy.LOG)
        results = []

        def failing_handler(event):
            raise ValueError("Handler failed")

        def passing_handler(event):
            results.append(event)

        bus.subscribe(MyEvent, failing_handler)
        bus.subscribe(MyEvent, passing_handler)

        with caplog.at_level(logging.ERROR):
            await bus.publish(MyEvent())

        # Passing handler should still be called
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_error_policy_raise_propagates(self):
        """RAISE policy propagates the error."""
        bus = EventBus(error_policy=ErrorPolicy.RAISE)

        def failing_handler(event):
            raise RuntimeError("Critical failure")

        bus.subscribe(MyEvent, failing_handler)

        with pytest.raises(Exception):  # EventBusHandlerError wraps it
            await bus.publish(MyEvent())


class TestEventBusAsyncHandlers:
    """Test async handler functionality."""

    @pytest.mark.asyncio
    async def test_async_handler_inline(self):
        """Async handlers with INLINE policy are awaited."""
        bus = EventBus(default_exec_policy=ExecPolicy.INLINE)
        result = []

        async def async_handler(event):
            await asyncio.sleep(0.01)
            result.append(event.data)

        bus.subscribe(MyEvent, async_handler)

        await bus.publish(MyEvent(data="async"))

        assert len(result) == 1
        assert result[0] == "async"

    @pytest.mark.asyncio
    async def test_async_handler_task_policy(self):
        """Async handlers with TASK policy run as tasks."""
        bus = EventBus(default_exec_policy=ExecPolicy.TASK)
        result = []

        async def async_handler(event):
            await asyncio.sleep(0.01)
            result.append(event.data)

        bus.subscribe(MyEvent, async_handler, policy=ExecPolicy.TASK)

        await bus.publish(MyEvent(data="task"))

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_sync_handler_threadpool_policy(self):
        """Sync handlers with THREADPOOL policy run in executor."""
        bus = EventBus()
        result = []
        thread_ids = []

        def sync_handler(event):
            thread_ids.append(threading.current_thread().ident)
            result.append(event.data)

        bus.subscribe(MyEvent, sync_handler, policy=ExecPolicy.THREADPOOL)

        await bus.publish(MyEvent(data="threadpool"))

        assert len(result) == 1


class TestEventBusWorkerQueue:
    """Test worker queue functionality."""

    @pytest.mark.asyncio
    async def test_start_worker_creates_task(self):
        """start_worker() creates worker task."""
        bus = EventBus()

        await bus.start_worker()

        assert bus._worker_task is not None
        assert bus._worker_loop is not None

        await bus.aclose()

    @pytest.mark.asyncio
    async def test_stop_worker_stops_task(self):
        """stop_worker() stops the worker task."""
        bus = EventBus()

        await bus.start_worker()
        await bus.stop_worker()

        assert bus._worker_task is None

    @pytest.mark.asyncio
    async def test_post_with_worker(self):
        """post() queues events to worker."""
        bus = EventBus()
        results = []

        def handler(event):
            results.append(event.data)

        bus.subscribe(MyEvent, handler)

        await bus.start_worker()

        # Post from async context
        bus.post(MyEvent(data="queued"))

        # Wait for processing
        await asyncio.sleep(0.1)

        await bus.aclose()

        assert "queued" in results

    @pytest.mark.asyncio
    async def test_post_without_worker_raises(self):
        """post() raises if worker not started."""
        bus = EventBus()

        with pytest.raises(EventBusError):
            bus.post(MyEvent())


class TestEventBusClose:
    """Test EventBus close functionality."""

    @pytest.mark.asyncio
    async def test_aclose_clears_subscribers(self):
        """aclose() clears all subscribers."""
        bus = EventBus()

        def handler(event):
            pass

        bus.subscribe(MyEvent, handler)
        assert len(bus._subs) > 0

        await bus.start_worker()
        await bus.aclose()

        assert len(bus._subs) == 0
        assert bus._closed is True

    @pytest.mark.asyncio
    async def test_subscribe_after_close_raises(self):
        """subscribe() after close raises error."""
        bus = EventBus()

        await bus.start_worker()
        await bus.aclose()

        with pytest.raises(EventBusClosedError):
            bus.subscribe(MyEvent, lambda e: None)

    @pytest.mark.asyncio
    async def test_publish_after_close_raises(self):
        """publish() after close raises error."""
        bus = EventBus()

        await bus.start_worker()
        await bus.aclose()

        with pytest.raises(EventBusClosedError):
            await bus.publish(MyEvent())


class TestSubscribeDecorator:
    """Test @subscribe decorator."""

    def test_subscribe_decorator_registers_metadata(self):
        """@subscribe decorator adds subscription metadata."""

        @subscribe(MyEvent)
        def decorated_handler(event):
            pass

        assert hasattr(decorated_handler, "_pico_subscriptions_")
        subs = decorated_handler._pico_subscriptions_
        assert len(subs) == 1
        assert subs[0][0] is MyEvent

    def test_subscribe_decorator_with_priority(self):
        """@subscribe decorator accepts priority."""

        @subscribe(MyEvent, priority=5)
        def priority_handler(event):
            pass

        subs = priority_handler._pico_subscriptions_
        assert subs[0][1] == 5

    def test_subscribe_decorator_with_once(self):
        """@subscribe decorator accepts once flag."""

        @subscribe(MyEvent, once=True)
        def once_handler(event):
            pass

        subs = once_handler._pico_subscriptions_
        assert subs[0][3] is True

    def test_subscribe_decorator_stacking(self):
        """@subscribe can be stacked for multiple events."""

        @subscribe(AnotherEvent)
        @subscribe(MyEvent)
        def multi_handler(event):
            pass

        subs = multi_handler._pico_subscriptions_
        assert len(subs) == 2


class TestPublishSync:
    """Test synchronous publish functionality."""

    def test_publish_sync_works_outside_async(self):
        """publish_sync() works outside async context."""
        bus = EventBus()
        results = []

        def handler(event):
            results.append(event.data)

        bus.subscribe(MyEvent, handler)

        bus.publish_sync(MyEvent(data="sync"))

        assert len(results) == 1
        assert results[0] == "sync"


class TestAutoSubscriberMixin:
    """Test AutoSubscriberMixin functionality."""

    def test_autosubscriber_has_configure_method(self):
        """AutoSubscriberMixin has _pico_autosubscribe method."""
        assert hasattr(AutoSubscriberMixin, "_pico_autosubscribe")
