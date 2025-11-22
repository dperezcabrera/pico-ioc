# Runtime Model: Scheduling and Contexts

This document describes how the pico_ioc container runtime schedules dependency resolution, manages per-context lifetimes, tracks resolution/caching statistics, cleans up resources at shutdown, and preserves container context across asynchronous calls.

It is based on unit tests that verify:
- Container identity uniqueness
- Context isolation and nested context managers
- Resolution reuse and caching statistics
- Shutdown cleanup hooks
- Preservation of the current container context across async calls

## What is this?

The runtime model is the set of rules the container follows when resolving dependencies at runtime. Key aspects:

- Container identity
  - Each container instance has a unique identity (e.g., `container.id`).
  - Identity guarantees help differentiate containers in multi-tenant or multi-environment scenarios.

- Contexts (scopes)
  - A context is a temporary resolution scope with its own cache.
  - Contexts are entered via a context manager and ensure isolation of instances between contexts.
  - Nested contexts create new, isolated caches so inner resolutions do not leak into outer scopes.

- Scheduling and caching
  - Within a single context, resolutions of the same type can be reused (per-context caching).
  - The container tracks resolution and cache-hit statistics to aid tuning and diagnostics.

- Shutdown semantics
  - When the container shuts down, it runs cleanup hooks for resolved instances (e.g., closing connections).
  - This ensures predictable resource teardown.

- Async context preservation
  - The active context is preserved across `await` boundaries.
  - Resolutions done in async functions see the same context as the caller, avoiding unintended cross-task leakage.

## How do I use it?

Below are example usage patterns reflecting the runtime model. They demonstrate contexts, resolution reuse, statistics, cleanup, and async preservation.

### Create a container and inspect identity

```python
from pico_ioc import Container

container_a = Container()
container_b = Container()

assert container_a.id != container_b.id
print(f"A: {container_a.id}, B: {container_b.id}")
```

Each container instance has a unique identity. Use this to ensure you are operating on the intended container.

### Define components

```python
# Simple components
class SimpleA:
    pass

class SimpleB:
    pass

# Constructor-injected dependency
class NeedsSimpleA:
    def __init__(self, a: SimpleA):
        self.a = a

# Cache implementations for different environments
class RedisCache:
    def close(self):
        print("Redis connection closed")

class InMemoryCache:
    def close(self):
        print("In-memory cache flushed")

# Async component
class AsyncService:
    def __init__(self):
        self.ready = True
```

The container can resolve classes and inject constructor dependencies (e.g., `NeedsSimpleA` gets a `SimpleA`).

### Resolve dependencies inside an isolated context

```python
# Enter a context (scope) to resolve instances
with container_a.context() as ctx:
    a1 = ctx.resolve(SimpleA)
    a2 = ctx.resolve(SimpleA)
    needs_a = ctx.resolve(NeedsSimpleA)

    # Per-context caching: a1 and a2 may be the same instance
    assert needs_a.a is a1

# Outside the context, you get a fresh scope on next entry
with container_a.context() as another_ctx:
    a3 = another_ctx.resolve(SimpleA)
    # a3 is isolated from previous context's cache
    assert a3 is not a1
```

- Use `container.context()` to create a context manager that yields a context.
- Call `ctx.resolve(Type)` to obtain instances.
- Resolutions inside a single context can be reused, but contexts are isolated from each other.

### Nested contexts

```python
with container_a.context() as outer:
    outer_a = outer.resolve(SimpleA)

    with container_a.context() as inner:
        inner_a = inner.resolve(SimpleA)

    # Nested context is isolated: inner_a is not reused in outer
    assert inner_a is not outer_a
```

Nested contexts create new caches; resolutions in inner contexts do not affect outer contexts.

### Environment-specific bindings (dev vs prod caches)

You can schedule different implementations based on environment. For example, use `RedisCache` in production and `InMemoryCache` in development.

```python
import os

env = os.getenv("APP_ENV", "dev")

with container_a.context() as ctx:
    if env == "prod":
        cache = ctx.resolve(RedisCache)
    else:
        cache = ctx.resolve(InMemoryCache)

    # use cache ...
```

Bind and resolve the appropriate implementation for the current environment. Ensure cleanup runs during shutdown.

### Resolution and caching statistics

Track how often the container resolves and how often it serves from cache.

```python
with container_a.context() as ctx:
    _ = ctx.resolve(SimpleA)
    _ = ctx.resolve(SimpleA)  # likely served from cache

stats = container_a.stats()  # aggregated runtime stats
print("Total resolutions:", stats.resolutions)
print("Cache hits:", stats.cache_hits)
```

Use statistics to understand resolution patterns:
- `resolutions`: number of times types were actually constructed.
- `cache_hits`: number of times a cached instance was reused.

Note: Stats may be aggregated per container or per context depending on your configuration.

### Shutdown cleanup

When you are done, shut down the container to release resources.

```python
with container_a.context() as ctx:
    cache = ctx.resolve(RedisCache)  # or InMemoryCache
    # ... work with cache

# Trigger cleanup for tracked instances
container_a.shutdown()
```

Shutdown runs cleanup hooks (e.g., `close()`) so resources are properly released. Ensure you call `shutdown()` during application teardown.

### Async context preservation

The active context is preserved across `await` boundaries so your async functions resolve within the same scope.

```python
import asyncio

async def async_helper_function():
    # This function runs under the caller's context
    svc = container_a.resolve(AsyncService)
    assert svc.ready
    return svc

async def main():
    with container_a.context() as ctx:
        # Resolve before await
        pre = ctx.resolve(SimpleA)

        # Context is preserved inside awaited function
        svc = await async_helper_function()

        # Resolve after await; still within the same context
        post = ctx.resolve(SimpleA)
        assert pre is post  # per-context caching holds across async boundaries

asyncio.run(main())
```

- Enter a context before starting async operations.
- Resolutions inside awaited functions continue to use the same context.
- This avoids cross-task leakage and maintains per-context caching correctness.

## Tips

- Use contexts liberally to define clear lifetimes for resolved instances.
- Inspect stats regularly during development to catch excessive resolutions or missed caching.
- Always call `shutdown()` during teardown to ensure all resources are cleaned up.
- For asynchronous workflows, open the context at the boundary of the async operation (e.g., in request handlers or task runners) so it flows through all awaited calls.