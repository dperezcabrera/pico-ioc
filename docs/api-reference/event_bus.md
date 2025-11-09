# `EventBus` API Reference 📨

The `EventBus` provides a lightweight, asynchronous pub–sub mechanism for decoupling components. It is provided by default when scanning the `pico_ioc.event_bus` module.

---

## Class: `EventBus`

### `subscribe(event_type, fn, *, priority=0, policy=ExecPolicy.INLINE, once=False)`

Registers a callback function (handler) for a specific event type.

- `event_type: Type[Event]`: The event class to listen for.
- `fn: Callable`: The function or async coroutine to call.
- `priority: int = 0`: Handlers with higher priority run first.
- `policy: ExecPolicy = ExecPolicy.INLINE`:
  - `INLINE`: (Default) The handler is awaited by `publish`.
  - `TASK`: Runs as a fire-and-forget `asyncio.Task`.
  - `THREADPOOL`: Runs a sync handler in a thread pool.
- `once: bool = False`: If `True`, the handler is removed after one execution.

Notes:
- Handlers can be sync or async. Sync handlers published with `INLINE` will be executed in place; use `THREADPOOL` to run sync handlers off the main loop.
- Priority ordering applies within the same event type; higher numbers execute first.
- Registering the same `(event_type, fn)` multiple times will result in multiple executions (one per registration).

---

### `unsubscribe(event_type, fn)`

Removes a specific handler for an event type. If the handler is not registered, this is a no-op.

---

### `async publish(event: Event)`

Asynchronously publishes an event, dispatching it to all registered subscribers.

- Behavior:
  - Immediately finds all subscribers for `type(event)`.
  - Executes handlers based on their `ExecPolicy`.
  - Awaits the completion of all `INLINE` handlers before returning.
  - Exceptions raised by handlers are surfaced as `EventBusHandlerError` unless otherwise handled by the policy.

- Usage:
  ```python
  await event_bus.publish(UserCreatedEvent(user_id=123))
  ```

---

### `publish_sync(event: Event)`

Synchronously publishes an event.

- Behavior:
  - If an event loop is running, it creates a task for `publish(event)`.
  - If no loop is running, it calls `asyncio.run(self.publish(event))`.

- Usage:
  Use when you must publish from a `def` function.

---

### `post(event: Event)`

Posts an event to an internal queue for processing by a background worker.

- Behavior: Non-blocking. Places the event in an `asyncio.Queue`.
- Requires: The background worker must be started via `await event_bus.start_worker()` for queued events to be processed.
- Thread Safety: Thread-safe and can be called from non-async threads.
- Queue Capacity: If a maximum queue size was configured, posting to a full queue raises `EventBusQueueFullError`.

- Usage:
  Advanced use for fire-and-forget queuing from any context, provided the worker is running.

---

### `async start_worker()`

Starts an `asyncio.Task` that continuously processes events from the internal queue (fed by `post()`). The task runs on the same event loop that `start_worker` was awaited on. Calling this when the worker is already running is a no-op.

---

### `async stop_worker()`

Gracefully stops the background worker task by queuing a `None` signal and waiting for the queue to be processed. Safe to call if the worker is not running (no-op).

---

### `async aclose()`

Stops the worker (if running) and cleans up all resources, clearing all subscribers. After closing, any call to `publish` or `post` raises `EventBusClosedError`. This is called automatically by `@cleanup` if the `PicoEventBusProvider` is used.

---

## Decorator: `@subscribe(...)`

A decorator to mark methods as event handlers. Used with `AutoSubscriberMixin`.

```python
from pico_ioc import component, subscribe
from pico_ioc.event_bus import AutoSubscriberMixin, Event, ExecPolicy

class MyEvent(Event):
    ...

@component
class MyListener(AutoSubscriberMixin):

    @subscribe(MyEvent, policy=ExecPolicy.TASK, priority=5, once=False)
    async def on_my_event(self, event: MyEvent):
        print("Got event in the background!")
```

- Supported options: `priority=0`, `policy=ExecPolicy.INLINE`, `once=False`.
- Methods can be sync or async; choose `policy` accordingly.
- `AutoSubscriberMixin` scans decorated methods and registers/unregisters them automatically during component lifecycle.

-----

## Exceptions

| Exception | Raised When |
| :--- | :--- |
| `EventBusClosedError` | `publish` or `post` is called after `aclose()`. |
| `EventBusQueueFullError` | `post()` is called on a full queue (if `max_queue_size` was set). |
| `EventBusHandlerError` | A subscriber function raises an unhandled exception. |
| `EventBusError` | `post()` is called without the worker running. |

---

## Notes

- Threading and concurrency:
  - `post()` is safe to call from any thread; events are processed on the loop where `start_worker()` was called.
  - Use `THREADPOOL` for CPU-bound or blocking sync handlers to avoid blocking the event loop.
- Integration:
  - The default `EventBus` instance is provided by scanning `pico_ioc.event_bus`.
  - Cleanup is automatic when using `PicoEventBusProvider` together with `@cleanup`.
