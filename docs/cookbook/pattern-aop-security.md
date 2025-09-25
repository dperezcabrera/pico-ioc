# Cookbook: Pattern: Security Checks with AOP (`@secured`)

**Goal:** Implement a declarative security mechanism where methods can be annotated with required roles or permissions (e.g., `@secured(roles=["admin"])`). An AOP interceptor checks the current user's privileges (obtained from a request-scoped context) before allowing method execution.

**Key `pico-ioc` Features:** AOP (`MethodInterceptor`, `@intercepted_by`), Scopes (`scope="request"` parameter), Component Injection into Interceptors. An alias (`apply_security`) enhances readability.

## The Pattern

1.  **`@secured` Decorator:** A custom decorator that attaches required roles/permissions metadata to methods. It does *not* perform the check itself.
2.  **`SecurityContext` Component:** A `@component` configured with `scope="request"`. It holds the current user's security information (e.g., user ID, roles, permissions), typically populated by authentication middleware early in the request lifecycle.
3.  **`SecurityInterceptor` Component:** A `@component` implementing `MethodInterceptor`. It injects the request-scoped `SecurityContext` and performs the authorization check based on the `@secured` metadata found on the target method. It raises an `AuthorizationError` if the check fails.
4.  **`apply_security` Alias:** Defined as `@intercepted_by(SecurityInterceptor)` for cleaner application code when applying the interceptor, often at the class level.
5.  **Application:** Service classes are decorated with `@apply_security`, and specific methods needing protection are decorated with `@secured(...)`.
6.  **Bootstrap & Request Handling:** `init()` scans all relevant modules. Web framework middleware manages the `request` scope activation/deactivation and populates the `SecurityContext` for each request.

## Full, Runnable Example

### 1. Project Structure

```text
.
├── security_lib/
│   ├── __init__.py
│   ├── context.py     <-- SecurityContext
│   ├── decorator.py   <-- @secured and AuthorizationError
│   └── interceptor.py <-- SecurityInterceptor & apply_security alias
├── my_app/
│   ├── __init__.py
│   └── services.py    <-- Example service using the pattern
└── main.py            <-- Simulation entrypoint (no web server)
```

### 2\. Security Library (`security_lib/`)

#### Decorator & Exception (`decorator.py`)

```python
# security_lib/decorator.py
import functools
from typing import Callable, List, Optional, Set

# Metadata key used to store security requirements on decorated methods
SECURED_META = "_pico_secured_meta"

class AuthorizationError(Exception):
    """Custom exception raised for failed security checks."""
    pass

def secured(*, roles: Optional[List[str]] = None, permissions: Optional[List[str]] = None):
    """
    Decorator to specify required roles or permissions for a method.
    Attaches metadata, does not perform the check itself.
    """
    if not roles and not permissions:
        raise ValueError("Must specify either 'roles' or 'permissions' for @secured")

    # Store requirements as sets for efficient checking
    metadata = {"roles": set(roles or []), "permissions": set(permissions or [])}

    def decorator(func: Callable) -> Callable:
        # Attach metadata to the function object
        setattr(func, SECURED_META, metadata)

        # Use functools.wraps to preserve original function metadata (good practice)
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # The wrapper itself doesn't do anything special here,
            # as the interceptor will handle the logic.
            return func(*args, **kwargs)

        # Ensure metadata is also on the wrapper if needed by introspection tools
        setattr(wrapper, SECURED_META, metadata)
        return wrapper
    return decorator
```

#### Security Context (`context.py`)

```python
# security_lib/context.py
from dataclasses import dataclass, field
from typing import Set, List
from pico_ioc import component

# Use scope="request" directly in the @component decorator
@component(scope="request") # One instance per request context
@dataclass
class SecurityContext:
    """Holds the current authenticated user's security information for a request."""
    user_id: str | None = None
    roles: Set[str] = field(default_factory=set)
    permissions: Set[str] = field(default_factory=set)
    is_authenticated: bool = False

    def load_from_request(self, user_id: str, roles: List[str], perms: List[str]):
        """
        Populates the context. In a real app, this would be called by
        authentication middleware based on a token, session, etc.
        """
        self.user_id = user_id
        self.roles = set(r.lower() for r in roles) # Normalize roles
        self.permissions = set(p.lower() for p in perms) # Normalize permissions
        self.is_authenticated = True
        print(f"[Context] Loaded SecurityContext for user '{user_id}' with roles={self.roles}, perms={self.permissions}")
```

#### Interceptor & Alias (`interceptor.py`)

```python
# security_lib/interceptor.py
import inspect # Needed for async check
from typing import Any, Callable
from pico_ioc import component, MethodInterceptor, MethodCtx, intercepted_by
from .context import SecurityContext
from .decorator import SECURED_META, AuthorizationError

@component # The interceptor itself is a component managed by pico-ioc
class SecurityInterceptor(MethodInterceptor):
    """
    Checks @secured metadata against the current SecurityContext before
    allowing the method call to proceed.
    """
    def __init__(self, context: SecurityContext):
        # Inject the SecurityContext for the *current request*
        self.context = context
        print("[Interceptor] SecurityInterceptor initialized (instance depends on scope).")

    # Use 'async def invoke' if the methods being secured might be async
    async def invoke(self, ctx: MethodCtx, call_next: Callable[[MethodCtx], Any]) -> Any:
        """Performs the security check."""
        try:
            # Access the *original* unbound function from the class
            # to reliably read decorator metadata. ctx.method might be already wrapped.
            original_func = getattr(ctx.cls, ctx.name)
            security_meta = getattr(original_func, SECURED_META, None)
        except AttributeError:
            security_meta = None # Should not happen if called on a valid method

        # If the method doesn't have @secured metadata, proceed immediately
        if not security_meta:
            result = call_next(ctx)
            # Await if the called method was async
            return await result if inspect.isawaitable(result) else result

        print(f"[Interceptor] Checking security for {ctx.cls.__name__}.{ctx.name}")

        # --- 1. Authentication Check ---
        if not self.context.is_authenticated:
            raise AuthorizationError("User is not authenticated.")

        # --- 2. Role Check ---
        required_roles: Set[str] = security_meta.get("roles", set())
        if required_roles:
            missing_roles = required_roles - self.context.roles
            if missing_roles:
                raise AuthorizationError(
                    f"User '{self.context.user_id}' lacks required roles: {missing_roles}"
                )

        # --- 3. Permission Check ---
        required_perms: Set[str] = security_meta.get("permissions", set())
        if required_perms:
            missing_perms = required_perms - self.context.permissions
            if missing_perms:
                  raise AuthorizationError(
                      f"User '{self.context.user_id}' lacks required permissions: {missing_perms}"
                  )

        # --- Check Passed ---
        print("[Interceptor] ✅ Security check PASSED.")
        result = call_next(ctx)
        # Await if the called method was async
        return await result if inspect.isawaitable(result) else result

# --- Define the alias ---
# apply_security makes the code more readable at the class level
apply_security = intercepted_by(SecurityInterceptor)
```

#### Library `__init__.py`

```python
# security_lib/__init__.py
from .decorator import secured, AuthorizationError
from .context import SecurityContext
from .interceptor import SecurityInterceptor, apply_security # Export the alias too

__all__ = [
    "secured", "AuthorizationError",
    "SecurityContext", "SecurityInterceptor", "apply_security" # Make alias available
]
```

### 3\. Application Code (`my_app/services.py`)

Apply the `@secured` decorator to methods that require checks, and use the `@apply_security` alias (usually at the class level) to activate the interceptor.

```python
# my_app/services.py
from pico_ioc import component
# Import the alias and the @secured decorator
from security_lib import secured, apply_security

@component
@apply_security # <-- Apply the interceptor alias to the whole class
class AdminService:
    """An example service with methods requiring different privileges."""

    @secured(roles=["admin"]) # <-- Define requirements for this specific method
    def perform_admin_action(self, action: str):
        """Requires the 'admin' role."""
        print(f"[AdminService] Performing critical admin action: {action}")
        # ... actual logic ...
        return f"Admin action '{action}' completed successfully."

    @secured(permissions=["read_data", "view_audit_log"]) # <-- Multiple permissions
    def view_sensitive_data(self) -> dict:
        """Requires specific permissions."""
        print("[AdminService] Accessing sensitive data...")
        # ... actual logic ...
        return {"data": "highly_secret_information", "log_entries": []}

    # No @secured decorator on this method
    def get_public_info(self) -> str:
        """Accessible by any authenticated user."""
        # The SecurityInterceptor will still run (due to @apply_security on the class),
        # but it will find no @secured metadata and immediately call the original method.
        # The interceptor *does* still enforce the authentication check implicitly.
        print("[AdminService] Getting public information...")
        return "This information is public."

    # Example of an async method
    # async def async_admin_op(self, task: str):
    #     await asyncio.sleep(0.1)
    #     print(f"[AdminService] Async admin op {task} done.")
    #     return "Async OK"

```

### 4\. Main Application (`main.py`) - Simulation

This simulates handling different requests with different users by activating the `request` scope and populating the `SecurityContext`.

```python
# main.py
import uuid
import time
import asyncio # Needed if using async methods
from pico_ioc import init, PicoContainer
# Adjust imports for your structure
from my_app.services import AdminService
from security_lib import SecurityContext, AuthorizationError

async def run_simulation():
    """Initializes container and simulates web requests."""
    print("--- Initializing Container ---")
    # Scan modules containing components, context, interceptor, etc.
    container = init(modules=["my_app", "security_lib"])
    print("--- Container Initialized ---\n")

    # --- Simulate Request 1: Admin User ---
    print("--- SIMULATING REQUEST 1: ADMIN USER ---")
    request_id_1 = f"req-{uuid.uuid4().hex[:6]}"
    # Use container.scope to manage the request context
    with container.scope("request", request_id_1):
        # 1. Populate SecurityContext for this 'request'
        # (In a real app, middleware does this based on auth token/session)
        sec_ctx = await container.aget(SecurityContext) # Use aget if invoke is async
        sec_ctx.load_from_request(
            user_id="admin_user",
            roles=["admin", "user"], # Has 'admin' role
            perms=["read_data", "view_audit_log"] # Has needed permissions
        )

        # 2. Get the service (interceptor gets the correct SecurityContext)
        admin_service = await container.aget(AdminService)

        try:
            print(f"\nCalling perform_admin_action (should PASS)...")
            result = await admin_service.perform_admin_action("restart_server")
            print(f"✅ Result: {result}")

            await asyncio.sleep(0.01) # Small delay for output clarity
            print(f"\nCalling view_sensitive_data (should PASS)...")
            data = await admin_service.view_sensitive_data()
            print(f"✅ Result: {data}")

            await asyncio.sleep(0.01)
            print(f"\nCalling get_public_info (should PASS)...")
            info = await admin_service.get_public_info()
            print(f"✅ Result: {info}")

        except AuthorizationError as e:
            print(f"❌ Authorization Error (UNEXPECTED): {e}")
    print("-" * 50)


    # --- Simulate Request 2: Regular User (Lacks Role) ---
    print("\n--- SIMULATING REQUEST 2: REGULAR USER ---")
    request_id_2 = f"req-{uuid.uuid4().hex[:6]}"
    with container.scope("request", request_id_2):
        sec_ctx = await container.aget(SecurityContext)
        # This user only has the 'user' role and 'read_data' permission
        sec_ctx.load_from_request(
            user_id="normal_user",
            roles=["user"], # Lacks 'admin' role
            perms=["read_data"] # Lacks 'view_audit_log' permission
        )

        admin_service = await container.aget(AdminService)

        try:
            print(f"\nCalling perform_admin_action (should FAIL)...")
            result = await admin_service.perform_admin_action("delete_database")
            print(f"✅ Result: {result}") # Should not reach here
        except AuthorizationError as e:
            print(f"👍 Caught Expected Error: {e}") # Expect role error

        await asyncio.sleep(0.01)
        try:
            print(f"\nCalling view_sensitive_data (should FAIL)...")
            data = await admin_service.view_sensitive_data()
            print(f"✅ Result: {data}") # Should not reach here
        except AuthorizationError as e:
            print(f"👍 Caught Expected Error: {e}") # Expect permission error

        await asyncio.sleep(0.01)
        try:
            print(f"\nCalling get_public_info (should PASS)...")
            info = await admin_service.get_public_info()
            print(f"✅ Result: {info}")
        except AuthorizationError as e:
             print(f"❌ Authorization Error (UNEXPECTED): {e}")
    print("-" * 50)


    # --- Simulate Request 3: Unauthenticated User ---
    print("\n--- SIMULATING REQUEST 3: UNAUTHENTICATED USER ---")
    request_id_3 = f"req-{uuid.uuid4().hex[:6]}"
    with container.scope("request", request_id_3):
        # SecurityContext is created automatically, but remains unpopulated
        # (is_authenticated=False) because load_from_request wasn't called.
        admin_service = await container.aget(AdminService)
        try:
            print(f"\nCalling get_public_info (should FAIL)...")
            info = await admin_service.get_public_info()
            print(f"✅ Result: {info}") # Should not reach here
        except AuthorizationError as e:
            print(f"👍 Caught Expected Error: {e}") # Expect authentication error
    print("-" * 50)

    print("\n--- Cleaning up Container ---")
    await container.cleanup_all_async()

if __name__ == "__main__":
    asyncio.run(run_simulation())
```

## 5\. Benefits

  * **Declarative Security:** Permissions and roles are clearly stated on methods using `@secured`. 📜
  * **Clean Business Logic:** Service methods focus solely on their core task, free from authorization boilerplate. ✨
  * **Centralized & Reusable Logic:** Security checks are handled consistently by the `SecurityInterceptor`.  centralised central reused central reusable central reusable. 🏛️
  * **Readability:** The `@apply_security` alias clearly indicates that security checks are active for the class or method. 👀
  * **Testable:**
      * Services can be unit-tested without the interceptor by initializing the container differently or not using it at all.
      * The `SecurityInterceptor` itself can be tested by providing different `SecurityContext` states. 🧪
  * **Flexible:** Easily extend `@secured` or the `SecurityInterceptor` to support more complex authorization rules (e.g., checking ownership, specific resource permissions). 🔧

