# `GUIDE_CREATING_PLUGINS_AND_INTERCEPTORS.md`

This guide provides an advanced example of how to extend `pico-ioc` using its powerful plugin and interceptor systems. We will build a complete **Feature Toggle** system from scratch.

A feature toggle allows you to enable or disable pieces of functionality at runtime, typically using an environment variable, without changing the code.

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

Before integrating with `pico-ioc`, we need to define our core logic. This part of the code is framework-agnostic.

First, we define an `Enum` for the toggle's behavior and the decorator itself. In the interceptor pattern, the decorator's only job is to attach metadata to the function; it doesn't need to wrap the function itself.

```python
import os
from enum import Enum
from typing import Callable

class Mode(str, Enum):
    EXCEPTION = "exception"
    PASS = "pass"

def feature_toggle(*, name: str, mode: Mode = Mode.PASS):
    def decorator(fn: Callable) -> Callable:
        fn._pico_feature_toggle = {
            "name": name,
            "mode": mode,
        }
        return fn
    return decorator
```

Next, we create a registry. This will be a simple singleton that reads an environment variable (`FT_DISABLED`) at startup to determine the state of all features. A feature is enabled by default unless explicitly listed as disabled.

```python
class FeatureToggleRegistry:
    _inst: "FeatureToggleRegistry" | None = None

    def __init__(self):
        disabled = os.getenv("FT_DISABLED", "")
        self._features: dict[str, bool] = {
            feat.strip(): False
            for feat in disabled.split(",")
            if feat.strip()
        }

    @classmethod
    def instance(cls) -> "FeatureToggleRegistry":
        if cls._inst is None:
            cls._inst = FeatureToggleRegistry()
        return cls._inst

    def is_enabled(self, name: str) -> bool:
        return self._features.get(name, True)
```

-----

## Step 3: Integration - The `MethodInterceptor`

Now for the most important part: integrating with `pico-ioc`. We want to execute our toggle logic every time a decorated method is called. This is the perfect use case for a **`MethodInterceptor`**. An interceptor wraps method calls for all components, allowing us to run code before and after the original method.

Our interceptor will get an instance of the registry. In its `__call__` method, it inspects the original method (`inv.call`) for our `_pico_feature_toggle` metadata. If found, it checks the feature's status and acts accordingly; otherwise, it proceeds with the original call.

```python
from typing import Any
from pico_ioc.interceptors import MethodInterceptor, Invocation

class FeatureToggleInterceptor(MethodInterceptor):
    def __init__(self):
        self.registry = FeatureToggleRegistry.instance()

    def __call__(self, inv: Invocation, proceed: Callable[[], Any]) -> Any:
        toggle_meta = getattr(inv.call, "_pico_feature_toggle", None)

        if not toggle_meta:
            return proceed()

        name = toggle_meta["name"]
        mode = toggle_meta["mode"]

        if self.registry.is_enabled(name):
            return proceed()
        else:
            if mode == Mode.EXCEPTION:
                raise RuntimeError(f"Feature '{name}' is disabled.")
            return None
```

-----

## Step 4: Final Assembly - Bootstrapping the Application

We have all the pieces. The `__init__.py` for our library exports all the public symbols.

```python
from .feature_toggle import feature_toggle, FeatureToggleInterceptor, Mode, FeatureToggleRegistry

__all__ = ["feature_toggle", "FeatureToggleInterceptor", "Mode", "FeatureToggleRegistry"]
```

And finally, the application's entry point registers the interceptor during initialization. This tells `pico-ioc` to apply our feature toggle logic to all component methods.

**HOW TO RUN:**

1.  To see the success case (feature enabled):
    `$ python main.py`
    Output: `API call successful.`
2.  To see the failure case (feature disabled):
    `$ FT_DISABLED=new-api python main.py`
    Output: `RuntimeError: Feature 'new-api' is disabled.`

<!-- end list -->

```python
import sys
from pico_ioc import init
from demo_app.service import MyService
from pico_ioc_feature_toggle import FeatureToggleInterceptor

def main():
    container = init(
        sys.modules[__name__],
        method_interceptors=[FeatureToggleInterceptor()]
    )
    service = container.get(MyService)
    
    try:
        result = service.call_api()
        print(result)
    except RuntimeError as e:
        print(e)


if __name__ == "__main__":
    main()
```

-----

## When to Use a `PicoPlugin`?

In this guide, we used an **`Interceptor`** because we needed to act on **method calls**. So when should you use a **`PicoPlugin`**?

Use a `PicoPlugin` when you need to hook into the **container's lifecycle events**, such as:

  * `before_scan`: Before `pico-ioc` starts looking for components.
  * `visit_class`: For every single class found during the scan.
  * `after_bind`: After all providers have been registered but before eager instantiation.
  * `after_ready`: After the container is fully built and all eager components are created.

By choosing the right tool—`Interceptor` for AOP and `Plugin` for lifecycle—you can build powerful and clean extensions for `pico-ioc`.
