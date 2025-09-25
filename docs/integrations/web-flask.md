# Integration: Flask 🍶

Flask is a classic, flexible WSGI framework known for its minimalist core. It doesn't include a built-in dependency injection system, making `pico-ioc` an excellent companion for managing your application's service layer and keeping your views clean. ✨

This guide demonstrates the standard pattern for integrating `pico-ioc` with Flask:
1. Initialize the `pico-ioc` container alongside the Flask `app`.
2. Use Flask's **request hooks** (`@before_request`, `@teardown_request`) to manage `pico-ioc`'s `request` scope and container context.
3. Access your `pico-ioc`-managed services from within your Flask views (routes).

---

## 1. Container Initialization

The most straightforward approach is to create both the Flask `app` and the `pico-ioc` `container` within a factory function. This keeps the setup together and allows easy registration of the necessary hooks.

```python
# app.py
from flask import Flask
from pico_ioc import init, PicoContainer

# --- Assume components are defined elsewhere ---
# e.g., in 'app/services.py', 'app/database.py'
# from app.services import MyService
# from app.database import DatabaseConnection

# Global variable to hold the container
container: PicoContainer | None = None

def register_pico_hooks(app: Flask, container: PicoContainer):
    # We'll define the hook logic in the next step
    pass

def register_routes(app: Flask):
    # Define Flask routes here
    @app.route("/")
    def home():
        return "Hello from Flask + pico-ioc!"
    # More routes...

def create_app() -> Flask:
    """Factory function to create the Flask app and pico-ioc container."""
    global container
    app = Flask(__name__)
    print("🚀 Creating Flask app...")

    # --- Initialize the pico-ioc container ---
    print("📦 Initializing pico-ioc container...")
    container = init(
        modules=[
            "app.services", # Scan your service modules
            "app.database"
        ],
        profiles=("prod",) # Or load from Flask config/env
    )
    print(f"✅ Container initialized (ID: {container.container_id})")

    # --- Attach pico-ioc hooks to Flask ---
    register_pico_hooks(app, container)

    # --- Register Flask routes ---
    register_routes(app)

    return app

# Create the app instance when this module is loaded
app = create_app()

# --- For running locally ---
if __name__ == "__main__":
    # Make sure 'app' directory exists with dummy files if needed for demo
    try:
        os.makedirs("app", exist_ok=True)
        with open("app/services.py", "w") as f: f.write("from pico_ioc import component\n@component\nclass MyService:\n  def greet(self) -> str: return \"Hello from MyService!\"")
        with open("app/database.py", "w") as f: f.write("from pico_ioc import component\n@component\nclass DatabaseConnection: pass")
    except Exception: pass

    import os # Needed for makedirs
    app.run(debug=True) # Run Flask dev server
```

-----

## 2\. Request Scope Management (The Hooks)

To make `scope("request")` work correctly (i.e., one component instance per web request), we need to signal the start and end of each request to `pico-ioc`. Flask's `@app.before_request` and `@app.teardown_request` decorators are ideal for this.

We'll use these hooks to:

1.  Generate a unique `request_id`.
2.  **Activate** the `pico-ioc` `request` scope using `container.activate_scope()`.
3.  **Activate** the container context using `container.activate()` so `PicoContainer.get_current()` works within the view.
4.  Store the `contextvars` **tokens** returned by the activation calls.
5.  **Deactivate** everything in reverse order after the request using the stored tokens in `@teardown_request`.

<!-- end list -->

```python
# app.py (continued)
import uuid
import contextvars
from flask import g # Use Flask's 'g' object to store tokens per request

# ... (imports: Flask, init, PicoContainer, etc.) ...

# Make sure the global 'container' variable is accessible here
# container: PicoContainer | None = None (defined earlier)

def register_pico_hooks(app: Flask, current_container: PicoContainer):
    """Registers before_request and teardown_request handlers."""

    @app.before_request
    def _pico_activate_context():
        """
        Activates the container and request scope before handling the request.
        Stores context tokens in Flask's request global `g`.
        """
        if not current_container: return # Safety check

        request_id = str(uuid.uuid4())
        g._pico_request_id = request_id # Store for potential logging

        # 1. Activate the 'request' scope
        request_scope_token = current_container.activate_scope(
            "request", request_id
        )
        # 2. Activate the container context
        container_token = current_container.activate()

        # 3. Store tokens in Flask's 'g' for teardown
        g._pico_request_scope_token = request_scope_token
        g._pico_container_token = container_token
        # print(f"Activated context for request {request_id}") # Debug logging

    @app.teardown_request
    def _pico_deactivate_context(exception=None):
        """
        Deactivates the container and request scope after the request.
        Retrieves tokens from Flask's `g`.
        """
        if not current_container or not hasattr(g, '_pico_container_token'): return

        container_token = g.pop('_pico_container_token', None)
        request_scope_token = g.pop('_pico_request_scope_token', None)
        # request_id = g.pop('_pico_request_id', 'unknown') # Debug logging

        try:
            # 1. Deactivate container context (must be first)
            if container_token:
                current_container.deactivate(container_token)

            # 2. Deactivate request scope
            if request_scope_token:
                current_container.deactivate_scope("request", request_scope_token)
            # print(f"Deactivated context for request {request_id}") # Debug logging
        except Exception as e:
            # Log error during deactivation if necessary
            app.logger.error(f"Error during pico-ioc context teardown: {e}")


# ... (create_app function, app instance, and __main__ block) ...
```

**Note:** We use Flask's `g` object to store the `contextvars` tokens. `g` is automatically cleaned up by Flask after each request, ensuring proper isolation.

-----

## 3\. Injecting Services into Routes (Views)

Unlike FastAPI's `Depends`, Flask doesn't have a built-in per-route dependency injection mechanism. The standard Flask pattern is to access shared resources (like our container) within the view function itself.

Thanks to our `before_request` hook activating the context, we can reliably use `PicoContainer.get_current()` inside any view function to get the correct container instance. Then, we simply call `.get()` on it.

```python
# --- Define some example components ---
# app/services.py
from pico_ioc import component, scope, PicoContainer

@component(scope="request")
class RequestData:
    """A component unique to each request."""
    def __init__(self):
        # Access the current container and its scope manager to get the ID
        self.scope_id = "N/A"
        current_container = PicoContainer.get_current()
        if current_container:
            self.scope_id = current_container.scopes.get_id("request")
        print(f"RequestData CREATED for scope ID: {self.scope_id}")

@component
class MyService:
    """A singleton service depending on request-scoped data."""
    def __init__(self, data: RequestData):
        self.data = data
        print("MyService CREATED/INJECTED")

    def greet(self) -> str:
        return f"Hello from MyService! Your request ID is {self.data.scope_id}"

# --- Update Flask routes ---
# app.py (inside register_routes function)
from app.services import MyService # Import your service

def register_routes(app: Flask):
    @app.route("/")
    def home():
        return "Hello from Flask + pico-ioc!"

    @app.route("/greet")
    def greet_user():
        """
        Flask view using pico-ioc for service resolution.
        """
        # 1. Get the currently active container (set by the hook)
        current_container = PicoContainer.get_current()
        if not current_container:
            return "Error: Pico-IoC container context not found!", 500

        try:
            # 2. 'get' your service. Pico-ioc handles dependencies,
            #    including the request-scoped 'RequestData'.
            #    Use .get() for sync Flask views.
            service = current_container.get(MyService)

            # 3. Call the service method
            message = service.greet()
            return message

        except Exception as e:
            app.logger.error(f"Error resolving or using service: {e}")
            return f"An error occurred: {e}", 500

# ... (rest of app.py: create_app, app instance, __main__) ...
```

When a request hits `/greet`:

1.  `@before_request` runs, activating the `request` scope and container context.
2.  The `greet_user` view runs.
3.  `PicoContainer.get_current()` successfully retrieves the active container.
4.  `container.get(MyService)` resolves `MyService`. This triggers the resolution of its dependency `RequestData`. Since the `request` scope is active, `pico-ioc` correctly creates or retrieves the `RequestData` instance for *this specific request*.
5.  The service method executes.
6.  `@teardown_request` runs, deactivating the scope and context.

This pattern provides clean separation: Flask handles routing and HTTP, while `pico-ioc` manages your application's components and their lifecycles. ✅

-----

## Next Steps

This pattern is typical for integrating IoC with WSGI frameworks. Now, let's look at Django, a more "batteries-included" framework, which requires a slightly different approach focusing on a distinct service layer.

  * **[Django Integration](./web-django.md)**: Learn how to initialize the container within Django's app lifecycle and use `pico-ioc` for a decoupled service layer alongside the Django ORM.

