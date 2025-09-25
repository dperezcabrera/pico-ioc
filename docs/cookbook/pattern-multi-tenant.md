# Cookbook: Pattern: Multi-Tenant Applications

**Goal:** Build a single application that serves multiple customers (tenants), where each tenant has its own isolated configuration, services, and data.

This is a common pattern for SaaS (Software as a Service) applications. The key requirement is **isolation**: Tenant A should *never* be able to access Tenant B's data or services.

`pico-ioc` solves this by leveraging its [Container Context](./observability/container-context.md) system. Instead of one global container, you create a **container-per-tenant**.

## The Pattern

1.  **Base Components:** Define your components (`UserService`, `DatabaseClient`) as usual.
2.  **Tenant Configuration:** Define a `TenantConfig` component that holds tenant-specific settings (like their database URL or API key).
3.  **Tenant Manager:** Create a singleton service, `TenantManager`, whose job is to `init()` a *new, isolated* `PicoContainer` for each tenant. It uses `init(overrides={...})` to inject that tenant's specific `TenantConfig`.
4.  **Middleware:** Write web middleware that:
    * Reads a tenant identifier from the request (e.g., `X-Tenant-ID` header).
    * Asks the `TenantManager` for that tenant's specific container.
    * Activates that container using `with container.as_current()`.
5.  **Route:** Your route/view code remains simple. It just calls `PicoContainer.get_current().get(UserService)` and automatically receives the correct, isolated service for the current tenant.

---

## Full, Runnable Example

This example uses FastAPI to simulate the web layer, but the core logic (`TenantManager`, `middleware`) can be adapted to any framework.

```python
# multi_tenant_app.py
import uvicorn
import uuid
from fastapi import FastAPI, Request, Depends
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Dict, Type

from pico_ioc import (
    init, PicoContainer, component, 
    PicoError, configure, cleanup
)

# --- 1. Define Tenant-Specific Components ---

@dataclass
class TenantConfig:
    """Holds the unique configuration for a single tenant."""
    tenant_id: str
    database_url: str

@component
class TenantDatabase:
    """
    A database client that is unique to each tenant.
    It depends on the TenantConfig.
    """
    def __init__(self, config: TenantConfig):
        self.db_url = config.database_url
        self.tenant_id = config.tenant_id
        print(f"[{self.tenant_id}] TenantDatabase CREATED: {self.db_url}")

    def get_data(self) -> str:
        return f"Data for {self.tenant_id} from {self.db_url}"

    @cleanup
    def close(self):
        print(f"[{self.tenant_id}] TenantDatabase CLEANUP")

@component
class TenantService:
    """
    The main business logic service for a tenant.
    This will be a unique instance for each tenant.
    """
    def __init__(self, db: TenantDatabase):
        self.db = db

    def do_work(self) -> str:
        return self.db.get_data()

# --- 2. Define the Tenant Manager (Singleton) ---

@component
class TenantManager:
    """
    A *global singleton* responsible for creating,
    caching, and retrieving the container for each tenant.
    """
    def __init__(self):
        # A cache of all running tenant containers
        self.tenant_containers: Dict[str, PicoContainer] = {}

    def get_container_for_tenant(self, tenant_id: str) -> PicoContainer:
        """
        Gets a tenant's container. If it doesn't exist,
        it creates and caches it.
        """
        if tenant_id not in self.tenant_containers:
            print(f"[TenantManager] Creating new container for {tenant_id}")
            
            # Look up the tenant's config (e.g., from a master DB)
            config = self._load_config_for_tenant(tenant_id)
            
            # Create a new, isolated container for this tenant
            tenant_container = init(
                modules=[__name__], # Scan this file for components
                profiles=(config.plan_type,), # e.g., "free" or "pro"
                container_id=f"tenant-{tenant_id}",
                overrides={
                    # **THE KEY**: We override TenantConfig
                    # with this tenant's specific instance.
                    TenantConfig: config
                }
            )
            self.tenant_containers[tenant_id] = tenant_container
        
        return self.tenant_containers[tenant_id]

    def _load_config_for_tenant(self, tenant_id: str) -> TenantConfig:
        """Mock: Loads config from a master database."""
        db_urls = {
            "tenant-1": "postgres://tenant1:pass@db/tenant1_db",
            "tenant-2": "postgres://tenant2:pass@db/tenant2_db",
        }
        if tenant_id not in db_urls:
            raise PicoError(f"Unknown tenant: {tenant_id}")
        
        return TenantConfig(
            tenant_id=tenant_id,
            database_url=db_urls[tenant_id],
            plan_type="pro" if tenant_id == "tenant-2" else "free"
        )
    
    @cleanup
    def shutdown_all_tenants(self):
        """On app shutdown, clean up all tenant containers."""
        print("[TenantManager] Shutting down all tenant containers...")
        for container in self.tenant_containers.values():
            container.shutdown()
        self.tenant_containers.clear()

# --- 3. Create the Global ("Root") Container ---

# The 'root_container' only holds global singletons,
# like the TenantManager itself.
root_container: PicoContainer | None = None

def get_tenant_manager() -> TenantManager:
    if not root_container:
        raise RuntimeError("Root container not initialized")
    return root_container.get(TenantManager)

# --- 4. FastAPI Setup ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    On app start, create the 'root_container'.
    On app end, shut down the 'root_container',
    which in turn shuts down all tenant containers.
    """
    global root_container
    root_container = init(
        modules=[__name__],
        container_id="root"
    )
    yield
    await root_container.cleanup_all_async()
    root_container.shutdown()

app = FastAPI(lifespan=lifespan)

@app.middleware("http")
async def tenant_context_middleware(request: Request, call_next):
    """
    The middleware that activates the correct
    container for the incoming request.
    """
    tenant_id = request.headers.get("X-Tenant-ID")
    if not tenant_id:
        return {"error": "X-Tenant-ID header is required"}, 400
    
    try:
        manager = get_tenant_manager()
        tenant_container = manager.get_container_for_tenant(tenant_id)
        
        # **THE KEY**: Activate this tenant's container
        # for the duration of this request.
        with tenant_container.as_current():
            response = await call_next(request)
            
        return response
    except Exception as e:
        return {"error": str(e)}, 500

# --- 5. The Application Route ---

def get_service(service_type: Type[T]) -> Callable[..., T]:
    """DI bridge to get a service from the *active* container."""
    async def _dependency() -> T:
        # PicoContainer.get_current() will return the
        # container activated by the middleware.
        container = PicoContainer.get_current()
        if not container:
            raise RuntimeError("No active PicoContainer context!")
        return await container.aget(service_type)
    return _dependency

@app.get("/work")
async def do_work(
    # This automatically injects the correct, isolated
    # TenantService for the user making the request.
    service: TenantService = Depends(get_service(TenantService))
):
    """
    Run work using the tenant's isolated service.
    """
    result = service.do_work()
    return {"data": result}

if __name__ == "__main__":
    print("--- To test, run the following ---")
    print('curl [http://127.0.0.1:8000/work](http://127.0.0.1:8000/work) -H "X-Tenant-ID: tenant-1"')
    print('curl [http://127.0.0.1:8000/work](http://127.0.0.1:8000/work) -H "X-Tenant-ID: tenant-2"')
    uvicorn.run(app, host="127.0.0.1", port=8000)
````

-----

## Next Steps

This pattern is extremely powerful for building secure, scalable, and isolated multi-tenant systems.

  * **[Pattern: Hot Reload (Dev Server)](./pattern-hot-reload.md)**: Learn another pattern that uses `container.shutdown()` and `init()` to automatically reload your application on code changes.

