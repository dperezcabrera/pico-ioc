# Advanced: AOP & Interceptors 🎭

Aspect-Oriented Programming (AOP) is a powerful technique for separating **cross-cutting concerns** (like logging, tracing, caching, or security checks) from your core **business logic**.

**Problem:** Your business methods often get cluttered with repetitive technical code that isn't their primary responsibility.

```python
import logging
from pico_ioc import component

log = logging.getLogger(__name__)

@component
class UserService:
    # Assume db and tracer are injected
    
    def create_user(self, username: str):
        # ⚠️ Technical Concern: Logging Entry
        log.info(f"Entering create_user with username: {username}")
        
        # ⚠️ Technical Concern: Performance Tracing
        with tracer.start_span("create_user") as span:
            span.set_attribute("username", username)
            
            # ✅ Business Logic: The actual work
            print(f"Creating user {username}...")
            user = User(name=username)
            db.save(user) # Simulate saving
            
            # ⚠️ Technical Concern: Logging Exit
            log.info(f"Exiting create_user, returning user ID: {user.id}")
            return user
````

The core job of `create_user` is just creating the user. The logging and tracing are important, but they obscure the business logic and need to be repeated in many other methods.

**Solution:** `pico_ioc` allows you to extract these technical concerns into reusable **`MethodInterceptor`** components. You then apply them declaratively to your business methods using the **`@intercepted_by`** decorator. Your business methods become clean and focused again. ✨

-----

## 1\. Core Concepts

### `MethodInterceptor` Protocol

This is the interface your interceptor classes must implement. It defines a single `invoke` method that wraps the original method call.

```python
# Defined in pico_ioc.aop
from typing import Any, Callable, Protocol

class MethodCtx:
    """Context object passed to the interceptor's invoke method."""
    instance: object       # The component instance being called (e.g., UserService)
    cls: type              # The class of the instance (e.g., UserService)
    method: Callable       # The original bound method (e.g., UserService.create_user)
    name: str              # The method name (e.g., "create_user")
    args: tuple            # Positional arguments passed (e.g., ())
    kwargs: dict           # Keyword arguments passed (e.g., {'username': 'alice'})
    container: PicoContainer # The container instance
    local: Dict[str, Any]  # Scratchpad for interceptors in the same chain
    request_key: Any | None # Current request scope ID, if active

class MethodInterceptor(Protocol):
    def invoke(
        self,
        ctx: MethodCtx, 
        call_next: Callable[[MethodCtx], Any] # Function to call the next interceptor/method
    ) -> Any:
        """
        Implement this method to add behavior around the original call.
        You MUST call 'call_next(ctx)' to proceed.
        """
        # Code here runs BEFORE the original method
        ...
        result = call_next(ctx) # Calls the next interceptor or original method
        ...
        # Code here runs AFTER the original method
        return result # You can modify the result if needed
```

**Key Points:**

  * Interceptors themselves **must be registered components** (usually with `@component`) so `pico-ioc` can create them and inject their own dependencies if needed.
  * You **must** call `call_next(ctx)` within your `invoke` method, otherwise the original method (and any subsequent interceptors) will never run.

### `@intercepted_by` Decorator

This decorator is applied directly to the methods you want to intercept. You pass it the *class types* of the interceptor components you want to apply.

```python
from pico_ioc import component, intercepted_by

# Assume LoggingInterceptor and TracingInterceptor are components
# defined elsewhere and implement MethodInterceptor

@component
class MyService:
    
    @intercepted_by(LoggingInterceptor, TracingInterceptor)
    def important_method(self, data: str):
        print("Executing core business logic...")
        return f"Processed: {data}"
```

`pico-ioc` will resolve `LoggingInterceptor` and `TracingInterceptor` from the container and build an execution chain around `important_method`.

-----

## 2\. Step-by-Step Example: Refactoring with a Logging Interceptor

Let's clean up our initial `UserService` example.

### Step 1: Define the `LoggingInterceptor` Component

We create a class that implements the `MethodInterceptor` protocol and register it as a `@component`.

```python
# app/interceptors.py
import logging
from typing import Any, Callable
from pico_ioc import component, MethodCtx, MethodInterceptor

log = logging.getLogger(__name__)

@component # <-- Interceptors must be components!
class LoggingInterceptor(MethodInterceptor):
    def invoke(
        self,
        ctx: MethodCtx, 
        call_next: Callable[[MethodCtx], Any]
    ) -> Any:
        
        # 1. Logic BEFORE the original method
        log.info(
            f"==> Entering {ctx.cls.__name__}.{ctx.name} "
            f"Args: {ctx.args}, Kwargs: {ctx.kwargs}"
        )
        
        try:
            # 2. Call the next interceptor or the original method
            start_time = time.monotonic()
            result = call_next(ctx)
            duration_ms = (time.monotonic() - start_time) * 1000
            
            # 3. Logic AFTER the original method (on success)
            log.info(
                f"<== Exiting {ctx.cls.__name__}.{ctx.name} "
                f"Result: {result} (Duration: {duration_ms:.2f}ms)"
            )
            return result
            
        except Exception as e:
            # 4. Logic AFTER the original method (on failure)
            log.exception(
                f"[!] Exception in {ctx.cls.__name__}.{ctx.name}: {e}"
            )
            raise # Re-raise the exception
```

### Step 2: Apply the Interceptor to the Service

Now, we decorate the `create_user` method in `UserService` with `@intercepted_by`. The business logic becomes much cleaner.

```python
# app/services.py
from pico_ioc import component, intercepted_by
from .interceptors import LoggingInterceptor # Import the interceptor

# Assume User and db are defined elsewhere

@component
class UserService:
    # Assume db and tracer are injected via __init__

    @intercepted_by(LoggingInterceptor) # <-- Apply the interceptor
    def create_user(self, username: str):
        # ✅ This is PURE business logic now!
        print(f"Creating user {username}...")
        user = User(name=username)
        db.save(user) # Simulate saving
        return user
```

### Step 3: Run It

When you initialize the container, make sure to scan the modules containing both the service and the interceptor.

```python
# main.py
from pico_ioc import init
from app.services import UserService

# Scan modules containing components AND interceptors
container = init(modules=["app.interceptors", "app.services"])

service = container.get(UserService)

# Calling this method now automatically triggers the interceptor
user = service.create_user(username="alice") 
```

**Log Output:**

```
INFO: ==> Entering UserService.create_user Args: (), Kwargs: {'username': 'alice'}
Creating user alice...
INFO: <== Exiting UserService.create_user Result: <User object ...> (Duration: 5.12ms)
```

The logging concern is now cleanly separated and reusable across any method you decorate.

-----

## 3\. Chaining Multiple Interceptors

You can apply multiple interceptors to a single method. They execute in the order listed in the decorator, forming a chain (like layers of an onion).

```python
@intercepted_by(TracingInterceptor, LoggingInterceptor, CachingInterceptor)
def process_data(self, data_id: int):
    ...
```

**Execution Order:**

1.  `TracingInterceptor` (Code Before `call_next`)
2.  `LoggingInterceptor` (Code Before `call_next`)
3.  `CachingInterceptor` (Code Before `call_next` - maybe returns cached value here)
4.  **`process_data`** (Original Method - might be skipped by cache)
5.  `CachingInterceptor` (Code After `call_next` - maybe caches result)
6.  `LoggingInterceptor` (Code After `call_next`)
7.  `TracingInterceptor` (Code After `call_next`)

-----

## 4\. Async Interceptors

The AOP system is **fully async-aware**.

  * If you apply interceptors to an `async def` method, `pico-ioc` correctly handles `await`ing the `call_next(ctx)` function.
  * Your `MethodInterceptor.invoke` method itself can be `async def`.

<!-- end list -->

```python
import asyncio
from pico_ioc import component, intercepted_by, MethodInterceptor, MethodCtx

@component
class AsyncTimerInterceptor(MethodInterceptor):
    
    async def invoke(self, ctx: MethodCtx, call_next: Callable): # Can be async def
        start_time = asyncio.get_event_loop().time()
        log.info(f"==> Entering async method {ctx.name}...")
        
        # Correctly awaits the next async interceptor or original method
        result = await call_next(ctx) 
        
        duration = asyncio.get_event_loop().time() - start_time
        log.info(f"<== Exiting async method {ctx.name} (Duration: {duration*1000:.2f}ms)")
        return result

@component
class MyAsyncService:
    @intercepted_by(AsyncTimerInterceptor)
    async def fetch_remote_data(self):
        await asyncio.sleep(0.5) # Simulate I/O
        return {"data": 123}
```

-----

## Next Steps

AOP using interceptors is a powerful way to add technical behavior without cluttering your business logic. Another key pattern for decoupling is using events.

  * **[The Event Bus](./event-bus.md)**: Learn how to use the built-in async event bus for a publish/subscribe architecture, further decoupling your components.

