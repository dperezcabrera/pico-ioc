## GUIDE: Creating Infrastructure and Interceptors

This guide provides an advanced example of how to extend `pico-ioc` using its powerful **infrastructure and interceptor** system. We will build a complete **Feature Toggle** system from scratch.

A feature toggle allows you to enable or disable pieces of functionality at runtime without changing the code.

We will use two key `pico-ioc` extension points:

  * **Metadata Decorators**: To mark which parts of our code are controlled by a feature.
  * **Infrastructure and Method Interceptors**: To query the container and apply the feature toggle logic to our components' methods.

-----

### Step 1: The Goal - Defining the User Experience

First, let's define what we want to achieve. We want a simple decorator, `@feature_toggle`, that we can apply to any method within a `@component`.

Here is the target client code we want to write:

```python
from pico_ioc import component
from pico_ioc_feature_toggle import feature_toggle, Mode

@component
class MyService:
    @feature_toggle(name="new-api", mode=Mode.EXCEPTION)
    def call_api(self) -> str:
        return "API call successful."
```

-----

### Step 2: Core Logic - The Decorator and Registry

First, we define our custom decorator. Its only job is to **attach metadata** to the function; it doesn't need to wrap the function itself.

```python
# pico_ioc_feature_toggle/decorators.py
from enum import Enum
from typing import Callable

# A unique key to store metadata on the function
FEATURE_TOGGLE_META = "_pico_feature_toggle_meta"

class Mode(str, Enum):
    EXCEPTION = "exception"
    PASS = "pass" # Returns None when disabled

def feature_toggle(*, name: str, mode: Mode = Mode.PASS):
    def decorator(fn: Callable) -> Callable:
        setattr(fn, FEATURE_TOGGLE_META, {"name": name, "mode": mode})
        return fn
    return decorator
```

Next, we'll create a registry to manage the state of our feature toggles. By defining it as a `@component`, we allow `pico-ioc` to manage its lifecycle and inject it later.

```python
# pico_ioc_feature_toggle/registry.py
import os
from pico_ioc import component

@component
class FeatureToggleRegistry:
    def __init__(self):
        disabled = os.getenv("FT_DISABLED", "")
        self._disabled_features = {
            feat.strip() for feat in disabled.split(",") if feat.strip()
        }

    def is_enabled(self, name: str) -> bool:
        return name not in self._disabled_features
```

-----

### Step 3: Integration - The `MethodInterceptor` and the Infrastructure Class

This is the most important part. We will use the new "around-style" `MethodInterceptor` to execute our logic whenever a decorated method is called.

**1. The Interceptor (The Logic)**

The interceptor is a plain Python class implementing the `MethodInterceptor` protocol. Its `invoke` method receives the call context (`MethodCtx`) and a `call_next` function to proceed with the execution chain.

```python
# pico_ioc_feature_toggle/interceptor.py
from typing import Any, Callable
from pico_ioc.interceptors import MethodInterceptor, MethodCtx
from .decorators import FEATURE_TOGGLE_META, Mode
from .registry import FeatureToggleRegistry

class FeatureToggleInterceptor(MethodInterceptor):
    def __init__(self, registry: FeatureToggleRegistry):
        self.registry = registry

    def invoke(self, ctx: MethodCtx, call_next: Callable[[MethodCtx], Any]) -> Any:
        # Get the original unbound function from the class to access the decorator's metadata
        original_method = getattr(ctx.cls, ctx.name, None)
        toggle_meta = getattr(original_method, FEATURE_TOGGLE_META, None)

        if not toggle_meta:
            return call_next(ctx) # Not a feature-toggled method, continue normally

        name = toggle_meta["name"]
        if self.registry.is_enabled(name):
            return call_next(ctx)
        
        # Feature is disabled, apply the specified mode
        mode = toggle_meta["mode"]
        if mode == Mode.EXCEPTION:
            raise RuntimeError(f"Feature '{name}' is disabled.")
        return None # Mode.PASS
```

**2. The Infrastructure (The Registration and Policy)**

The `@infrastructure` class is the entrypoint for configuration. `pico-ioc` discovers it, injects its dependencies (like our `FeatureToggleRegistry`), and executes its `configure` method. This is where we register our interceptor and define **where** it applies.

```python
# pico_ioc_feature_toggle/infra.py
from pico_ioc import infrastructure
from pico_ioc.infra import Infra, Select
from .registry import FeatureToggleRegistry
from .interceptor import FeatureToggleInterceptor

@infrastructure(order=100)
class FeatureToggleInfrastructure:
    # pico-ioc will inject the toggle registry here
    def __init__(self, registry: FeatureToggleRegistry):
        self.registry = registry

    def configure(self, infra: Infra) -> None:
        # 1. Create an instance of our interceptor
        interceptor_instance = FeatureToggleInterceptor(self.registry)
        
        # 2. Define the policy: where should this interceptor apply?
        #    We want it to apply to all components. To do this safely, we
        #    use an explicit selector instead of an empty one.
        #    The interceptor's internal logic will then check for the decorator.
        selector = Select().class_name(".*") # Select all classes

        # 3. Use the infra API to add the interceptor with its policy.
        infra.intercept.add(
            interceptor=interceptor_instance,
            where=selector
        )
```

-----

### Step 4: Final Assembly - Bootstrapping the Application

We have all the pieces. The `__init__.py` for our library exports all public symbols so the scanner can find them.

```python
# pico_ioc_feature_toggle/__init__.py
from .decorators import feature_toggle, Mode
from .registry import FeatureToggleRegistry
from .interceptor import FeatureToggleInterceptor
from .infra import FeatureToggleInfrastructure

__all__ = ["feature_toggle", "Mode", "FeatureToggleRegistry", "FeatureToggleInterceptor", "FeatureToggleInfrastructure"]
```

Now, the application's entry point is simple. We just need to tell `init()` where our new library is so it can be scanned. The scanner will find the `@infrastructure` class and activate it automatically.

**How to Run**:

1.  To see the success case (feature enabled):

    ```bash
    $ python main.py
    ```

    Output: `API call successful.`

2.  To see the failure case (feature disabled):

    ```bash
    $ FT_DISABLED=new-api python main.py
    ```

    Output: `Feature 'new-api' is disabled.`

<!-- end list -->

```python
# main.py
from pico_ioc import init
# Assuming MyService is in demo_app/service.py
from demo_app.service import MyService

def main():
    # init() now scans both the main app and our feature toggle library.
    # The FeatureToggleInfrastructure class is found and registered.
    container = init("demo_app", auto_scan=["pico_ioc_feature_toggle"])
    
    service = container.get(MyService)
    
    try:
        result = service.call_api()
        if result is not None:
            print(result)
    except RuntimeError as e:
        print(e)

if __name__ == "__main__":
    main()
```

-----

### When to Use a `PicoPlugin`?

In this guide, we used a combination of **`@infrastructure` and an `Interceptor`** because we needed to act on **method calls** (Aspect-Oriented Programming). So when should you use a **`PicoPlugin`**?

Use a `PicoPlugin` when you need to hook into the **container's lifecycle events**, such as:

  * `before_scan`: Before `pico-ioc` starts looking for components.
  * `visit_class`: For every single class found during the scan. This is useful for custom component registration.
  * `after_bind`: After all providers have been registered but before eager instantiation.
  * `after_ready`: After the container is fully built.

By choosing the right tool—`Interceptor` for AOP, `Infrastructure` for configuration and policies, and `Plugin` for lifecycle management—you can build powerful and clean extensions for `pico-ioc`.
