# Frequently Asked Questions (FAQ)

Common questions and solutions for pico-ioc.

---

## Installation & Setup

### Q: What Python versions are supported?

**A:** Python 3.11 or newer. We use modern type hints that require 3.11+.

### Q: How do I enable YAML configuration support?

```bash
pip install pico-ioc[yaml]
```

---

## Components & Registration

### Q: Why is my component not being found?

**A:** Check these common issues:

1. **Missing `@component` decorator**
   ```python
   # Wrong - no decorator
   class MyService:
       pass

   # Correct
   @component
   class MyService:
       pass
   ```

2. **Module not included in `init()`**
   ```python
   # Make sure the module is scanned
   container = init(modules=["myapp.services", "myapp.repos"])
   ```

3. **Circular import** - Use string type hints:
   ```python
   # Instead of: from myapp.other import OtherService
   @component
   class MyService:
       def __init__(self, other: "OtherService"):  # String hint
           self.other = other
   ```

### Q: How do I register a third-party class I can't decorate?

**A:** Use `@provides`:

```python
import redis
from pico_ioc import provides

@provides(redis.Redis)
def build_redis() -> redis.Redis:
    return redis.Redis.from_url("redis://localhost")
```

### Q: Can I have multiple implementations of the same type?

**A:** Yes, use qualifiers:

```python
from pico_ioc import component, Qualifier
from typing import Annotated

@component(qualifiers={"fast"})
class FastCache:
    pass

@component(qualifiers={"persistent"})
class PersistentCache:
    pass

@component
class MyService:
    def __init__(self, cache: Annotated[FastCache, Qualifier("fast")]):
        self.cache = cache
```

---

## Configuration

### Q: How do I read configuration from environment variables?

```python
import os
from dataclasses import dataclass
from pico_ioc import configured, configuration, init

@configured(prefix="DB_")
@dataclass
class DBConfig:
    host: str = "localhost"
    port: int = 5432

# Set env vars: DB_HOST=myhost, DB_PORT=5433
container = init(modules=[__name__], config=configuration())
```

### Q: How do I load configuration from YAML?

```python
from pico_ioc import configuration, YamlSource

config = configuration(
    YamlSource("config.yaml"),
    YamlSource("config.local.yaml", required=False)  # Optional override
)
container = init(modules=[__name__], config=config)
```

### Q: What's the precedence order for configuration sources?

Later sources override earlier ones:
1. Default values in dataclass
2. YAML/JSON files (in order specified)
3. Environment variables (highest priority)

---

## Async

### Q: How do I create async components?

**A:** Use `__ainit__` and resolve with `aget()`:

```python
@component
class AsyncService:
    async def __ainit__(self):
        self.conn = await create_connection()

# Must use aget() for async components
service = await container.aget(AsyncService)
```

### Q: I get `AsyncResolutionError` - what's wrong?

**A:** You're calling `container.get()` on a component that has async initialization. Solutions:

1. **Use `aget()` instead:**
   ```python
   service = await container.aget(AsyncService)
   ```

2. **Or mark the component as `lazy=True`:**
   ```python
   @component(lazy=True)
   class AsyncService:
       async def __ainit__(self):
           ...
   ```

### Q: How do I properly shutdown async resources?

```python
# Use ashutdown() for async cleanup
await container.ashutdown()

# This will call all @cleanup decorated methods
@component
class AsyncService:
    @cleanup
    async def close(self):
        await self.conn.close()
```

---

## Scopes & Lifecycle

### Q: What scopes are available?

| Scope | Description |
|-------|-------------|
| `singleton` (default) | One instance for the container lifetime |
| `prototype` | New instance every `get()` call |
| `request` | One instance per request scope |
| `session` | One instance per session scope |
| `transaction` | One instance per transaction scope |

### Q: How do I use request scope (e.g., with FastAPI)?

```python
@component(scope="request")
class RequestContext:
    pass

# Activate the scope
with container.scope("request", request_id):
    ctx = container.get(RequestContext)
```

With `pico-fastapi`, this is handled automatically.

### Q: How do I clean up resources when the container shuts down?

```python
@component
class DatabasePool:
    @cleanup
    def close(self):
        self.pool.close()

# When you call shutdown(), all @cleanup methods are invoked
container.shutdown()
```

---

## Testing

### Q: How do I replace components for testing?

**A:** Use `overrides`:

```python
class FakeDatabase:
    def query(self):
        return "fake data"

container = init(
    modules=["myapp"],
    overrides={Database: FakeDatabase()}
)
```

### Q: How do I test with different configurations?

```python
from pico_ioc import configuration, DictSource

test_config = configuration(
    DictSource({"DB_HOST": "testdb", "DB_PORT": "5432"})
)

container = init(modules=["myapp"], config=test_config)
```

### Q: How do I validate my wiring without running the app?

```python
try:
    container = init(modules=["myapp"])
    # All wiring is validated at init() time
except ProviderNotFoundError as e:
    print(f"Missing dependency: {e}")
```

---

## Debugging

### Q: How do I see what components are registered?

```python
container = init(modules=["myapp"])
stats = container.stats()
print(f"Registered components: {stats['registered_components']}")
```

### Q: How do I visualize the dependency graph?

```python
container.export_graph("dependencies.dot")

# Then convert to PNG:
# dot -Tpng dependencies.dot -o dependencies.png
```

### Q: How do I enable debug logging?

```python
import logging
logging.getLogger("pico_ioc").setLevel(logging.DEBUG)
```

---

## Troubleshooting -- Error Reference

This section lists every error message produced by pico-ioc, what causes it,
and how to fix it.

---

### `ProviderNotFoundError`

**Message:** `Provider for key 'X' not found (required by: 'Y')`

**Causes:**

- Missing `@component` decorator on the class.
- Module not included in `init(modules=[...])`.
- Typo in the type hint (e.g. `Databse` instead of `Database`).
- The class is conditionally excluded (wrong profile, missing env var).

**Fix:**

1. Add `@component` to the class.
2. Include the module in `init(modules=[...])`.
3. Check the type hint matches the registered class exactly.
4. Verify profiles and environment variables.

---

### `InvalidBindingError` (Circular Dependency)

**Message:** `Invalid bindings:\n- Circular dependency detected: A -> B -> A`

**Cause:** Component A depends on B, and B depends on A (directly or transitively).

**Fix:** Break the cycle by marking one side as `lazy=True`:

```python
@component(lazy=True)
class ServiceA:
    def __init__(self, b: "ServiceB"):
        self.b = b
```

---

### `InvalidBindingError` (Missing Binding)

**Message:** `Invalid bindings:\n- MyService (component MyService) depends on Database which is not bound`

**Cause:** A dependency declared in a constructor type hint has no registered provider.

**Fix:**

1. Register the dependency with `@component`, `@provides`, or `overrides`.
2. If the dependency is optional, annotate it as `Optional[Database]` or provide a default value.

---

### `AsyncResolutionError`

**Message:** `Synchronous get() received an awaitable for key 'X'. Use aget() instead.`

**Cause:** Calling `container.get()` on a component whose provider, `__ainit__`,
or `@configure` method returns a coroutine.

**Fix:** Use `await container.aget(X)` instead, or mark the component as
`lazy=True` and access it in an async context.

---

### `ComponentCreationError`

**Message:** `Failed to create component for key: X; cause: ErrorType: details`

**Cause:** The provider callable raised an exception during component creation.

**Fix:** Read the `cause` in the message. Common issues:

- Missing constructor argument (dependency not bound).
- Exception in `__init__` or `__ainit__`.
- Database connection failure in a factory `@provides` method.

---

### `ConfigurationError` (Unknown Profiles)

**Message:** `Unknown profiles: ['staging']; allowed: ['dev', 'prod', 'test']`

**Cause:** A profile name was passed to `init(profiles=(...))` that is not in
`allowed_profiles`.

**Fix:** Either add the profile to `allowed_profiles`, or fix the typo.

---

### `ConfigurationError` (Missing Config Key)

**Message:** `Missing configuration key: DB_HOST`

**Cause:** A `@configured(mapping="flat")` dataclass has a required field with
no default, and no configuration source provides a value for that key.

**Fix:** Either provide the key in your configuration source (env var, dict, etc.)
or add a default value to the dataclass field.

---

### `ConfigurationError` (Missing Config Prefix)

**Message:** `Missing config prefix: db.connection`

**Cause:** A `@configured(prefix="db.connection", mapping="tree")` class expects
a subtree in the configuration, but no source provides it.

**Fix:** Add the subtree to your `DictSource`, `JsonTreeSource`, or `YamlTreeSource`.

---

### `ConfigurationError` (Unknown Source Type)

**Message:** `Unknown configuration source type: <class 'MySource'>`

**Cause:** An unrecognised object was passed to `configuration(...)`.

**Fix:** Use one of the supported source types: `EnvSource`, `FileSource`,
`FlatDictSource`, `DictSource`, `JsonTreeSource`, `YamlTreeSource`.

---

### `ConfigurationError` (Missing ENV Var)

**Message:** `Missing ENV var MY_SECRET`

**Cause:** A `${ENV:MY_SECRET}` interpolation in a tree config references an
environment variable that is not set.

**Fix:** Set the environment variable, or remove the interpolation.

---

### `ConfigurationError` (Async Singletons)

**Message:** `Sync init() found eagerly loaded singletons with async @configure methods. ...`

**Cause:** A non-lazy singleton has an async `@configure` method, but `init()`
is called synchronously.

**Fix:** Either mark the component `lazy=True`, or use `await container.aget(X)`
in an async context.

---

### `ScopeError` (Unknown Scope)

**Message:** `Unknown scope: tenant`

**Cause:** A component uses `scope="tenant"`, but the scope was not registered.

**Fix:** Pass `custom_scopes=["tenant"]` to `init()`.

---

### `ScopeError` (No Active Scope ID)

**Message:** `Cannot resolve component in scope 'request': No active scope ID found. Are you trying to use a request-scoped component outside of its context?`

**Cause:** You called `container.get(RequestScopedComponent)` outside of a
`container.scope("request", id)` block.

**Fix:** Wrap the resolution in the appropriate scope context:

```python
with container.scope("request", request_id):
    component = container.get(RequestScopedComponent)
```

---

### `ScopeError` (Reserved Scope)

**Message:** `Cannot register reserved scope: 'singleton'`

**Cause:** Attempting to register `"singleton"` or `"prototype"` as a custom scope.

**Fix:** Choose a different scope name. `singleton` and `prototype` are built-in.

---

### `EventBusClosedError`

**Message:** `EventBus is closed`

**Cause:** Calling `publish()`, `subscribe()`, or `post()` after the EventBus
has been closed via `await bus.aclose()`.

**Fix:** Do not interact with the bus after shutdown.

---

### `RuntimeError` (DeferredProvider)

**Message:** `DeferredProvider must be attached before use`

**Cause:** Internal error -- a provider was called before the container and
locator were wired. This usually indicates a bug in custom scanner logic.

**Fix:** Ensure `DeferredProvider.attach(pico, locator)` is called before
the provider is invoked.

---

### `RuntimeError` (Async Interceptor on Sync Method)

**Message:** `Async interceptor returned awaitable on sync method: method_name`

**Cause:** An interceptor returned a coroutine from `invoke()`, but the
intercepted method is synchronous.

**Fix:** Ensure sync methods only use sync interceptors, or handle the
async/sync distinction inside your interceptor.

---

### `ValueError` (Invalid Mapping)

**Message:** `mapping must be one of 'auto', 'flat', or 'tree'`

**Cause:** Invalid `mapping` argument passed to `@configured(mapping="xyz")`.

**Fix:** Use `"auto"`, `"flat"`, or `"tree"`.

---

## Common Errors (Quick Reference)

| Error | Typical Cause | Fix |
|-------|--------------|-----|
| `ProviderNotFoundError` | Missing decorator or module | Add `@component` and include module |
| `InvalidBindingError` | Circular or missing deps | Use `lazy=True` or register missing provider |
| `AsyncResolutionError` | Sync `get()` on async component | Use `await aget()` |
| `ComponentCreationError` | Exception in provider | Fix the root cause in the error message |
| `ConfigurationError` | Missing key, bad source, async singleton | Provide the key or mark `lazy=True` |
| `ScopeError` | Unknown scope or missing context | Register scope or use `container.scope()` |
| `EventBusClosedError` | Using bus after shutdown | Stop using the bus after `aclose()` |

---

## Migration

### Q: How do I migrate from dependency-injector?

| dependency-injector | pico-ioc |
|---------------------|----------|
| `@inject` | Type hints in `__init__` |
| `Container.provider()` | `@component` or `@provides` |
| `Singleton()` | `@component(scope="singleton")` |
| `Factory()` | `@component(scope="prototype")` |

### Q: How do I migrate from FastAPI's Depends?

```python
# FastAPI Depends style
def get_db():
    return Database()

@app.get("/")
def route(db: Database = Depends(get_db)):
    ...

# pico-ioc style (with pico-fastapi)
@component
class Database:
    pass

@app.get("/")
def route(db: Database):  # Injected automatically
    ...
```

---

## Still stuck?

- Check the [User Guide](./user-guide/README.md) for detailed explanations
- See [Cookbook](./cookbook/README.md) for real-world patterns
- Open an issue on [GitHub](https://github.com/dperezcabrera/pico-ioc/issues)
