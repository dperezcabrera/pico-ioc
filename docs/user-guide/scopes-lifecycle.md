# Scopes, Lifecycle & lazy

Dependency Injection isn't just about wiring components together; it's also about managing their lifecycles. How many instances of a component should exist? When should they be created? When should they be destroyed?

`pico-ioc` gives you fine-grained control over this using scopes, lifecycle hooks, and lazy instantiation.

---

## 1. Scopes: Controlling Instance Lifecycles ♻️

The scope of a component defines how many instances of it will exist and how long they will live. You set the scope using the `scope="..."` parameter in the main registration decorators (`@component`, `@factory`, `@provides`).

`pico-ioc` supports several built-in scopes:

### `scope="singleton"` (Default)

- Definition: One instance per container. The first time a singleton component is requested (via `get` or `aget`), it's created. That same instance is then cached and returned for all subsequent requests within that container's lifetime.
- Use Case: This is the default and most common scope. Use it for stateless services, configuration objects, utility classes, database connection pools, etc. – anything that can be safely shared across the entire application.

```python
from pico_ioc import component, init

@component(scope="singleton")  # Explicitly singleton (also the default)
class MySingletonService:
    def __init__(self):
        print("SingletonService CREATED!")

container = init(modules=[__name__])

print("Getting service 1...")
s1 = container.get(MySingletonService)  # Output: SingletonService CREATED!

print("Getting service 2...")
s2 = container.get(MySingletonService)  # No output, uses cached instance

assert s1 is s2  # They are the exact same object
```

### `scope="prototype"`

- Definition: A new instance every time. Each call to `get` or `aget` for a prototype-scoped component results in a brand new instance being created. These instances are never cached.
- Use Case: Use this for stateful objects where each consumer needs its own isolated copy (e.g., a builder object, a temporary data holder). Use sparingly, as frequent object creation can impact performance.

```python
from pico_ioc import component, init

@component(scope="prototype")
class MyPrototype:
    def __init__(self):
        print("Prototype CREATED!")

container = init(modules=[__name__])

print("Getting prototype 1...")
p1 = container.get(MyPrototype)  # Output: Prototype CREATED!

print("Getting prototype 2...")
p2 = container.get(MyPrototype)  # Output: Prototype CREATED!

assert p1 is not p2  # They are different objects
```

### `scope="request"` (and other Context-Aware Scopes)

- Definition: One instance per active scope ID. These scopes rely on Python's `contextvars` (see ADR-003). You typically activate these scopes in middleware (e.g., for an incoming HTTP request). For the duration of that request (identified by a unique ID), the container will create one instance of the component. If the same component is requested again within the same request, the cached instance is returned. A different request (with a different ID) will get its own separate instance.
- Built-in Context Scopes: `"request"`, `"session"`, `"transaction"`.
- Use Case: Essential for web applications. Perfect for holding request-specific state (like the current user's ID, permissions, or per-request database transaction objects) without resorting to global variables or passing context down call stacks manually.

```python
import uuid
from pico_ioc import component, init

@component(scope="request")
class RequestData:
    def __init__(self):
        self.request_id = None  # Will be set externally
        print(f"RequestData CREATED for scope ID: {self.request_id}")

container = init(modules=[__name__])

# Simulate Request 1
req_id_1 = f"req-{uuid.uuid4().hex[:6]}"
print(f"--- Entering Request {req_id_1} ---")
with container.scope("request", req_id_1):  # Activate the 'request' scope
    print("Getting data 1...")
    data1 = container.get(RequestData)
    data1.request_id = req_id_1  # In real app, middleware sets this

    print("Getting data 2...")
    data2 = container.get(RequestData)  # Gets cached instance for req_id_1

    assert data1 is data2
    assert data1.request_id == req_id_1
print(f"--- Exiting Request {req_id_1} ---")


# Simulate Request 2
req_id_2 = f"req-{uuid.uuid4().hex[:6]}"
print(f"\n--- Entering Request {req_id_2} ---")
with container.scope("request", req_id_2):
    print("Getting data 3...")
    data3 = container.get(RequestData)  # Creates NEW instance for req_id_2
    data3.request_id = req_id_2

    assert data3 is not data1  # Different instance from Request 1
    assert data3.request_id == req_id_2
print(f"--- Exiting Request {req_id_2} ---")

# Output:
# --- Entering Request req-xxxxxx ---
# Getting data 1...
# RequestData CREATED for scope ID: None
# Getting data 2...
# --- Exiting Request req-xxxxxx ---

# --- Entering Request req-yyyyyy ---
# Getting data 3...
# RequestData CREATED for scope ID: None
# --- Exiting Request req-yyyyyy ---
```

See Integrations for how to manage `request` scopes in FastAPI/Flask: ../integrations/README.md

Also see ADR-003 for design details: ../adr/adr-0003-context-aware-scopes.md

-----

## 2. Lifecycle Hooks: `@configure` and `@cleanup` ⚙️

Sometimes, creating an object via `__init__` isn't enough. You might need to:

- Perform extra setup after all dependencies are injected (e.g., initialize a cache, start a background task).
- Release resources before the application shuts down (e.g., close database connections, flush buffers).

`pico-ioc` provides two decorators for these lifecycle methods:

### `@configure`

- Purpose: Marks a method to be called immediately after the component instance is fully created and all dependencies (including `__init__` and `__ainit__`) are resolved, but before the instance is returned by `get`/`aget`.
- Signature: Can take `self` and optionally inject other dependencies by type hint, just like `__init__`. Can be `async def`.
- Use Case: Post-construction initialization logic that requires dependencies. Breaking circular dependencies (see ADR-008).

```python
from pico_ioc import component, configure, init

@component
class Database: ...

@component
class CacheManager:
    def __init__(self, db: Database):
        self.db = db
        self.cache_initialized = False
        print("CacheManager __init__")

    @configure  # Called after __init__
    def initialize_cache(self):
        print("CacheManager @configure: Initializing cache...")
        # Logic using self.db potentially
        self.cache_initialized = True

container = init(modules=[__name__])
cache = container.get(CacheManager)
assert cache.cache_initialized is True

# Output:
# CacheManager __init__
# CacheManager @configure: Initializing cache...
```

See ADR-008 for circular dependency handling: ../adr/adr-0008-circular-dependencies.md

### `@cleanup`

- Purpose: Marks a method to be called when the container is shut down (via `container.cleanup_all()` or `container.cleanup_all_async()`).
- Signature: Should only take `self`. Can be `async def` (requires calling `cleanup_all_async`).
- Use Case: Releasing resources gracefully (closing files, network connections, thread pools).

```python
import asyncio
from pico_ioc import component, cleanup, init

@component
class ConnectionPool:
    def __init__(self):
        print("ConnectionPool CREATED")
        self.is_closed = False

    @cleanup  # Called by container.cleanup_all_async()
    async def close(self):
        print("ConnectionPool @cleanup: Closing connections...")
        await asyncio.sleep(0.01)  # Simulate async close
        self.is_closed = True

async def main():
    container = init(modules=[__name__])
    pool = await container.aget(ConnectionPool)

    print("Shutting down...")
    await container.cleanup_all_async()  # MUST call async version
    assert pool.is_closed is True

# Output:
# ConnectionPool CREATED
# Shutting down...
# ConnectionPool @cleanup: Closing connections...

asyncio.run(main())
```

-----

## 3. Lazy Instantiation: `lazy=True` 🛋️

By default, `pico-ioc` performs eager validation at startup (`init()`). It checks that all dependencies can be resolved. For singleton components, it usually creates them immediately (or soon after startup).

However, sometimes you have a singleton component that is:

- Heavy to initialize: Takes a long time or consumes significant resources.
- Rarely used: Only needed in specific code paths.

In these cases, you can defer its creation until it's actually requested for the first time using `lazy=True`.

- Parameter: `lazy=True` (applicable to `@component`, `@factory`, `@provides`).
- Behavior:
  - The component's dependencies are not fully validated at startup (only that providers exist). An error could still occur when it's first accessed if a transitive dependency is missing or misconfigured.
  - The component's `__init__`, `__ainit__`, and `@configure` methods are only called the first time `get` or `aget` is invoked for it.
  - After the first access, the instance is cached like a regular singleton.

```python
import time
from pico_ioc import component, init

@component(lazy=True)  # <-- Mark as lazy
class HeavyService:
    def __init__(self):
        print("HeavyService INITIALIZING (takes time)...")
        time.sleep(0.1)
        print("HeavyService READY.")

@component
class RegularService:
    def __init__(self, heavy: HeavyService):  # Depends on lazy service
        self.heavy = heavy
        print("RegularService created.")

print("Initializing container...")
container = init(modules=[__name__])
# NO output from HeavyService yet!
print("Container ready.")

print("\nGetting RegularService (triggers lazy load)...")
service = container.get(RegularService)
# Output:
# HeavyService INITIALIZING (takes time)...
# HeavyService READY.
# RegularService created.

print("\nGetting HeavyService again (cached)...")
heavy_cached = container.get(HeavyService)
# NO output, uses cached instance

assert service.heavy is heavy_cached
```

Use `lazy=True` judiciously. While it can improve startup time, it defers potential errors to runtime and can make performance less predictable on the first request that triggers the lazy load.

-----

## Next Steps

You now understand how to control when and how often your components are created and destroyed. The next step is dealing with situations where multiple components implement the same interface.

- Qualifiers & List Injection: Learn how to inject all implementations of an interface or select specific ones using tags — ./qualifiers-lists.md
