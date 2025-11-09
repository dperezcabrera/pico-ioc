# Design Principles

Understanding why pico-ioc is built the way it is helps in using it effectively and anticipating its behavior. The framework embodies specific design choices aimed at addressing common challenges in developing maintainable, robust, and scalable Python applications.

These core principles guided its architecture:

---

## 1. Fail-Fast at Startup ⚡

Principle: Detect configuration and dependency wiring errors immediately during application initialization (init()) rather than encountering them at runtime during operation (e.g., during a user request).

Rationale: Runtime errors like ProviderNotFoundError or CircularDependencyError caused by incorrect setup are disruptive, hard to debug in production, and can lead to unpredictable application states. Catching these issues early improves reliability and developer confidence.

Implementation:
- Eager Validation (ADR-006): During init(), the Registrar.validate_bindings step proactively analyzes the dependency graph. It verifies that a provider exists for every required dependency (excluding lazy=True components) in component constructors (__init__) and factory methods (@provides). If any dependency cannot be satisfied, init() raises an InvalidBindingError immediately, listing all issues.
- Cycle Detection (ADR-008): Circular dependencies are also detected during this static analysis phase or upon first resolution attempt, raising an InvalidBindingError with the full chain, preventing the application from starting with an unresolvable graph.

Trade-off: This eager validation adds a small overhead to application startup time. This is generally considered a worthwhile trade-off for increased runtime stability. lazy=True offers an escape hatch for components where startup performance is critical and delayed error detection is acceptable.

---

## 2. Observability First 🔭

Principle: In complex or distributed systems, understanding the container’s internal state, behavior, and context is crucial for debugging, monitoring, and performance tuning. Observability features should be integral, not bolted on later.

Rationale: Tracking component lifecycles, diagnosing resolution bottlenecks, or managing multiple container instances (e.g., in multi-tenant scenarios) becomes difficult without adequate introspection and monitoring tools.

Implementation (ADR-004):
- Container Context: Each container instance has a unique container_id. The with container.as_current() mechanism allows logs, metrics, and traces to be correlated to a specific container, even in concurrent or multi-instance environments. PicoContainer.get_current() and PicoContainer.all_containers() provide runtime access.
- Built-in Stats: container.stats() provides essential runtime metrics (uptime, resolve counts, cache hit rate) out of the box.
- Observer Protocol: ContainerObserver defines hooks (on_resolve, on_cache_hit) allowing integration with external monitoring and tracing systems (like OpenTelemetry). Observers are registered via init(observers=[...]).
- Graph Export: container.export_graph() enables visualization of the dependency structure using Graphviz, aiding architectural understanding and debugging.

---

## 3. Async-Native asyncio 🔄

Principle: Asynchronous programming with asyncio is standard for I/O-bound Python applications. A modern DI container must fully embrace async/await throughout the component lifecycle without resorting to thread pools for core operations or blocking the event loop.

Rationale: Components often need to perform async operations during initialization (__ainit__) or cleanup (async def @cleanup). A synchronous container forces complex workarounds or can degrade performance by blocking the event loop during resolution.

Implementation (ADR-001):
- aget(): A dedicated asynchronous resolution method (await container.aget(...)) that correctly handles async dependencies.
- Async Lifecycle: Native support for async def in factory @provides methods, the async def __ainit__ initializer convention, and async def @configure/@cleanup lifecycle hooks. Corresponding container.cleanup_all_async() method.
- Async AOP: MethodInterceptor.invoke can be async def, and the AOP proxy correctly awaits async intercepted methods and call_next.
- Async Event Bus: The built-in EventBus (ADR-007) is designed for asynchronous event handling.

---

## 4. Explicit Configuration over Convention ✨

Principle: Critical configuration and dependency wiring should be explicit and discoverable through decorators and type hints, minimizing reliance on implicit naming conventions or complex classpath scanning rules. Explicitness improves clarity and maintainability.

Rationale: Implicit conventions can make application behavior hard to follow and debug ("magic"). Explicit decorators (@component, @factory, @provides, @configured, etc.) and type-hint-based injection make the container’s setup clear and leverage static analysis tools.

Implementation:
- Decorator-Driven Registration: Components are registered via explicit decorators.
- Type Hint Injection: Dependencies are primarily resolved based on constructor/method type hints.
- Explicit Configuration Binding (ADR-010): The @configured decorator, combined with the configuration(...) builder, requires clear definitions of sources and explicit mapping parameters (prefix, mapping) or relies on predictable auto-detection based on the dataclass structure to bind configuration to objects.

---

## 5. Separation of Concerns (SoC) 🧩

Principle: Promote loose coupling and high cohesion by providing tools that help developers separate different kinds of logic (e.g., business logic, infrastructure concerns, configuration management).

Rationale: Tightly coupled code is difficult to test, maintain, and evolve. Mixing cross-cutting concerns (like logging, transaction management) directly into business logic reduces clarity and reusability.

Implementation:
- Dependency Injection: The core pattern inherently decouples components by externalizing dependency creation.
- AOP (@intercepted_by, ADR-005): Provides a dedicated mechanism to extract cross-cutting concerns into reusable MethodInterceptor components, keeping business logic clean.
- Event Bus (ADR-007): Enables further decoupling through asynchronous event-based communication (Publish/Subscribe) instead of direct service calls.
- Unified Configuration Binding (ADR-010): The @configured decorator and configuration(...) builder separate the loading, parsing, validation, and source management of configuration from the components that consume it.

---

## 6. Explicit Handling of Circular Dependencies ♻️ (ADR-008)

Principle: Circular dependencies should be treated as an explicit design decision, not resolved implicitly by the container through potentially fragile mechanisms like automatic proxy injection into constructors. The container must detect cycles and require developers to break them using clear, defined patterns.

Rationale: Automatically resolving cycles can hide architectural problems and lead to objects being used in partially initialized states. Failing fast during startup (InvalidBindingError) and requiring explicit patterns like @configure or provider injection ensures a predictable and robust component lifecycle.

Implementation:
- Fail-Fast Detection: Cycles are detected during eager validation in init(), raising an error with the full chain.
- No Implicit Resolution: pico-ioc deliberately avoids automatic proxy injection or lazy fields to break cycles within constructors.
- Promoted Explicit Patterns: Encourages using @configure methods, provider injection (Callable[[], T]), or the EventBus to break cycles explicitly where necessary.

Trade-off: Requires developers to manually implement cycle-breaking patterns, adding some boilerplate compared to frameworks with implicit resolution, but gaining predictability and lifecycle safety.

---

## Next Steps

Now that you understand the "Why" behind pico-ioc’s design, compare it to other libraries to see how these principles translate into distinct features and trade-offs.

- Comparison to Other Libraries (./comparison.md): See how pico-ioc stacks up against alternatives like dependency-injector, punq, and framework-native DI.
