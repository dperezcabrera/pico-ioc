## GUIDE: Creating Plugins and Interceptors

This guide provides an advanced example of how to extend `pico-ioc` using its powerful plugin and interceptor systems. We will build a complete **Feature Toggle** system from scratch.

A feature toggle allows you to enable or disable pieces of functionality at runtime without changing the code.

We will use two key `pico-ioc` extension points:

  * **Metadata Decorators**: To mark which parts of our code are controlled by a feature.
  * **Method Interceptors**: To apply the feature toggle logic to our components' methods.

-----

## Step 1: The Goal - Defining the User Experience

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

## Step 2: Core Logic - The Decorator and Registry

First, we define our custom decorator. In the interceptor pattern, the decorator's only job is to **attach metadata** to the function; it doesn't need to wrap the function itself.

```python
# pico_ioc_feature_toggle/decorators.py
import os
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

Next, we'll create a registry to manage the state of our feature toggles. By defining it as a `@component`, we allow `pico-ioc` to manage its lifecycle and inject it into our interceptor later. This is better than a manual singleton.

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

## Step 3: Integration - The `MethodInterceptor`

This is the most important part. We need to execute our toggle logic every time a decorated method is called. This is the perfect use case for a **`MethodInterceptor`**.

We mark our interceptor with `pico-ioc`'s `@interceptor` decorator. This tells the scanner to find it, build it, and register it **automatically**. Because both the interceptor and its dependency (`FeatureToggleRegistry`) are components, `pico-ioc` handles the dependency injection for us.

The interceptor inspects the original method for our metadata. If found, it checks the feature's status; otherwise, it simply proceeds with the original call.

```python
# pico_ioc_feature_toggle/interceptor.py
from typing import Any, Callable
from pico_ioc import interceptor
from pico_ioc.interceptors import MethodInterceptor, Invocation
from .decorators import FEATURE_TOGGLE_META, Mode
from .registry import FeatureToggleRegistry

@interceptor
class FeatureToggleInterceptor(MethodInterceptor):
    def __init__(self, registry: FeatureToggleRegistry):
        self.registry = registry

    def __call__(self, inv: Invocation, proceed: Callable[[], Any]) -> Any:
        # The real function is in inv.call
        toggle_meta = getattr(inv.call, FEATURE_TOGGLE_META, None)

        if not toggle_meta:
            return proceed() # Not a feature-toggled method, continue normally

        name = toggle_meta["name"]
        if self.registry.is_enabled(name):
            return proceed()
        
        # Feature is disabled, apply the specified mode
        mode = toggle_meta["mode"]
        if mode == Mode.EXCEPTION:
            raise RuntimeError(f"Feature '{name}' is disabled.")
        return None # Mode.PASS
```

-----

## Step 4: Final Assembly - Bootstrapping the Application

We have all the pieces. The `__init__.py` for our `pico_ioc_feature_toggle` library exports all the public symbols and `@component`-decorated classes so the scanner can find them.

```python
# pico_ioc_feature_toggle/__init__.py
from .decorators import feature_toggle, Mode
from .registry import FeatureToggleRegistry
from .interceptor import FeatureToggleInterceptor

__all__ = ["feature_toggle", "Mode", "FeatureToggleRegistry", "FeatureToggleInterceptor"]
```

Now, the application's entry point is much simpler. We no longer need to manually register the interceptor. We just need to tell `init()` where our new library is so it can be scanned.

**How to Run**:

1.  To see the success case (feature enabled):
    `$ python main.py`
    Output: `API call successful.`

2.  To see the failure case (feature disabled):
    `$ FT_DISABLED=new-api python main.py`
    Output: `Feature 'new-api' is disabled.`

<!-- end list -->

```python
# main.py
from pico_ioc import init
from demo_app.service import MyService

def main():
    # init() now scans both the main app and our feature toggle library.
    # The FeatureToggleInterceptor is found and activated automatically.
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

## When to Use a `PicoPlugin`?

In this guide, we used an **`Interceptor`** because we needed to act on **method calls** (Aspect-Oriented Programming). So when should you use a **`PicoPlugin`**?

Use a `PicoPlugin` when you need to hook into the **container's lifecycle events**, such as:

  * `before_scan`: Before `pico-ioc` starts looking for components.
  * `visit_class`: For every single class found during the scan. This is useful for custom component registration.
  * `after_bind`: After all providers have been registered but before eager instantiation.
  * `after_ready`: After the container is fully built.

By choosing the right tool—`Interceptor` for AOP and `Plugin` for lifecycle management—you can build powerful and clean extensions for `pico-ioc`.
