import asyncio
import inspect
import logging
import threading
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Tuple, Type
from .api import factory, provides, configure, cleanup
from .exceptions import EventBusClosedError, EventBusError, EventBusQueueFullError, EventBusHandlerError

log = logging.getLogger(__name__)

class ExecPolicy(Enum):
    INLINE = auto()
    THREADPOOL = auto()
    TASK = auto()

class ErrorPolicy(Enum):
    LOG = auto()
    RAISE = auto()

class Event: ...

@dataclass(order=True)
class _Subscriber:
    sort_index: int = field(init=False, repr=False, compare=True)
    priority: int = field(compare=False)
    callback: Callable[[Event], Any] | Callable[[Event], Awaitable[Any]] = field(compare=False)
    policy: ExecPolicy = field(compare=False)
    once: bool = field(compare=False)
    def __post_init__(self):
        self.sort_index = -int(self.priority)

class EventBus:
    def __init__(
        self,
        *,
        default_exec_policy: ExecPolicy = ExecPolicy.INLINE,
        error_policy: ErrorPolicy = ErrorPolicy.LOG,
        max_queue_size: int = 0,
    ):
        self._subs: Dict[Type[Event], List[_Subscriber]] = {}
        self._default_policy = default_exec_policy
        self._error_policy = error_policy
        self._queue: Optional[asyncio.Queue[Event]] = asyncio.Queue(max_queue_size) if max_queue_size >= 0 else None
        self._worker_task: Optional[asyncio.Task] = None
        self._worker_loop: Optional[asyncio.AbstractEventLoop] = None
        self._closed = False
        self._lock = threading.RLock()

    def subscribe(
        self,
        event_type: Type[Event],
        fn: Callable[[Event], Any] | Callable[[Event], Awaitable[Any]],
        *,
        priority: int = 0,
        policy: Optional[ExecPolicy] = None,
        once: bool = False,
    ) -> None:
        with self._lock:
            if self._closed:
                raise EventBusClosedError()
            sub = _Subscriber(priority=priority, callback=fn, policy=policy or self._default_policy, once=once)
            lst = self._subs.setdefault(event_type, [])
            if any(s.callback is fn for s in lst):
                return
            lst.append(sub)
            lst.sort()

    def unsubscribe(self, event_type: Type[Event], fn: Callable[[Event], Any] | Callable[[Event], Awaitable[Any]]) -> None:
        with self._lock:
            lst = self._subs.get(event_type, [])
            self._subs[event_type] = [s for s in lst if s.callback is not fn]

    def publish_sync(self, event: Event) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self.publish(event))
            return
        if loop.is_running():
            async def _bridge():
                await self.publish(event)
            loop.create_task(_bridge())
        else:
            asyncio.run(self.publish(event))

    async def publish(self, event: Event) -> None:
        if self._closed:
            raise EventBusClosedError()
        with self._lock:
            subs = list(self._subs.get(type(event), []))
        to_remove: List[_Subscriber] = []
        pending: List[asyncio.Task] = []
        for sub in subs:
            try:
                cb = sub.callback
                if inspect.iscoroutinefunction(cb):
                    if sub.policy is ExecPolicy.TASK:
                        pending.append(asyncio.create_task(cb(event)))
                    else:
                        await cb(event)
                else:
                    if sub.policy is ExecPolicy.THREADPOOL:
                        loop = asyncio.get_running_loop()
                        await loop.run_in_executor(None, cb, event)
                    else:
                        cb(event)
                if sub.once:
                    to_remove.append(sub)
            except Exception as ex:
                self._handle_error(EventBusHandlerError(type(event).__name__, getattr(sub.callback, "__name__", "<callback>"), ex))
        if pending:
            try:
                await asyncio.gather(*pending, return_exceptions=False)
            except Exception as ex:
                self._handle_error(EventBusError(f"Unhandled error awaiting event tasks: {ex}"))
        if to_remove:
            with self._lock:
                lst = self._subs.get(type(event), [])
                self._subs[type(event)] = [s for s in lst if s not in to_remove]

    async def start_worker(self) -> None:
        if self._closed:
            raise EventBusClosedError()
        if self._worker_task:
            return
        if self._queue is None:
            self._queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        self._worker_loop = loop
        async def _worker():
            while True:
                evt = await self._queue.get()
                if evt is None:
                    self._queue.task_done()
                    break
                try:
                    await self.publish(evt)
                finally:
                    self._queue.task_done()
        self._worker_task = asyncio.create_task(_worker())

    async def stop_worker(self) -> None:
        if self._worker_task and self._queue and self._worker_loop:
            await self._queue.put(None)
            await self._queue.join()
            await self._worker_task
            self._worker_task = None
            self._worker_loop = None

    def post(self, event: Event) -> None:
        with self._lock:
            if self._closed:
                raise EventBusClosedError()
            if self._queue is None:
                raise EventBusError("Worker queue not initialized. Call start_worker().")
            
            queue_ref = self._queue
            loop_ref = self._worker_loop

        if loop_ref and loop_ref.is_running():
            try:
                current_loop = asyncio.get_running_loop()
                if current_loop is loop_ref:
                    try:
                        queue_ref.put_nowait(event)
                        return
                    except asyncio.QueueFull:
                        raise EventBusQueueFullError()
            except RuntimeError:
                pass
            try:
                loop_ref.call_soon_threadsafe(queue_ref.put_nowait, event)
                return
            except asyncio.QueueFull:
                raise EventBusQueueFullError()
        else:
            raise EventBusError("Worker queue not initialized or loop not running. Call start_worker().")

    async def aclose(self) -> None:
        await self.stop_worker()
        with self._lock:
            self._closed = True
            self._subs.clear()

    def _handle_error(self, ex: EventBusError) -> None:
        if self._error_policy is ErrorPolicy.RAISE:
            raise ex
        if self._error_policy is ErrorPolicy.LOG:
            log.exception("%s", ex)

def subscribe(event_type: Type[Event], *, priority: int = 0, policy: ExecPolicy = ExecPolicy.INLINE, once: bool = False):
    def dec(fn: Callable[[Event], Any] | Callable[[Event], Awaitable[Any]]):
        subs: Iterable[Tuple[Type[Event], int, ExecPolicy, bool]] = getattr(fn, "_pico_subscriptions_", ())
        subs = list(subs)
        subs.append((event_type, int(priority), policy, bool(once)))
        setattr(fn, "_pico_subscriptions_", tuple(subs))
        return fn
    return dec

class AutoSubscriberMixin:
    @configure
    def _pico_autosubscribe(self, event_bus: EventBus) -> None:
        for _, attr in inspect.getmembers(self, predicate=callable):
            subs: Iterable[Tuple[Type[Event], int, ExecPolicy, bool]] = getattr(attr, "_pico_subscriptions_", ())
            for evt_t, pr, pol, once in subs:
                event_bus.subscribe(evt_t, attr, priority=pr, policy=pol, once=once)

@factory()
class PicoEventBusProvider:
    @provides(EventBus, primary=True)
    def build(self) -> EventBus:
        return EventBus()
    @cleanup
    def shutdown(self, event_bus: EventBus) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(event_bus.aclose())
            return
        if loop.is_running():
            loop.create_task(event_bus.aclose())
        else:
            asyncio.run(event_bus.aclose())
