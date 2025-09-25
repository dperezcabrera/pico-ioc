# Cookbook: Pattern: Structured Logging with AOP 🪵

**Goal:** Automatically add structured (e.g., JSON) logs before and after key service method calls, including contextual information like `request_id` or `user_id` without manually passing it everywhere.

**Key `pico-ioc` Features:** AOP (`MethodInterceptor`, `@intercepted_by`), Scopes (`scope="request"` parameter), Component Injection into Interceptors.

## The Pattern

1.  **Context Holder (`RequestContext`):** A `@component` configured with `scope="request"` to store data specific to the current request (like `request_id`, `user_id`). This would typically be populated by middleware in a web application.
2.  **Structured Logger (`JsonLogger`):** (Optional) A helper component for formatting logs consistently as JSON.
3.  **Logging Interceptor (`LoggingInterceptor`):** A `@component` implementing `MethodInterceptor`. It:
    * Injects the `RequestContext` (which will be the one for the current request) and `JsonLogger`.
    * Reads method call details from `ctx` (`class_name`, `method_name`, `args`).
    * Reads context details from the injected `RequestContext`.
    * Logs an entry ("before") event in structured format.
    * Calls `call_next(ctx)` to execute the original method.
    * Logs an exit ("after") event (including result or exception details and duration) in structured format.
4.  **Alias (`log_calls`):** An alias defined as `@intercepted_by(LoggingInterceptor)` for cleaner application code.
5.  **Application:** Service classes or specific methods are decorated with `@log_calls` to enable the structured logging.

## Full, Runnable Example

### 1. Project Structure

```text
.
├── logging_lib/
│   ├── __init__.py
│   ├── context.py     <-- RequestContext
│   ├── interceptor.py <-- LoggingInterceptor & log_calls alias
│   └── logger.py      <-- JsonLogger (optional helper)
├── my_app/
│   ├── __init__.py
│   └── services.py    <-- Example service using @log_calls
└── main.py            <-- Simulation entrypoint
```

### 2\. Logging Library (`logging_lib/`)

#### Context (`context.py`)

```python
# logging_lib/context.py
from dataclasses import dataclass
from pico_ioc import component

# Use scope="request" parameter directly in @component
@component(scope="request")
@dataclass
class RequestContext:
    """Holds data specific to the current request."""
    request_id: str | None = None
    user_id: str | None = None

    def load(self, request_id: str, user_id: str | None = None):
        """Populates the context (e.g., called from middleware)."""
        self.request_id = request_id
        self.user_id = user_id
        print(f"[Context] Loaded RequestContext: ID={request_id}, User={user_id}")
```

#### Logger (`logger.py`) - Optional Helper

```python
# logging_lib/logger.py
import json
import logging
from pico_ioc import component

# Configure basic logging for the example
log = logging.getLogger("StructuredLogger")
logging.basicConfig(level=logging.INFO, format='%(message)s') # Simple format for demo output

@component
class JsonLogger:
    """A simple helper to log dictionary data as JSON lines."""
    def log(self, event_type: str, **kwargs):
        """Logs the event type and additional context as JSON."""
        log_entry = {"event": event_type, **kwargs}
        # Use default=str to handle potential non-serializable args/results in basic cases
        log.info(json.dumps(log_entry, default=str))
```

#### Interceptor & Alias (`interceptor.py`)

```python
# logging_lib/interceptor.py
import time
import inspect # For checking async
from typing import Any, Callable
from pico_ioc import component, MethodInterceptor, MethodCtx, intercepted_by
from .context import RequestContext
from .logger import JsonLogger # Import our helper

@component
class LoggingInterceptor(MethodInterceptor):
    """Intercepts method calls to add structured logging."""
    def __init__(self, context: RequestContext, logger: JsonLogger):
        # Inject the request-scoped context and the logger
        self.context = context
        self.logger = logger
        print("[Interceptor] LoggingInterceptor initialized.")

    # Use 'async def invoke' if you need to support intercepting async methods
    async def invoke(self, ctx: MethodCtx, call_next: Callable[[MethodCtx], Any]) -> Any:
        """Logs entry, executes the call, logs exit."""
        start_time = time.perf_counter()
        log_context = {
            "request_id": self.context.request_id,
            "user_id": self.context.user_id,
            "class": ctx.cls.__name__,
            "method": ctx.name,
            # Caution: Avoid logging full args/kwargs in production if they
            # contain sensitive data or are very large. Consider filtering/truncating.
            # "args": ctx.args,
            # "kwargs": ctx.kwargs
        }

        # Log method entry
        self.logger.log("method_entry", **log_context)

        try:
            # Execute the next interceptor or the original method
            result = call_next(ctx)
            # Await if the result is awaitable (e.g., an async method was called)
            if inspect.isawaitable(result):
                result = await result

            # Calculate duration
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Log method success exit
            log_context["duration_ms"] = round(duration_ms, 2)
            # Caution: Avoid logging large or sensitive results.
            # log_context["result_type"] = type(result).__name__
            self.logger.log("method_exit", status="success", **log_context)
            return result

        except Exception as e:
            # Calculate duration even on failure
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Log method failure exit
            log_context["duration_ms"] = round(duration_ms, 2)
            log_context["exception_type"] = type(e).__name__
            log_context["exception_message"] = str(e)
            self.logger.log("method_exit", status="failure", **log_context)
            raise # Important: re-raise the exception to maintain original behavior

# Define the alias for convenience
log_calls = intercepted_by(LoggingInterceptor)
```

#### Library `__init__.py`

```python
# logging_lib/__init__.py
from .context import RequestContext
from .interceptor import LoggingInterceptor, log_calls # Export the alias
from .logger import JsonLogger

__all__ = ["RequestContext", "LoggingInterceptor", "log_calls", "JsonLogger"]
```

### 3\. Application Code (`my_app/services.py`)

```python
# my_app/services.py
import time # For simulation
from pico_ioc import component
from logging_lib import log_calls # Import the alias

@component
@log_calls # Apply the interceptor alias to the whole class
class OrderService:
    """Example service whose methods will be logged automatically."""

    def create_order(self, user_id: str, item: str):
        """Simulates creating an order, possibly failing."""
        print(f"  [OrderService] Creating order for {user_id} - item: {item}")
        # Simulate work
        time.sleep(0.05)
        if item == "error":
            raise ValueError("Invalid item specified")
        return {"order_id": "ORD123", "status": "created"}

    def get_order_status(self, order_id: str):
        """Simulates fetching order status."""
        print(f"  [OrderService] Getting status for {order_id}")
        time.sleep(0.02)
        return "Shipped"

    # Example of an async method (requires invoke to be async)
    # async def async_operation(self, data: str):
    #     print(f"  [OrderService] Running async op with {data}")
    #     await asyncio.sleep(0.03)
    #     return "Async OK"

```

### 4\. Main Application (`main.py`)

```python
# main.py
import uuid
import asyncio # Needed if using async methods
from pico_ioc import init
# Adjust imports based on actual structure
from my_app.services import OrderService
from logging_lib import RequestContext

async def run_simulation():
    """Initializes container and simulates requests."""
    print("--- Initializing Container ---")
    container = init(modules=["my_app", "logging_lib"])
    print("--- Container Initialized ---\n")

    # --- Simulate Request 1 (Success) ---
    req_id_1 = f"req-{uuid.uuid4().hex[:4]}"
    print(f"--- SIMULATING REQUEST {req_id_1} (User: alice) ---")
    # Use container.scope to manage the request context
    with container.scope("request", req_id_1):
        # Populate context for this request
        ctx = await container.aget(RequestContext) # Use aget if invoke is async
        ctx.load(request_id=req_id_1, user_id="alice")

        # Get the service (will be created within the request scope if needed)
        service = await container.aget(OrderService) # Use aget if invoke is async

        print("Calling create_order (success)...")
        # Use await if the intercepted method could be async or invoke is async
        await service.create_order(user_id="alice", item="book")

        print("\nCalling get_order_status...")
        await service.get_order_status(order_id="ORD123")

        # Example for async method
        # print("\nCalling async_operation...")
        # await service.async_operation(data="test")

    print("-" * 40)

    # --- Simulate Request 2 (Failure) ---
    req_id_2 = f"req-{uuid.uuid4().hex[:4]}"
    print(f"\n--- SIMULATING REQUEST {req_id_2} (User: bob) ---")
    with container.scope("request", req_id_2):
        ctx = await container.aget(RequestContext)
        ctx.load(request_id=req_id_2, user_id="bob")

        service = await container.aget(OrderService)

        print("Calling create_order (failure)...")
        try:
            await service.create_order(user_id="bob", item="error")
        except ValueError as e:
            print(f"Caught expected error: {e}")

    print("-" * 40)
    print("\n--- Cleaning up Container ---")
    await container.cleanup_all_async() # Use async cleanup

if __name__ == "__main__":
    # Use asyncio.run if your simulation or intercepted methods are async
    asyncio.run(run_simulation())
    # If everything were synchronous, you could just call run_simulation()
```

### 5\. Example Output (Logs)

*(Output will be JSON lines, formatted here for readability)*

```json
{"event": "method_entry", "request_id": "req-...", "user_id": "alice", "class": "OrderService", "method": "create_order"}
{"event": "method_exit", "request_id": "req-...", "user_id": "alice", "class": "OrderService", "method": "create_order", "status": "success", "duration_ms": 50.12}

{"event": "method_entry", "request_id": "req-...", "user_id": "alice", "class": "OrderService", "method": "get_order_status"}
{"event": "method_exit", "request_id": "req-...", "user_id": "alice", "class": "OrderService", "method": "get_order_status", "status": "success", "duration_ms": 20.05}

{"event": "method_entry", "request_id": "req-...", "user_id": "bob", "class": "OrderService", "method": "create_order"}
{"event": "method_exit", "request_id": "req-...", "user_id": "bob", "class": "OrderService", "method": "create_order", "status": "failure", "duration_ms": 50.33, "exception_type": "ValueError", "exception_message": "Invalid item specified"}
```

## Benefits

  * **Automatic Context:** Logs automatically include `request_id`, `user_id`, etc., pulled from the request scope without manual passing. 🌐
  * **Structured Data:** JSON format is easily parseable by log aggregation and analysis tools (like ELK stack, Datadog, Splunk). 📊
  * **Clean Code:** Service methods remain focused purely on business logic, uncluttered by logging statements. ✨
  * **Reusable & Declarative:** The `LoggingInterceptor` and `@log_calls` alias can be applied selectively to any component or method needing detailed logs.  reused easily across your application.  reusing easily across your application. 🔁

