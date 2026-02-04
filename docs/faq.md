# Frequently Asked Questions (FAQ)

Common questions and solutions for pico-ioc.

---

## Installation & Setup

### Q: What Python versions are supported?

**A:** Python 3.10 or newer. We use modern type hints that require 3.10+.

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

## Common Errors

### `ProviderNotFoundError: No provider found for X`

**Causes:**
- Missing `@component` decorator
- Module not included in `init(modules=[...])`
- Typo in type hint

### `CircularDependencyError: Circular dependency detected`

**Cause:** A depends on B, and B depends on A.

**Solution:** Use `lazy=True` on one of the components:
```python
@component(lazy=True)
class ServiceA:
    def __init__(self, b: "ServiceB"):
        self.b = b
```

### `AsyncResolutionError: Cannot resolve async component synchronously`

**Cause:** Calling `get()` on a component with `__ainit__` or async `@configure`.

**Solution:** Use `await container.aget(...)` instead.

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
