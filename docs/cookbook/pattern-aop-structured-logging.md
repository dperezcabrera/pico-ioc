# Cookbook: Pattern: Structured Logging with AOP

Goal: Automatically add structured logs (e.g., JSON) before and after key service method calls, including contextual information like request_id or user_id without manually passing it everywhere.

Key pico_ioc features: AOP (MethodInterceptor, @intercepted_by), scopes (scope="request"), component injection into interceptors.

The Pattern

- Context Holder (RequestContext): A @component configured with scope="request" to store data specific to the current request (like request_id, user_id). This would typically be populated by middleware in a web application.
- Structured Logger (JsonLogger): Optional helper component for formatting logs consistently as JSON.
- Logging Interceptor (LoggingInterceptor): A @component implementing MethodInterceptor that:
  - Injects the RequestContext (which will be the one for the current request) and JsonLogger.
  - Reads method call details from ctx (class_name, method_name, args as needed).
  - Reads context details from the injected RequestContext.
  - Logs an entry ("before") event in structured format.
  - Calls call_next(ctx) to execute the original method.
  - Logs an exit ("after") event (including result or exception details and duration) in structured format.
- Alias (log_calls): An alias defined as @intercepted_by(LoggingInterceptor) for cleaner application code.
- Application: Service classes or specific methods are decorated with @log_calls to enable the structured logging.

Full, Runnable Example

1. Project Structure

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

2. Logging Library (logging_lib/)

Context (context.py)

```python
# logging_lib/context.py
from dataclasses import dataclass
from pico_ioc import component

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

Logger (logger.py) - Optional Helper

```python
# logging_lib/logger.py
import json
import logging
from pico_ioc import component

log = logging.getLogger("StructuredLogger")
logging.basicConfig(level=logging.INFO, format="%(message)s")

@component
class JsonLogger:
    """Helper to log dictionary data as JSON lines."""
    def log(self, event_type: str, **kwargs):
        """Logs the event type and additional context as JSON."""
        entry = {"event": event_type, **kwargs}
        log.info(json.dumps(entry, default=str))
```

Interceptor & Alias (interceptor.py)

```python
# logging_lib/interceptor.py
import time
import inspect
from typing import Any, Callable
from pico_ioc import component, MethodInterceptor, MethodCtx, intercepted_by
from .context import RequestContext
from .logger import JsonLogger

@component
class LoggingInterceptor(MethodInterceptor):
    """Intercepts method calls to add structured logging."""
    def __init__(self, context: RequestContext, logger: JsonLogger):
        self.context = context
        self.logger = logger
        print("[Interceptor] LoggingInterceptor initialized.")

    async def invoke(self, ctx: MethodCtx, call_next: Callable[[MethodCtx], Any]) -> Any:
        """Logs entry, executes the call, logs exit."""
        start = time.perf_counter()
        log_ctx = {
            "request_id": self.context.request_id,
            "user_id": self.context.user_id,
            "class": ctx.cls.__name__,
            "method": ctx.name,
            # Consider carefully whether to include args/kwargs due to PII and size.
            # "args": ctx.args,
            # "kwargs": ctx.kwargs,
        }

        self.logger.log("method_entry", **log_ctx)

        try:
            result = call_next(ctx)
            if inspect.isawaitable(result):
                result = await result

            duration_ms = (time.perf_counter() - start) * 1000
            log_ctx["duration_ms"] = round(duration_ms, 2)
            self.logger.log("method_exit", status="success", **log_ctx)
            return result

        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            log_ctx["duration_ms"] = round(duration_ms, 2)
            log_ctx["exception_type"] = type(e).__name__
            log_ctx["exception_message"] = str(e)
            self.logger.log("method_exit", status="failure", **log_ctx)
            raise

log_calls = intercepted_by(LoggingInterceptor)
```

Library __init__.py

```python
# logging_lib/__init__.py
from .context import RequestContext
from .interceptor import LoggingInterceptor, log_calls
from .logger import JsonLogger

__all__ = ["RequestContext", "LoggingInterceptor", "log_calls", "JsonLogger"]
```

3. Application Code (my_app/services.py)

```python
# my_app/services.py
import time
from pico_ioc import component
from logging_lib import log_calls

@component
@log_calls
class OrderService:
    """Example service whose methods will be logged automatically."""

    def create_order(self, user_id: str, item: str):
        """Simulates creating an order, possibly failing."""
        print(f"  [OrderService] Creating order for {user_id} - item: {item}")
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

4. Main Application (main.py)

```python
# main.py
import uuid
import asyncio
from pico_ioc import init
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
    with container.scope("request", req_id_1):
        ctx = await container.aget(RequestContext)
        ctx.load(request_id=req_id_1, user_id="alice")

        service = await container.aget(OrderService)

        print("Calling create_order (success)...")
        await service.create_order(user_id="alice", item="book")

        print("\nCalling get_order_status...")
        await service.get_order_status(order_id="ORD123")

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
    await container.cleanup_all_async()

if __name__ == "__main__":
    asyncio.run(run_simulation())
```

5. Example Output (Logs)

```json
{"event":"method_entry","request_id":"req-...","user_id":"alice","class":"OrderService","method":"create_order"}
{"event":"method_exit","request_id":"req-...","user_id":"alice","class":"OrderService","method":"create_order","status":"success","duration_ms":50.12}

{"event":"method_entry","request_id":"req-...","user_id":"alice","class":"OrderService","method":"get_order_status"}
{"event":"method_exit","request_id":"req-...","user_id":"alice","class":"OrderService","method":"get_order_status","status":"success","duration_ms":20.05}

{"event":"method_entry","request_id":"req-...","user_id":"bob","class":"OrderService","method":"create_order"}
{"event":"method_exit","request_id":"req-...","user_id":"bob","class":"OrderService","method":"create_order","status":"failure","duration_ms":50.33,"exception_type":"ValueError","exception_message":"Invalid item specified"}
```

Benefits

- Automatic context: Logs automatically include request_id, user_id, etc., pulled from the request scope without manual passing.
- Structured data: JSON format is easily parseable by log aggregation and analysis tools (ELK, Datadog, Splunk).
- Clean code: Service methods remain focused on business logic, uncluttered by logging statements.
- Reusable and declarative: The LoggingInterceptor and @log_calls alias can be applied selectively to any component or method needing detailed logs and reused easily across your application.

Notes and Considerations

- Sensitive data: Be careful when logging args/kwargs or results; filter out PII and large payloads.
- Sync vs async: This example uses an async interceptor to handle both sync and async methods. If your app is fully synchronous, you can implement invoke as a regular def and use container.get/service.method() without awaits.
- Performance: Interception adds overhead. Keep logging lightweight and consider sampling for very hot paths.
- Scope management: Ensure middleware or request-handling code enters the request scope and populates RequestContext before invoking services.
