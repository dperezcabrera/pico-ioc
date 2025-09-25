# Advanced: Async Resolution (`aget`, `__ainit__`)

Modern Python applications are increasingly built on `asyncio`. `pico-ioc` is **async-native**, meaning it fully supports asynchronous operations throughout the component lifecycle, from creation to cleanup.

This guide covers how to:
* Resolve components asynchronously using `container.aget()`.
* Define components that require `await` during their creation.
* Use asynchronous lifecycle hooks like `@cleanup`.

---

## 1. `container.aget()`: The Async `get()`

If you are in an `async` function, you should **always** use `container.aget()` instead of `container.get()`.

* `container.get()`: **Synchronous**. Blocks the event loop if a component needs to be created.
* `container.aget()`: **Asynchronous**. Properly `await`s the creation of any async components, ensuring the event loop is never blocked.

```python
@component
class MyAsyncService:
    ...

async def main():
    container = init(...)
    
    # Use .aget() inside an async function
    service = await container.aget(MyAsyncService)
    
    # This would be bad! It could block.
    # service = container.get(MyAsyncService) 
````

-----

## 2\. Asynchronous Component Creation

Your components often need to perform I/O during their initialization (e.g., connect to a database, call an API). `pico-ioc` supports this in two primary ways.

### Method 1: Async Factory (`async def @provides`)

The cleanest way to create an async component is with a factory. You can decorate an `async def` method with `@provides`. `pico-ioc` will automatically `await` it when it's resolved via `container.aget()`.

```python
import asyncio
from pico_ioc import factory, provides, init

# A mock async database client
class AsyncDatabase:
    def __init__(self):
        self.connected = True
        print("Database connected")

    @staticmethod
    async def connect(url: str):
        print(f"Connecting to {url}...")
        await asyncio.sleep(0.01) # Mock I/O
        return AsyncDatabase()

@factory
class DatabaseFactory:
    
    # Use 'async def' with @provides
    @provides(AsyncDatabase)
    async def build_db(self) -> AsyncDatabase:
        db = await AsyncDatabase.connect("postgres://...")
        return db

@component
class UserService:
    def __init__(self, db: AsyncDatabase):
        self.db = db

# --- In your main async function ---
async def main():
    container = init(modules=[__name__])
    
    # .aget() will correctly await the build_db() factory
    user_service = await container.aget(UserService)
    
    assert user_service.db.connected is True

# Output:
# Connecting to postgres://...
# Database connected
```

### Method 2: Async Constructor (`__ainit__`)

You cannot make `__init__` an `async def` method in Python.

To solve this, `pico-ioc` supports a special method: **`__ainit__`**.

If you define an `async def __ainit__` method on a `@component` class, `pico-ioc` will automatically call and `await` it immediately after `__init__` is finished.

```python
import asyncio
from pico_ioc import component, init

@component
class AsyncService:
    def __init__(self):
        # __init__ remains synchronous
        self.connected = False
        print("Service __init__ (sync)")

    async def __ainit__(self):
        # This is where you put your async setup code
        print("Service __ainit__ (async) starting...")
        await asyncio.sleep(0.01) # Mock I/O
        self.connected = True
        print("Service __ainit__ finished.")

# --- In your main async function ---
async def main():
    container = init(modules=[__name__])
    
    # .aget() will call __init__() and then await __ainit__()
    service = await container.aget(AsyncService)
    
    assert service.connected is True

# Output:
# Service __init__ (sync)
# Service __ainit__ (async) starting...
# Service __ainit__ finished.
```

**`__ainit__`** can also have its own dependencies injected, just like `@configure`:

```python
    async def __ainit__(self, db: AsyncDatabase):
        await db.ping()
        self.connected = True
```

-----

## 3\. Asynchronous Lifecycle Hooks

The `@configure` and `@cleanup` decorators also work with `async def` methods.

  * `async def @configure`: Called and awaited after `__ainit__`.
  * `async def @cleanup`: Called and awaited by `container.cleanup_all_async()`.

This is essential for gracefully shutting down async resources.

```python
@component
class AsyncConnectionPool:
    async def __ainit__(self):
        self.pool = await self.create_pool()
        print("Pool created")

    @cleanup
    async def close_pool(self):
        # Use async def with @cleanup
        print("Closing pool (async)...")
        await self.pool.close()
        print("Pool closed.")
        
    async def create_pool(self): ... # mock

# --- In your main async function ---
async def main():
    container = init(modules=[__name__])
    pool = await container.aget(AsyncConnectionPool)
    
    print("Application shutting down...")
    
    # You MUST call the async version of cleanup
    await container.cleanup_all_async()

# Output:
# Pool created
# Application shutting down...
# Closing pool (async)...
# Pool closed.
```

-----

## Summary

  * Always use `container.aget()` from within an `async` function.
  * Use `async def @provides` in a factory for async creation logic.
  * Use `async def __ainit__` on a `@component` for async initialization logic.
  * Use `async def @cleanup` and `container.cleanup_all_async()` to gracefully release async resources.

-----

## Next Steps

Now that you understand how to build and resolve components asynchronously, let's look at a powerful pattern for separating your application's concerns.

  * **[AOP & Interceptors](./aop-interceptors.md)**: Learn how to intercept method calls for logging, tracing, or caching.

