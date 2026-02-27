# Advanced: AOP & Interceptors 🎭

Aspect-Oriented Programming (AOP) is a powerful technique for separating cross-cutting concerns (like logging, tracing, caching, or security checks) from your core business logic.

Problem: Your business methods often get cluttered with repetitive technical code that isn't their primary responsibility.

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
            db.save(user)  # Simulate saving
            
            # ⚠️ Technical Concern: Logging Exit
            log.info(f"Exiting create_user, returning user ID: {user.id}")
            return user
```

The core job of create_user is just creating the user. The logging and tracing are important, but they obscure the business logic and need to be repeated in many other methods.

Solution: pico_ioc allows you to extract these technical concerns into reusable MethodInterceptor components. You then apply them declaratively to your business methods using the @intercepted_by decorator. Your business methods become clean and focused again. ✨

-----

## 1. Core Concepts

### MethodInterceptor Protocol

This is the interface your interceptor classes must implement. It defines a single invoke method that wraps the original method call.

```python
# Defined in pico_ioc.aop
from typing import Any, Callable, Dict, Protocol

class MethodCtx:
    """Context object passed to the interceptor's invoke method."""
    instance: object        # The component instance being called (e.g., UserService)
    cls: type               # The class of the instance (e.g., UserService)
    method: Callable        # The original bound method (e.g., UserService.create_user)
    name: str               # The method name (e.g., "create_user")
    args: tuple             # Positional arguments passed (e.g., ())
    kwargs: dict            # Keyword arguments passed (e.g., {'username': 'alice'})
    container: Any          # The container instance (pico_ioc container)
    local: Dict[str, Any]   # Scratchpad for interceptors in the same chain
    request_key: Any | None # Current request scope ID, if active

class MethodInterceptor(Protocol):
    def invoke(
        self,
        ctx: MethodCtx,
        call_next: Callable[[MethodCtx], Any]  # Calls the next interceptor or original method
    ) -> Any:
        """
        Implement this method to add behavior around the original call.
        You may call 'call_next(ctx)' to proceed to the next element in the chain.
        If you return without calling 'call_next', you short-circuit the call (e.g., cache hit).
        """
        ...
```

Key Points:

- Interceptors must be registered components (annotated with @component) so pico_ioc can create them and inject their own dependencies if needed.
- You can short-circuit by returning without calling call_next (typical in caching or authorization failures). Otherwise, call_next(ctx) continues the chain and eventually calls the original method.
- ctx.local is a per-invocation dictionary shared by all interceptors in the chain; use it for passing state between interceptors.
- Interceptors should be stateless or thread-safe; use ctx.local for per-call state.

### @intercepted_by Decorator

This decorator is applied directly to the methods you want to intercept. You pass it the class types of the interceptor components you want to apply.

```python
from pico_ioc import component, intercepted_by
from pico_ioc.aop import MethodInterceptor, MethodCtx

# Assume LoggingInterceptor and TracingInterceptor are components
# defined elsewhere and implement MethodInterceptor

@component
class MyService:
    
    @intercepted_by(LoggingInterceptor, TracingInterceptor)
    def important_method(self, data: str):
        print("Executing core business logic...")
        return f"Processed: {data}"
```

pico_ioc resolves LoggingInterceptor and TracingInterceptor from the container and builds an execution chain around important_method.

Notes:

- Pass interceptor classes, not instances. The container creates and injects them.
- Apply @intercepted_by to concrete methods (sync or async). Do not apply to __init__ or properties.

-----

## 2. Step-by-Step Example: Refactoring with a Logging Interceptor

Let's clean up our initial UserService example.

### Step 1: Define the LoggingInterceptor Component

Create a class that implements the MethodInterceptor protocol and register it as a @component.

```python
# app/interceptors.py
import logging
import time
from typing import Any, Callable
from pico_ioc import component
from pico_ioc.aop import MethodCtx, MethodInterceptor

log = logging.getLogger(__name__)

@component  # <-- Interceptors must be components!
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
        
        start_time = time.perf_counter()
        try:
            # 2. Call the next interceptor or the original method
            result = call_next(ctx)
            duration_ms = (time.perf_counter() - start_time) * 1000
            
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
            raise  # Re-raise the exception
```

### Step 2: Apply the Interceptor to the Service

Decorate the create_user method in UserService with @intercepted_by. The business logic becomes much cleaner.

```python
# app/services.py
from pico_ioc import component, intercepted_by
from .interceptors import LoggingInterceptor  # Import the interceptor

# Assume User and db are defined elsewhere

@component
class UserService:
    # Assume db and tracer are injected via __init__

    @intercepted_by(LoggingInterceptor)  # <-- Apply the interceptor
    def create_user(self, username: str):
        # ✅ This is PURE business logic now!
        print(f"Creating user {username}...")
        user = User(name=username)
        db.save(user)  # Simulate saving
        return user
```

### Step 3: Run It

When you initialize the container, make sure to scan the modules containing both the service and the interceptor.

```python
# main.py
from pico_ioc import init
from app.services import UserService

# Scan modules containing components AND interceptors
container = init(modules=["app"])

service = container.get(UserService)

# Calling this method now automatically triggers the interceptor
user = service.create_user(username="alice")
```

Log Output:

```
INFO: ==> Entering UserService.create_user Args: (), Kwargs: {'username': 'alice'}
Creating user alice...
INFO: <== Exiting UserService.create_user Result: <User object ...> (Duration: 5.12ms)
```

The logging concern is now cleanly separated and reusable across any method you decorate.

-----

## 3. Chaining Multiple Interceptors

You can apply multiple interceptors to a single method. They execute in the order listed in the decorator, forming a chain (like layers of an onion).

```python
@intercepted_by(TracingInterceptor, LoggingInterceptor, CachingInterceptor)
def process_data(self, data_id: int):
    ...
```

Execution Order:

1) TracingInterceptor (code before call_next)
2) LoggingInterceptor (code before call_next)
3) CachingInterceptor (code before call_next — may return cached value and short-circuit)
4) process_data (original method — only runs if not short-circuited)
5) CachingInterceptor (code after call_next — may cache result)
6) LoggingInterceptor (code after call_next)
7) TracingInterceptor (code after call_next)

Tip: If you need to share state between interceptors, use ctx.local as a per-call scratchpad.

Short-circuit example (caching):

```python
@component
class CachingInterceptor(MethodInterceptor):
    def __init__(self, cache):
        self.cache = cache

    def invoke(self, ctx: MethodCtx, call_next):
        key = (ctx.cls.__name__, ctx.name, ctx.args, frozenset(ctx.kwargs.items()))
        cached = self.cache.get(key)
        if cached is not None:
            return cached  # Short-circuit
        
        result = call_next(ctx)  # Proceed
        self.cache.set(key, result)
        return result
```

-----

## 4. Async Interceptors

The AOP system is fully async-aware.

- If you apply interceptors to an async def method, pico_ioc correctly awaits the call chain.
- Your MethodInterceptor.invoke method itself can be async def. In that case, await call_next(ctx).

```python
import asyncio
import logging
from typing import Callable, Any
from pico_ioc import component, intercepted_by
from pico_ioc.aop import MethodInterceptor, MethodCtx

log = logging.getLogger(__name__)

@component
class AsyncTimerInterceptor(MethodInterceptor):
    async def invoke(self, ctx: MethodCtx, call_next: Callable[[MethodCtx], Any]):
        start = asyncio.get_running_loop().time()
        log.info(f"==> Entering async method {ctx.name}...")
        
        # Correctly awaits the next async interceptor or original method
        result = await call_next(ctx)
        
        duration_ms = (asyncio.get_running_loop().time() - start) * 1000
        log.info(f"<== Exiting async method {ctx.name} (Duration: {duration_ms:.2f}ms)")
        return result

@component
class MyAsyncService:
    @intercepted_by(AsyncTimerInterceptor)
    async def fetch_remote_data(self):
        await asyncio.sleep(0.5)  # Simulate I/O
        return {"data": 123}
```

Mixing sync and async interceptors:

- If the target method is async, write your interceptor invoke as async and await call_next(ctx).
- If the target method is sync, write your interceptor invoke as a regular def and call call_next(ctx) normally.
- The framework composes the chain correctly across sync/async boundaries.

-----

## 5. Context (MethodCtx) Tips

- ctx.instance, ctx.cls, ctx.method, ctx.name: Identify what is being called.
- ctx.args, ctx.kwargs: Inspect or modify arguments. If you need to change them, update ctx.args/ctx.kwargs before calling call_next(ctx).
- ctx.local: Use this dict to share per-call data across interceptors (e.g., correlation IDs, timers).
- ctx.container: Access the container to resolve additional components if necessary.
- ctx.request_key: Available when using request-scoped components; useful for correlating logs or traces.

Example sharing state:

```python
@component
class CorrelationIdInterceptor(MethodInterceptor):
    def invoke(self, ctx: MethodCtx, call_next):
        cid = ctx.kwargs.get("correlation_id") or "gen-1234"
        ctx.local["cid"] = cid
        return call_next(ctx)

@component
class UsesCorrelationInterceptor(MethodInterceptor):
    def invoke(self, ctx: MethodCtx, call_next):
        cid = ctx.local.get("cid")
        if cid:
            print(f"[CID={cid}] {ctx.cls.__name__}.{ctx.name} starting")
        return call_next(ctx)
```

Apply them together:

```python
@intercepted_by(CorrelationIdInterceptor, UsesCorrelationInterceptor)
def do_work(self, *, correlation_id: str | None = None):
    ...
```

-----

## 6. Troubleshooting

- My interceptor never runs:
  - Ensure the interceptor class is annotated with @component.
  - Ensure the module containing the interceptor is scanned during init(...).
  - Ensure @intercepted_by is applied to the method you are calling (not to an overridden method that isn’t used).

- I get errors with async methods:
  - Make the interceptor invoke async def and await call_next(ctx) if the target method is async.
  - Do not block the event loop inside async interceptors; use async APIs.

- I want to skip the original method:
  - Simply return from invoke without calling call_next(ctx) (e.g., for cache hits or authorization failures).

- Order seems wrong:
  - Interceptors execute in the order listed in @intercepted_by. Verify the decorator argument order.

-----

## Next Steps

AOP using interceptors is a powerful way to add technical behavior without cluttering your business logic. Another key pattern for decoupling is using events.

- The Event Bus: Learn how to use the built-in async event bus for a publish/subscribe architecture, further decoupling your components. See ./event-bus.md
