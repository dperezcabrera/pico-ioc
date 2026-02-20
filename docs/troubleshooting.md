# Troubleshooting

This guide uses a symptom-first approach: find the problem you're experiencing
and follow the steps to fix it.

For a complete list of every error message produced by pico-ioc, see the
[Error Reference](./faq.md#troubleshooting----error-reference) in the FAQ.

If you're using pico-boot, pico-fastapi, or pico-pydantic, see also the
[unified pico-boot troubleshooting guide](https://github.com/dperezcabrera/pico-boot/blob/main/docs/troubleshooting.md).

---

## "My component is not found" (`ProviderNotFoundError`)

```
ProviderNotFoundError: Provider for key 'Database' not found (required by: 'UserService')
```

### Step 1: Is the class decorated with `@component`?

```python
from pico_ioc import component

@component          # required
class Database:
    pass
```

### Step 2: Is the module included in `init()`?

```python
container = init(modules=[
    "myapp.database",   # must be listed
    "myapp.services",
])
```

> **Common mistake:** listing the package (`"myapp"`) instead of the module.
> `init(modules=["myapp"])` only scans `myapp/__init__.py`. If `Database`
> lives in `myapp/database.py`, list it explicitly or re-export from
> `__init__.py`.

### Step 3: Is it a third-party class you can't decorate?

Use `@provides` instead:

```python
from pico_ioc import provides

@provides(redis.Redis)
def build_redis(config: RedisConfig) -> redis.Redis:
    return redis.Redis.from_url(config.URL)
```

### Step 4: Is there a typo in the type hint?

The type hint must exactly match the registered class:

```python
# Wrong - typo
def __init__(self, db: Databse): ...

# Correct
def __init__(self, db: Database): ...
```

### Step 5: Is the component conditionally excluded?

If using profiles, verify the component's `conditional_profiles` matches:

```python
@component(conditional_profiles=("prod",))
class ProdOnlyService: ...

# This won't find ProdOnlyService:
container = init(modules=["myapp"], profiles=("dev",))
```

---

## "Circular dependency detected" (`InvalidBindingError`)

```
InvalidBindingError: Invalid bindings:
- Circular dependency detected: ServiceA -> ServiceB -> ServiceA
```

### Option 1: Use `lazy=True` on one side

```python
@component(lazy=True)
class ServiceA:
    def __init__(self, b: "ServiceB"):
        self.b = b
```

The lazy component receives a proxy that resolves on first attribute access,
breaking the initialization cycle.

### Option 2: Use an event to decouple

If the dependency is only needed for notifications, replace the direct
dependency with an event:

```python
from pico_ioc import component, subscribe, Event

class UserCreated(Event):
    user_id: int

@component
class ServiceA:
    def __init__(self, bus: EventBus):
        self.bus = bus

    async def create_user(self):
        # ... create user ...
        await self.bus.publish(UserCreated(user_id=42))

@component
class ServiceB:
    @subscribe(UserCreated)
    async def on_user_created(self, event: UserCreated):
        # ... react to event ...
        pass
```

### Option 3: Restructure the dependency

Often a circular dependency signals a missing abstraction. Extract the shared
logic into a third component that both sides depend on.

---

## "Synchronous get() received an awaitable" (`AsyncResolutionError`)

```
AsyncResolutionError: Synchronous get() received an awaitable for key 'X'. Use aget() instead.
```

### Cause

You called `container.get()` on a component that has async initialization
(`__ainit__`, async `@configure`, or an async `@provides` factory).

### Fix 1: Use `aget()`

```python
service = await container.aget(AsyncService)
```

### Fix 2: Mark the component as `lazy=True`

```python
@component(lazy=True)
class AsyncService:
    async def __ainit__(self):
        self.conn = await create_connection()
```

Lazy components return a proxy from `get()` that defers async initialization
until the first attribute access in an async context.

### Decision matrix

| Scenario | Use |
|----------|-----|
| You're in an async context (e.g., FastAPI handler) | `await container.aget(X)` |
| You need the component in a sync context | `@component(lazy=True)` |
| You're using pico-fastapi | Automatic -- controllers use `aget()` internally |

---

## "Scope 'request' is not active" (`ScopeError`)

```
ScopeError: Cannot resolve component in scope 'request': No active scope ID found.
```

### Cause

You called `container.get(RequestScopedComponent)` outside of a scope context.

### Fix

Wrap the resolution in the appropriate scope:

```python
with container.scope("request", request_id):
    component = container.get(RequestScopedComponent)
```

With **pico-fastapi**, this is handled automatically by `PicoScopeMiddleware`.
If you see this error with pico-fastapi, check that:

1. Your middleware priority is correct (negative = outer, positive = inner)
2. You're not resolving request-scoped components in startup events or
   background tasks

---

## "Unknown scope" (`ScopeError`)

```
ScopeError: Unknown scope: tenant
```

### Cause

A component uses `scope="tenant"`, but the scope was not registered.

### Fix

Pass `custom_scopes` to `init()`:

```python
container = init(
    modules=["myapp"],
    custom_scopes=["tenant"],
)
```

See [How to Create Custom Scopes](./how-to/custom-scopes.md) for a full
example.

---

## "Missing configuration key" (`ConfigurationError`)

```
ConfigurationError: Missing configuration key: DB_HOST
```

### Cause

A `@configured` dataclass has a required field with no default, and no
configuration source provides a value for that key.

### Fix

Either provide the key in your configuration source:

```bash
export DB_HOST=myhost
```

Or add a default value:

```python
@configured(prefix="DB_")
@dataclass
class DbConfig:
    host: str = "localhost"  # default value
```

### Configuration precedence

Later sources override earlier ones:

1. Default values in the dataclass
2. YAML/JSON files (in the order specified)
3. Environment variables (highest priority)

See [Configuration Binding](./user-guide/configuration-binding.md) for the
full precedence rules.

---

## "Async interceptor returned awaitable on sync method"

```
RuntimeError: Async interceptor returned awaitable on sync method: method_name
```

### Cause

An interceptor's `invoke()` method returned a coroutine, but the intercepted
method is synchronous.

### Fix

Ensure your interceptor handles both sync and async methods:

```python
class MyInterceptor(MethodInterceptor):
    def invoke(self, ctx: MethodCtx):
        # For sync methods, don't await
        result = ctx.proceed()
        return result

    async def ainvoke(self, ctx: MethodCtx):
        # For async methods
        result = await ctx.proceed()
        return result
```

Or only apply the interceptor to async methods.

---

## "My override is not working in tests"

### Common pitfall: overriding with a class instead of an instance

```python
# Wrong - passes the class object itself
overrides={Database: FakeDatabase}

# Correct - passes an instance
overrides={Database: FakeDatabase()}
```

### Common pitfall: overriding the concrete type instead of the interface

```python
# If consumers depend on the Protocol:
class UserService:
    def __init__(self, db: Database): ...  # Database is a Protocol

# Override by the Protocol, not the concrete class:
overrides={Database: FakeDatabase()}       # correct
overrides={PostgresDatabase: FakeDatabase()}  # won't affect UserService
```

### Common pitfall: shared state between tests

Singletons persist across the container's lifetime. Create a fresh container
per test:

```python
@pytest.fixture
def container():
    c = init(modules=["myapp"], overrides={Database: FakeDatabase()})
    yield c
    c.shutdown()
```

---

## Debugging tips

### Enable debug logging

```python
import logging
logging.getLogger("pico_ioc").setLevel(logging.DEBUG)
```

### Inspect registered components

```python
container = init(modules=["myapp"])
stats = container.stats()
print(f"Registered: {stats['registered_components']}")
```

### Export the dependency graph

```python
container.export_graph("dependencies.dot")
# dot -Tpng dependencies.dot -o dependencies.png
```

---

## See also

- [Error Reference](./faq.md#troubleshooting----error-reference) -- every error message with cause and fix
- [Unified pico-boot troubleshooting guide](https://github.com/dperezcabrera/pico-boot/blob/main/docs/troubleshooting.md) -- covers pico-boot, pico-fastapi, and pico-pydantic
- [FAQ](./faq.md) -- common questions
- [Testing guide](./how-to/testing.md) -- testing patterns
