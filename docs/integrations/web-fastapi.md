# Integration: FastAPI 🚀

FastAPI has its own dependency injection system based on `Depends`. This system is excellent for **web-layer dependencies** (like request bodies, headers, path parameters, and security tokens).

`pico-ioc` complements this by managing your deeper **application layer** (services, repositories, clients). You can easily integrate the two to get the best of both worlds: FastAPI handles the web request context, and `pico-ioc` manages your core business logic components. 🤝

This recipe shows how to:
1. Initialize the `pico-ioc` container during FastAPI's application **lifespan**.
2. Create a **request-scoped** container context for every incoming HTTP request using **middleware**.
3. Inject your `pico-ioc`-managed services directly into your FastAPI routes using `Depends` via a **simple bridge function**.

---

## 1. Container Initialization (Lifespan)

First, we need to create our main `pico-ioc` container. We'll define a global `PicoContainer` variable that gets initialized when the FastAPI application starts, using the standard `lifespan` context manager.

```python
# main.py
import uvicorn
import pico_ioc.event_bus # Example module to scan
from contextlib import asynccontextmanager
from fastapi import FastAPI
from pico_ioc import init, PicoContainer

# --- Assume your components are defined elsewhere ---
# e.g., in 'app/services.py', 'app/database.py'
# from app.services import MyService
# from app.database import DatabaseConnection

# --- Global Container Variable ---
# It starts as None and is initialized during startup.
container: PicoContainer | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage the pico-ioc container's lifecycle integrated with FastAPI's startup and shutdown.
    """
    global container
    print("🚀 Application starting... Initializing pico-ioc container.")

    # --- Initialize the container ---
    container = init(
        modules=[
            "app.services", # Your application's services
            "app.database", # Your database components
            pico_ioc.event_bus # Include if using the event bus
        ],
        profiles=("prod",) # Set active profiles (e.g., from env vars)
    )
    print(f"✅ Container initialized (ID: {container.container_id})")

    yield # --- Application is now running ---

    # --- Clean up on shutdown ---
    print("🛑 Application shutting down... Cleaning up container.")
    if container:
        await container.cleanup_all_async() # Use async cleanup
        container.shutdown()
    print("🗑️ Container cleanup complete.")

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return {"message": "Welcome to the FastAPI + pico-ioc app!"}

# --- For running locally ---
if __name__ == "__main__":
    # Make sure 'app' directory exists with dummy files if needed for demo
    # e.g., app/services.py:
    # from pico_ioc import component
    # @component
    # class MyService: def greet(self) -> str: return "Hello from MyService!"
    # e.g., app/database.py:
    # from pico_ioc import component
    # @component
    # class DatabaseConnection: pass

    try:
        os.makedirs("app", exist_ok=True)
        with open("app/services.py", "w") as f: f.write("from pico_ioc import component\n@component\nclass MyService:\n  def greet(self) -> str: return \"Hello from MyService!\"")
        with open("app/database.py", "w") as f: f.write("from pico_ioc import component\n@component\nclass DatabaseConnection: pass")
    except Exception: pass # Ignore if files exist or cannot be created

    import os # Needed formakedirs
    uvicorn.run(app, host="127.0.0.1", port=8000)
```

This ensures we have a single, application-wide `PicoContainer` instance ready when the server starts.

-----

## 2\. Request Scope Middleware

To use `scope("request")` components (components that should have one instance per HTTP request), we need to inform `pico-ioc` about the start and end of each request. FastAPI **middleware** is the perfect place for this.

This middleware will:

1.  Generate a **unique ID** for each incoming request.
2.  Use `container.scope("request", request_id)` to **activate the `request` scope** for `pico-ioc`.
3.  Use `container.as_current()` to make this specific container **globally accessible** within the request's context (important for `PicoContainer.get_current()`).

<!-- end list -->

```python
# main.py (continued)
import uuid
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

# ... (previous setup code: imports, container var, lifespan, app) ...

class PicoScopeMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """
        Activates the 'request' scope and the container context for each request.
        """
        if not container:
            # Should not happen if lifespan is correctly set up
            return Response("Internal Server Error: Container not initialized", status_code=500)

        request_id = str(uuid.uuid4())

        # Activate pico-ioc's request scope and container context
        with container.scope("request", request_id):
            with container.as_current():
                # Add request_id to request state for potential logging/tracing
                request.state.request_id = request_id
                try:
                    response = await call_next(request)
                    return response
                except Exception as e:
                    # Optional: Add error logging here, potentially using request_id
                    print(f"Error during request {request_id}: {e}")
                    # Re-raise or return an error response
                    raise e # Or: return Response("Internal Server Error", status_code=500)

# Add the middleware to the FastAPI app
app.add_middleware(PicoScopeMiddleware)

# ... (root route and uvicorn run from previous step) ...
```

Now, within any request handled after this middleware, `pico-ioc` knows which request context is active.

-----

## 3\. Injecting Services into Routes (`Depends` Bridge)

The final step is getting your `pico-ioc`-managed services into your FastAPI routes. FastAPI's `Depends` doesn't automatically know about `pico-ioc`, so we create a small **bridge function**.

This bridge uses `Depends` to get the *currently active* `pico-ioc` container (made available by our middleware) and then uses the container's `aget()` method to resolve the desired service.

```python
# main.py (continued)
from fastapi import Depends
from typing import Type, Callable, TypeVar

# ... (previous setup code: imports, container, lifespan, middleware, app) ...

# --- Dependency Bridge ---

T = TypeVar("T") # Generic type variable

def get_current_container() -> PicoContainer:
    """
    A simple FastAPI dependency that retrieves the currently active PicoContainer.
    Relies on the PicoScopeMiddleware having run first.
    """
    current = PicoContainer.get_current()
    if not current:
        # This error indicates the middleware might not be set up correctly
        raise RuntimeError("No active PicoContainer context found! Ensure PicoScopeMiddleware is added.")
    return current

def get_service(service_type: Type[T]) -> Callable[..., T]:
    """
    The bridge function. Returns a *new function* compatible with FastAPI's `Depends`.
    This new function, when called by FastAPI, will:
    1. Get the current container using `Depends(get_current_container)`.
    2. Resolve the requested `service_type` using `container.aget()`.
    """
    async def _dependency(
        container: PicoContainer = Depends(get_current_container)
    ) -> T:
        # Use aget for async resolution, respecting async lifecycle methods
        return await container.aget(service_type)

    return _dependency

# --- Example Usage ---

# Assume MyService is defined in app/services.py and registered via @component
# (Code for MyService shown in the uvicorn run section earlier)
from app.services import MyService

# Use the bridge in your route's dependencies!
@app.get("/greet")
async def greet_user(
    service: MyService = Depends(get_service(MyService)) # <-- Integration point!
):
    """
    FastAPI calls `get_service(MyService)`, which returns `_dependency`.
    FastAPI then calls `_dependency`, which gets the active container via `Depends`
    and resolves `MyService` using `container.aget()`.
    """
    greeting = service.greet()
    return {"message": greeting}

# ... (uvicorn run from first step) ...

```

This pattern provides seamless integration:

  * FastAPI handles web concerns and route parameters.
  * `pico-ioc` manages your application's object graph and lifecycle.
  * You get fully asynchronous, request-scoped dependency injection for your services within FastAPI. 🎉

-----

## Next Steps

This pattern is ideal for ASGI frameworks like FastAPI. Next, let's explore how to achieve similar integration with Flask, a popular WSGI framework, which requires slightly different handling of request context.

  * **[Flask Integration](./web-flask.md)**: Learn how to manage the container context using Flask's `g` object and request hooks (`@before_request`, `@teardown_request`).

