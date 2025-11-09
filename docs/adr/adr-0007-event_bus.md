## ADR-007: Built-in Asynchronous Event Bus

Status: Accepted

### Context

Decoupling components is a core tenet of DI. While direct injection works well, complex applications benefit from an event-driven approach where components can react to events without direct coupling (Publish/Subscribe pattern). Providing a standard, integrated event bus simplifies implementing this pattern.

### Decision

We included a built-in, asynchronous event bus as part of the core library:

1. Event base class: A simple marker class for event objects (typically dataclasses) that identifies messages as events.
2. EventBus component: A core, injectable component (registered via the pico_ioc.event_bus module) responsible for managing subscriptions and dispatching events. It supports await bus.publish(event) for immediate, awaited handling and bus.post(event) for queued, background processing.
3. @subscribe(EventType, ...) decorator: Marks methods as event handlers for specific event types. Supports priority and ExecPolicy (INLINE, TASK, THREADPOOL) for controlling execution order and concurrency.
4. AutoSubscriberMixin: A convenience mixin class. Components inheriting from it will have their @subscribe methods automatically registered with the EventBus when the component is created (via an @configure hook).
5. Async native: The bus and handlers are designed for asyncio, allowing async def handlers and non-blocking publishing.

### Usage

- Register the pico_ioc.event_bus module during container initialization so the EventBus is available for injection.
- Define events as plain dataclasses inheriting from Event.
- Annotate component methods with @subscribe(MyEvent, priority=?, policy=ExecPolicy.?) to handle events; these methods may be sync or async.
- Derive components from AutoSubscriberMixin to automatically register all @subscribe methods on creation.
- Use await bus.publish(event) when the publisher must await completion of all handlers; use bus.post(event) to queue handling in the background according to the selected ExecPolicy.

### Consequences

Positive:
- Promotes loosely coupled, event-driven architectures within applications using pico-ioc.
- Provides a standard, ready-to-use solution, reducing boilerplate for developers.
- Fully integrated with the DI container (bus is injectable, subscribers are components).
- Async-native design fits well with modern Python applications.
- ExecPolicy offers control over handler execution (critical path vs. background tasks).

Negative:
- Adds features beyond core DI, slightly increasing library scope.
- The event bus is currently in-process and synchronous in its core dispatch loop for publish (though handlers can be async or run in threads). It is not a replacement for distributed message queues (like RabbitMQ or Kafka).
- Requires explicit registration of the pico_ioc.event_bus module during init().
