# tests/test_event_bus.py
import asyncio
import threading
import pytest
from typing import List
from pico_ioc import EventBus, ExecPolicy, ErrorPolicy, Event, subscribe, AutoSubscriberMixin

class MyEvent(Event):
    def __init__(self, value: int):
        self.value = value

def test_subscribe_and_publish_sync():
    bus = EventBus()
    seen: List[int] = []
    def handler(evt: MyEvent):
        seen.append(evt.value)
    bus.subscribe(MyEvent, handler)
    bus.publish_sync(MyEvent(42))
    assert seen == [42]

def test_priority_order_sync():
    bus = EventBus()
    seen: List[str] = []
    def h_low(evt: MyEvent):
        seen.append("low")
    def h_high(evt: MyEvent):
        seen.append("high")
    bus.subscribe(MyEvent, h_low, priority=0)
    bus.subscribe(MyEvent, h_high, priority=10)
    bus.publish_sync(MyEvent(1))
    assert seen == ["high", "low"]

@pytest.mark.asyncio
async def test_once_subscription_and_unsubscribe():
    bus = EventBus()
    seen: List[int] = []
    def handler(evt: MyEvent):
        seen.append(evt.value)
    bus.subscribe(MyEvent, handler, once=True)
    await bus.publish(MyEvent(1))
    await bus.publish(MyEvent(2))
    assert seen == [1]

@pytest.mark.asyncio
async def test_async_handler_inline_and_task_policy():
    bus = EventBus()
    seen: List[str] = []
    async def h_inline(evt: MyEvent):
        await asyncio.sleep(0)
        seen.append("inline")
    async def h_task(evt: MyEvent):
        await asyncio.sleep(0)
        seen.append("task")
    bus.subscribe(MyEvent, h_inline, priority=0, policy=ExecPolicy.INLINE)
    bus.subscribe(MyEvent, h_task, priority=0, policy=ExecPolicy.TASK)
    await bus.publish(MyEvent(0))
    assert set(seen) == {"inline", "task"}

@pytest.mark.asyncio
async def test_threadpool_policy():
    bus = EventBus()
    seen: List[str] = []
    def h_tp(evt: MyEvent):
        seen.append("tp")
    bus.subscribe(MyEvent, h_tp, policy=ExecPolicy.THREADPOOL)
    await bus.publish(MyEvent(0))
    assert seen == ["tp"]

@pytest.mark.asyncio
async def test_worker_queue_post_from_thread():
    bus = EventBus(max_queue_size=10)
    seen: List[int] = []
    def handler(evt: MyEvent):
        seen.append(evt.value)
    bus.subscribe(MyEvent, handler)
    await bus.start_worker()
    def producer():
        for i in range(3):
            bus.post(MyEvent(i))
    t = threading.Thread(target=producer)
    t.start()
    t.join()
    await asyncio.sleep(0.05)
    await bus.stop_worker()
    assert seen == [0, 1, 2]

@pytest.mark.asyncio
async def test_error_policy_raise():
    bus = EventBus(error_policy=ErrorPolicy.RAISE)
    def bad(evt: MyEvent):
        raise RuntimeError("boom")
    bus.subscribe(MyEvent, bad)
    with pytest.raises(Exception):
        await bus.publish(MyEvent(0))

def test_auto_subscriber_mixin():
    seen: List[int] = []
    class S(AutoSubscriberMixin):
        @subscribe(MyEvent, priority=5)
        def handle(self, evt: MyEvent):
            seen.append(evt.value)
    bus = EventBus()
    s = S()
    s._pico_autosubscribe(bus)
    bus.publish_sync(MyEvent(7))
    assert seen == [7]

