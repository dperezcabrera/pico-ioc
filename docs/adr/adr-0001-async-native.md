## ADR-001: Native Asyncio Support

Status: Accepted

### Context

Modern Python web frameworks and I/O-bound applications heavily rely on asyncio. A synchronous DI container forces awkward workarounds (like running async initialization in __init__ via asyncio.run(), which blocks) or cannot properly manage async resources. V1 lacked native support, hindering its use in async applications. We needed first-class async/await integration across the component lifecycle.

### Decision

We decided to make pico-ioc async-native. This involved several key changes:

1. Introduce container.aget(key) as the asynchronous counterpart to container.get(key). aget correctly awaits async operations during resolution without blocking the event loop.
2. Support async def methods decorated with @provides within factories.
3. Introduce the async def __ainit__(self, ...) convention for components needing async initialization after __init__. Dependencies can be injected into __ainit__.
4. Allow @configure and @cleanup methods to be async def. A corresponding container.cleanup_all_async() method was added.
5. Ensure the AOP (MethodInterceptor) mechanism is async-aware, correctly awaiting call_next(ctx) and allowing async def invoke.
6. Make the built-in EventBus fully asynchronous.

### Details

- Resolution semantics:
  - container.get(key) resolves components whose providers, lifecycle hooks, and initialization are entirely synchronous.
  - container.aget(key) resolves components and awaits any async provider, __ainit__, @configure, or interceptor invocation encountered during the resolution graph.
  - When a resolution path contains any awaitable, aget must be used; get will not run the event loop.

- Lifecycle semantics:
  - Construction: __init__ runs synchronously.
  - Async initialization: if defined, __ainit__ runs after __init__ and may receive injected dependencies; it is awaited during aget.
  - Configuration: @configure may be sync or async; aget will await async configurations.
  - Cleanup: @cleanup may be sync or async. Use container.cleanup_all_async() to ensure async cleanup is awaited; container.cleanup_all() only invokes synchronous cleanup.

- Providers:
  - @provides methods may be sync or async. Async providers are supported in factories and modules; they are awaited during aget.
  - Provider selection remains unchanged; only execution mode differs based on sync vs async.

- AOP:
  - MethodInterceptor.invoke can be defined as def or async def.
  - call_next(ctx) may return a value or an awaitable; the interceptor framework detects awaitables and awaits them when necessary.
  - Interceptor chains support mixing sync and async interceptors. The final invocation respects the async nature of the underlying target.

- EventBus:
  - Handlers may be async functions.
  - Publishing and dispatch are performed asynchronously; dispatch awaits all async handlers.
  - Ordering and error propagation remain deterministic; exceptions in handlers are surfaced to the publisher as awaited failures.

### Consequences

Positive:
- Seamless integration with asyncio-based applications (FastAPI, etc.).
- Correct handling of async component initialization and cleanup without blocking.
- Enables fully asynchronous AOP and event handling.
- Improves developer experience for async projects.

Negative:
- Introduces a dual API (get/aget), requiring developers to choose the correct one based on context.
- Increases internal complexity to manage mixed sync/async operations correctly.
- Requires users to use container.cleanup_all_async() instead of cleanup_all() if any async cleanup methods exist.
- Testing and debugging can be more complex when mixing sync and async lifecycles.

### Alternatives Considered

- Implicit event-loop management inside get:
  - Rejected. Running the loop implicitly (e.g., via asyncio.run) in synchronous APIs can deadlock or conflict with frameworks that manage the loop, and breaks composability.
- Separate async-only container:
  - Rejected. Maintaining two containers increases surface area and duplication; a unified container with dual APIs is simpler and more ergonomic.

### Backward Compatibility

- Existing synchronous components, providers, interceptors, and cleanup methods continue to work without changes using container.get and container.cleanup_all.
- New async capabilities are opt-in. Projects can incrementally adopt aget and async lifecycle hooks.
- If any component in a dependency chain requires async work, callers must use container.aget. Using container.get in such cases will not execute async code and may lead to partially initialized components.

### Migration Guide

- Identify components that perform I/O or require awaiting during initialization or configuration. Move such logic from __init__ into __ainit__.
- Convert providers that need I/O to async def and decorate with @provides as before.
- Where components define async cleanup, call container.cleanup_all_async() in application shutdown routines.
- Update interceptor implementations to async def invoke when they need to await downstream calls; otherwise def invoke remains valid.
- In application composition and request handling paths, replace container.get with container.aget when resolving components that may involve async work.

### Testing Notes

- Prefer pytest-asyncio or equivalent to run async tests that exercise container.aget, async providers, __ainit__, and async interceptors.
- For cleanup verification, use container.cleanup_all_async() in async tests; use container.cleanup_all() in purely synchronous tests.
- When mixing sync and async interceptors, assert both execution order and awaited behavior to avoid hidden concurrency issues.

### Open Questions

- Whether to provide helper diagnostics to detect misuse of get when async work is required.
- Whether to add optional timeouts for async cleanup and event dispatch to guard against hung coroutines.
