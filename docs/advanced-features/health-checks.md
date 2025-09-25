# Advanced: Health Checks

In modern, containerized environments like Kubernetes, your application must report its health. An orchestrator needs to know: "Is this application healthy and ready to receive traffic?"

This usually means exposing a `/health` or `/live` endpoint that checks the status of all critical downstream dependencies.

**Problem:** You have health-check logic scattered everywhere.
* `DatabaseService` has a `.ping()` method.
* `RedisService` has a `.ping()` method.
* `ExternalApiService` has a `.check_status()` method.

You don't want your web framework's `/health` endpoint to have to manually get *every one* of these services and call *every one* of these methods.

**Solution:** `pico-ioc` provides a `@health` decorator. You use it to "tag" any method on any component as a health check. Then, you can simply call `container.health_check()` to run **all** registered checks and get a clean, aggregated report.

---

## 1. The `@health` Decorator

You can apply `@health` to any component method that:
1.  Takes no arguments (other than `self`).
2.  Returns a `bool` (or any truthy/falsy value) to indicate success.
3.  **OR** raises an exception to indicate failure.

`pico-ioc` will automatically consider any exception as a `False` (unhealthy) status.

---

## 2. Step-by-Step Example

Let's define several components, each with its own health check.

### Step 1: Tag Your Health Check Methods

```python
# services.py
from pico_ioc import component, health

@component
class Database:
    def connect(self): ...
    
    @health
    def check_connection(self):
        """
        This method will be run by the health check system.
        """
        print("Checking database connection...")
        try:
            self.ping_db() # This might raise an exception
            return True
        except Exception:
            return False
            
    def ping_db(self):
        # A mock function that succeeds
        pass

@component
class ExternalApiService:
    def __init__(self):
        self.api_is_down = True # Mock failure

    @health
    def check_api_status(self):
        """
        This method will also be run.
        """
        print("Checking external API status...")
        if self.api_is_down:
            # Raising an exception is a valid way to fail a health check
            raise ConnectionError("API is not reachable")
        return True

@component
class UnrelatedService:
    def do_work(self):
        # This method is NOT a health check and will be ignored
        pass
````

### Step 2: Call `container.health_check()`

Now, in your main application (e.g., in your `/health` endpoint), you just get the container and call the `health_check()` method.

This method finds all instantiated components, scans them for `@health` methods, executes all of them, and returns a simple dictionary of the results.

```python
# main.py
from pico_ioc import init
from services import Database, ExternalApiService, UnrelatedService

# Initialize the container. This creates the singletons.
container = init(modules=["services"])

# Pre-load services to ensure they are in the cache to be checked
# (In a real app, these would be loaded by other services)
container.get(Database)
container.get(ExternalApiService)

# ... In your web framework's /health endpoint ...
def health_endpoint():
    print("Running global health check...")
    
    # This is the only line you need
    health_status = container.health_check()
    
    # health_status is a simple dictionary
    print(health_status)
    
    # You can return it directly as JSON
    return health_status

health_endpoint()

# Output:
# Checking database connection...
# Checking external API status...
# Running global health check...
# {
#   'Database.check_connection': True, 
#   'ExternalApiService.check_api_status': False
# }
```

The keys in the report are automatically generated as `'ClassName.method_name'`.

-----

## Next Steps

You have now completed the User Guide and the Advanced Features sections. You have all the tools to build, configure, test, and monitor a production-grade application.

The next section, **Observability**, dives deeper into monitoring and debugging the container itself.

  * **[Observability Overview](./observability/README.md)**: Learn how to trace component resolution, get container-level stats, and export your dependency graph.

