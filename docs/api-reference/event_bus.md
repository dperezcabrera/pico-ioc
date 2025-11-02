# `EventBus` API Reference 📨

The `EventBus` provides a lightweight, asynchronous pub–sub mechanism for decoupling components. It is provided by default when scanning the `pico_ioc.event_bus` module.

---

## Class: `EventBus`

### **`subscribe(event_type, fn, *, priority, policy, once)`**

Registers a callback function (handler) for a specific event type.

* **`event_type: Type[Event]`**: The event class to listen for.
* **`fn: Callable`**: The function or async coroutine to call.
* **`priority: int = 0`**: Handlers with higher priority run first.
* **`policy: ExecPolicy = ExecPolicy.INLINE`**:
    * `INLINE`: (Default) The handler is awaited by `publish`.
    * `TASK`: Runs as a fire-and-forget `asyncio.Task`.
    * `THREADPOOL`: Runs a sync handler in a thread pool.
* **`once: bool = False`**: If `True`, the handler is removed after one execution.

---

### **`unsubscribe(event_type, fn)`**

Removes a specific handler for an event type.

---

### **`async publish(event: Event)`**

Asynchronously publishes an event, dispatching it to all registered subscribers.

* **Behavior**:
    * Immediately finds all subscribers for `type(event)`.
    * Executes handlers based on their `ExecPolicy`.
    * `await`s the completion of all `INLINE` handlers before returning.

* **Usage**: This is the primary method for publishing events in an `async` context.

    ```python
    await event_bus.publish(UserCreatedEvent(user_id=123))
    ```

---

### **`publish_sync(event: Event)`**

Synchronously publishes an event.

* **Behavior**: This is a bridge for calling from synchronous code.
    * If an event loop is running, it creates a task for `publish(event)`.
    * If no loop is running, it calls `asyncio.run(self.publish(event))`.

* **Usage**: Use when you must publish from a `def` function.

---

### **`post(event: Event)`**

Posts an event to an internal queue for processing by a background worker.

* **Behavior**: This method is non-blocking. It places the event in an `asyncio.Queue`.
* **Requires**: The background worker must be started via `await event_bus.start_worker()` for these events to be processed.
* **Thread Safety**: This method is thread-safe and can be called from non-async threads.

* **Usage**: Advanced use for "fire-and-forget" queuing from any context, provided the worker is running.

---

### **`async start_worker()`**

Starts an `asyncio.Task` that continuously processes events from the internal queue (fed by `post()`). The task runs on the same event loop that `start_worker` was awaited on.

---

### **`async stop_worker()`**

Gracefully stops the background worker task by queuing a `None` signal and waiting for the queue to be processed.

---

### **`async aclose()`**

Stops the worker (if running) and cleans up all resources, clearing all subscribers. This is called automatically by `@cleanup` if the `PicoEventBusProvider` is used.

---

## Decorator: `@subscribe(...)`

A decorator to mark methods as event handlers. Used with `AutoSubscriberMixin`.

```python
from pico_ioc import component, subscribe
from pico_ioc.event_bus import AutoSubscriberMixin, Event, ExecPolicy

class MyEvent(Event): ...

@component
class MyListener(AutoSubscriberMixin):

    @subscribe(MyEvent, policy=ExecPolicy.TASK)
    async def on_my_event(self, event: MyEvent):
        print("Got event in the background!")
```

-----

## Exceptions

| Exception | Raised When |
| :--- | :--- |
| **`EventBusClosedError`** | `publish` or `post` is called after `aclose()`. |
| **`EventBusQueueFullError`** | `post()` is called on a full queue (if `max_queue_size` was set). |
| **`EventBusHandlerError`** | A subscriber function raises an unhandled exception. |
| **`EventBusError`** | `post()` is called without the worker running. |

