# Cookbook: Pattern: Feature Toggles with AOP

**Goal:** Implement a "Feature Toggle" or "Feature Flag" system. This allows enabling or disabling specific functionality (methods) at runtime (e.g., via environment variables) without changing the code or redeploying.

**Key `pico-ioc` Feature:** **Aspect-Oriented Programming (AOP)** using `MethodInterceptor` and `@intercepted_by`. We'll create a custom decorator (`@feature_toggle`) to mark methods and an interceptor that checks if the feature is enabled before allowing the method call to proceed.

---

## The Pattern

1.  **Metadata Decorator (`@feature_toggle`):** A simple decorator that attaches metadata (the feature name and behavior-on-disable) to a function. It does *not* wrap the function directly.
2.  **Toggle Registry (`FeatureToggleRegistry`):** A `@component` that knows the current state (enabled/disabled) of all features, typically by reading environment variables or a configuration source.
3.  **Interceptor (`FeatureToggleInterceptor`):** A `@component` implementing `MethodInterceptor`. Its `invoke` method:
    * Checks if the called method has `@feature_toggle` metadata.
    * If yes, asks the `FeatureToggleRegistry` if the feature is enabled.
    * If enabled, calls `call_next(ctx)` to proceed with the original method.
    * If disabled, takes action based on the metadata (e.g., raises an exception or returns `None`).
4.  **Application:** Components apply the `@feature_toggle` decorator to methods and the `@intercepted_by(FeatureToggleInterceptor)` decorator *once* (usually on the class or methods needing toggles) to activate the interception.
5.  **Bootstrap:** `init()` scans modules containing the components, registry, interceptor, and decorator.

---

## Full, Runnable Example

### 1. Project Structure

```

.
├── feature\_toggle\_lib/
│   ├── **init**.py
│   ├── decorator.py   \<-- @feature\_toggle and Mode
│   ├── interceptor.py \<-- FeatureToggleInterceptor
│   └── registry.py    \<-- FeatureToggleRegistry
├── my\_app/
│   ├── **init**.py
│   └── services.py    \<-- Example service using the toggle
└── main.py              \<-- Application entrypoint

```

### 2. Feature Toggle Library (`feature_toggle_lib/`)

#### Decorator (`decorator.py`)

```python
# feature_toggle_lib/decorator.py
import functools
from enum import Enum
from typing import Callable

# Metadata key
FEATURE_TOGGLE_META = "_pico_feature_toggle_meta"

class Mode(str, Enum):
    """Behavior when the feature is disabled."""
    EXCEPTION = "exception" # Raise RuntimeError
    RETURN_NONE = "return_none" # Return None silently

def feature_toggle(*, name: str, mode: Mode = Mode.RETURN_NONE):
    """Decorator to mark a method as controlled by a feature toggle."""
    def decorator(func: Callable) -> Callable:
        metadata = {"name": name, "mode": mode}
        setattr(func, FEATURE_TOGGLE_META, metadata)
        
        # We need functools.wraps to preserve metadata for pico-ioc AOP
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # This wrapper isn't strictly needed for pico-ioc AOP,
            # but is good practice if the decorator might be used alone.
            # The interceptor will re-check the logic.
            return func(*args, **kwargs)
        
        # Ensure metadata is on the wrapper too if needed
        setattr(wrapper, FEATURE_TOGGLE_META, metadata)
        return wrapper
    return decorator
```

#### Registry (`registry.py`)

```python
# feature_toggle_lib/registry.py
import os
from pico_ioc import component

@component # <-- The registry is a component
class FeatureToggleRegistry:
    """Checks if features are enabled, typically via environment variables."""
    def __init__(self):
        # Read a comma-separated list of DISABLED features
        disabled_str = os.environ.get("PICO_FEATURES_DISABLED", "")
        self._disabled_set = {
            feature.strip().lower() 
            for feature in disabled_str.split(",") 
            if feature.strip()
        }
        print(f"[Registry] Disabled features: {self._disabled_set}")

    def is_enabled(self, feature_name: str) -> bool:
        """Check if a feature toggle is currently enabled."""
        return feature_name.lower() not in self._disabled_set
```

#### Interceptor (`interceptor.py`)

```python
# feature_toggle_lib/interceptor.py
from typing import Any, Callable
from pico_ioc import component, MethodInterceptor, MethodCtx
from .registry import FeatureToggleRegistry
from .decorator import FEATURE_TOGGLE_META, Mode

@component # <-- The interceptor is also a component
class FeatureToggleInterceptor(MethodInterceptor):
    def __init__(self, registry: FeatureToggleRegistry):
        # Inject the registry
        self.registry = registry
        print("[Interceptor] FeatureToggleInterceptor initialized.")

    def invoke(self, ctx: MethodCtx, call_next: Callable[[MethodCtx], Any]) -> Any:
        # Check the *original* method for metadata
        # ctx.method might be already wrapped by other interceptors
        try:
            # Access the unbound function via the class to read decorators reliably
            original_func = getattr(ctx.cls, ctx.name)
            toggle_meta = getattr(original_func, FEATURE_TOGGLE_META, None)
        except AttributeError:
            toggle_meta = None # Method not found on class (unlikely case)

        if not toggle_meta:
            # This method isn't feature-toggled, proceed normally
            return call_next(ctx)

        feature_name = toggle_meta["name"]
        
        if self.registry.is_enabled(feature_name):
            # Feature is ON, proceed with the original call
            print(f"[Interceptor] Feature '{feature_name}' is ENABLED. Proceeding.")
            return call_next(ctx)
        else:
            # Feature is OFF, apply the disabled behavior
            print(f"[Interceptor] Feature '{feature_name}' is DISABLED. Blocking.")
            mode = toggle_meta["mode"]
            if mode == Mode.EXCEPTION:
                raise RuntimeError(f"Feature '{feature_name}' is currently disabled.")
            else: # Mode.RETURN_NONE
                return None
```

#### Library `__init__.py`

```python
# feature_toggle_lib/__init__.py
from .decorator import feature_toggle, Mode
from .registry import FeatureToggleRegistry
from .interceptor import FeatureToggleInterceptor

__all__ = [
    "feature_toggle", "Mode", 
    "FeatureToggleRegistry", "FeatureToggleInterceptor"
]
```

### 3\. Application Code (`my_app/services.py`)

Here's how you use the library in your application.

```python
# my_app/services.py
from pico_ioc import component, intercepted_by
from feature_toggle_lib import (
    feature_toggle, Mode, FeatureToggleInterceptor
)

@component
class MyService:
    
    # Apply the toggle decorator AND the interceptor
    @feature_toggle(name="new-reporting", mode=Mode.EXCEPTION)
    @intercepted_by(FeatureToggleInterceptor) 
    def generate_report(self, user_id: int) -> dict:
        print("[MyService] Generating complex new report...")
        # ... actual reporting logic ...
        return {"report_id": 123, "user": user_id}

    # Apply toggle with different mode
    @feature_toggle(name="experimental-feature", mode=Mode.RETURN_NONE)
    @intercepted_by(FeatureToggleInterceptor)
    def try_experimental(self) -> str | None:
        print("[MyService] Trying experimental feature...")
        return "Experimental Success!"

    # This method is not toggled and not intercepted
    def always_available(self) -> str:
        print("[MyService] Running essential function.")
        return "Always OK"

# Note: You could apply @intercepted_by at the class level
# if all methods should potentially be checked by the interceptor.
# @component
# @intercepted_by(FeatureToggleInterceptor)
# class MyService:
#     @feature_toggle(...)
#     def method1(...): ...
#     def method2(...): ... # Interceptor runs, finds no metadata, proceeds
```

### 4\. Main Application (`main.py`)

Initialize the container, ensuring it scans both your app and the library.

```python
# main.py
import os
from pico_ioc import init
from my_app.services import MyService

def run_app():
    print("--- Initializing Container ---")
    # Scan both the app and the feature toggle library
    container = init(modules=["my_app", "feature_toggle_lib"])
    print("--- Container Initialized ---\n")

    service = container.get(MyService)

    # --- Test Cases ---
    print("--- Testing 'always_available' ---")
    print(f"Result: {service.always_available()}\n")
    
    print("--- Testing 'generate_report' (new-reporting feature) ---")
    try:
        report = service.generate_report(user_id=42)
        print(f"Result: {report}\n")
    except Exception as e:
        print(f"Caught Exception: {e}\n")

    print("--- Testing 'try_experimental' (experimental-feature) ---")
    exp_result = service.try_experimental()
    print(f"Result: {exp_result}\n")


if __name__ == "__main__":
    print("="*30)
    print("RUN 1: ALL FEATURES ENABLED")
    print("="*30)
    # Ensure no features are disabled
    os.environ.pop("PICO_FEATURES_DISABLED", None) 
    run_app()

    print("\n" + "="*30)
    print("RUN 2: 'new-reporting' FEATURE DISABLED")
    print("="*30)
    # Disable one feature via environment variable
    os.environ["PICO_FEATURES_DISABLED"] = "new-reporting"
    run_app()
    
    print("\n" + "="*30)
    print("RUN 3: BOTH FEATURES DISABLED")
    print("="*30)
    # Disable multiple features
    os.environ["PICO_FEATURES_DISABLED"] = "new-reporting,experimental-feature"
    run_app()
```

-----

## 5\. Benefits

  * **Clean Business Logic:** Your `MyService` methods contain only business logic, completely unaware of the toggle mechanism.
  * **Centralized Control:** The enable/disable logic is centralized in `FeatureToggleRegistry`.
  * **Reusable:** The `FeatureToggleInterceptor` can be applied to any method in any component.
  * **Declarative:** Features are clearly marked with `@feature_toggle`.
  * **Testable:** `FeatureToggleRegistry` and `FeatureToggleInterceptor` can be unit-tested. Services can be tested by overriding the registry or simply testing without the interceptor active.

This pattern demonstrates how `pico-ioc`'s AOP allows you to cleanly implement sophisticated cross-cutting concerns like feature toggles.

