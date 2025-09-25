## ADR-001: Native Asyncio Support

**Status:** Accepted

### Context

Modern Python web frameworks and I/O-bound applications heavily rely on `asyncio`. A synchronous DI container forces awkward workarounds (like running async initialization in `__init__` via `asyncio.run()`, which blocks) or cannot properly manage async resources. V1 lacked native support, hindering its use in async applications. We needed first-class `async`/`await` integration across the component lifecycle.

### Decision

We decided to make `pico-ioc` **async-native**. This involved several key changes:

1.  Introduce `container.aget(key)` as the asynchronous counterpart to `container.get(key)`. `aget` correctly handles `await`ing async operations during resolution without blocking the event loop.
2.  Support `async def` methods decorated with `@provides` within factories.
3.  Introduce the `async def __ainit__(self, ...)` convention for components needing async initialization after `__init__`. Dependencies can be injected into `__ainit__`.
4.  Allow `@configure` and `@cleanup` methods to be `async def`. A corresponding `container.cleanup_all_async()` method was added.
5.  Ensure the AOP (`MethodInterceptor`) mechanism is async-aware, correctly `await`ing `call_next(ctx)` and allowing `async def invoke`.
6.  Make the built-in `EventBus` fully asynchronous.

### Consequences

**Positive:** 👍
* Seamless integration with `asyncio`-based applications (FastAPI, etc.).
* Correct handling of async component initialization and cleanup without blocking.
* Enables fully asynchronous AOP and event handling.
* Improves developer experience for async projects.

**Negative:** 👎
* Introduces a dual API (`get`/`aget`), requiring developers to choose the correct one based on context.
* Slightly increases internal complexity to manage async operations correctly.
* Requires users to use `container.cleanup_all_async()` instead of `cleanup_all()` if any async cleanup methods exist.
