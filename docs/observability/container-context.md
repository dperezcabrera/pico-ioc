# Observability: Container Context

The "Container Context" is a fundamental `pico-ioc` feature that allows you to manage multiple containers within a single process and track which one is "active" at any given moment.

Every container you create with `init()` receives a unique **`container_id`** (e.g., `c67f8...`). `pico-ioc` maintains a global registry of all running containers.

This system is the foundation for:
* **Observability & Tracing:** Tagging logs and metrics with the `container_id` to know *which* container is doing *what*.
* **Multi-Tenant Applications:** Creating an isolated container for each tenant and activating the correct one for each incoming request.
* **Hot-Reloading:** Shutting down (`shutdown`) an old container and putting a new one in its place without restarting the process.

The four key APIs for managing context are:
* `container.activate()` / `with container.as_current()`: Activates a container.
* `PicoContainer.get_current()`: Gets the active container.
* `container.shutdown()`: Deactivates and destroys a container.
* `PicoContainer.all_containers()`: Lists all active containers.

---

## 1. Activating a Container: `as_current()`

By default, a container is **not** globally active. If you need code in other parts of your application (which don't have a direct reference to the `container`) to be able to find the container, you must activate it.

The easiest and safest way to do this is with the `with container.as_current()` context manager.

This manager uses `contextvars` to make the container "active" only within that block, in a thread-safe and `asyncio` task-safe manner.

```python
from pico_ioc import init, PicoContainer

container = init(...)
print(f"Container created with ID: {container.container_id}")

# Outside the block, no container is active
assert PicoContainer.get_current() is None

# Inside this block, 'container' is the active one
with container.as_current():
    # Now, code anywhere can find it
    current_c = PicoContainer.get_current()
    assert current_c is container
    print(f"Active container: {current_c.container_id}")

# After exiting the block, the context is restored
assert PicoContainer.get_current() is None

# --- Output ---
# Container created with ID: c67f8...
# Active container: c67f8...
````

-----

## 2\. Managing Multiple Containers

This is where context shines. You can have multiple containers and switch between them. This is essential for multi-tenant patterns, where each tenant has its own configuration and isolated set of services.

```python
from pico_ioc import init, PicoContainer, component

# --- Component Definitions ---
class Config:
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id

@component
class TenantService:
    def __init__(self, config: Config):
        self.config = config
    
    def who_am_i(self):
        print(f"I am the service for {self.config.tenant_id}")

# --- Container Creation ---
# Create an isolated container for Tenant 1
container_tenant_1 = init(
    modules=[__name__],
    overrides={Config: Config(tenant_id="Tenant-1")}
)

# Create another isolated container for Tenant 2
container_tenant_2 = init(
    modules=[__name__],
    overrides={Config: Config(tenant_id="Tenant-2")}
)

# --- Simulating Requests ---
print("--- Request for Tenant 1 ---")
with container_tenant_1.as_current():
    service1 = PicoContainer.get_current().get(TenantService)
    service1.who_am_i()

print("--- Request for Tenant 2 ---")
with container_tenant_2.as_current():
    service2 = PicoContainer.get_current().get(TenantService)
    service2.who_am_i()

# --- Output ---
# --- Request for Tenant 1 ---
# I am the service for Tenant-1
# --- Request for Tenant 2 ---
# I am the service for Tenant-2
```

`PicoContainer.get_current()` always returns the correct container for the current context.

-----

## 3\. Shutdown and Cleanup: `container.shutdown()`

When you no longer need a container (e.g., the tenant logs off, or you are doing a hot-reload), you **must** call `container.shutdown()`.

This function does two things:

1.  It calls `container.cleanup_all()` to execute all `@cleanup` methods on your components (closing database connections, files, etc.).
2.  It **removes the container from the global registry.**

<!-- end list -->

```python
# Get all active containers
all_c = PicoContainer.all_containers()
print(f"Active containers: {list(all_c.keys())}")
# Output: Active containers: ['c67f8...', 'c67f9...'] (IDs for Tenant 1 and 2)

# Shut down the Tenant 1 container
container_tenant_1.shutdown()

all_c = PicoContainer.all_containers()
print(f"Active containers now: {list(all_c.keys())}")
# Output: Active containers now: ['c67f9...']
```

Calling `shutdown()` is crucial for preventing memory leaks if you are dynamically creating and destroying containers.

-----

## Next Steps

Now that you understand how to manage a container's lifecycle and context, the next step is to monitor what's happening *inside* it.

  * **[Observers & Metrics (`stats`)](./observers-metrics.md)**: Learn how to get performance metrics from the container and create your own tracing observers.

