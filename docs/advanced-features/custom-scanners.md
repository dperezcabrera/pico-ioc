# Advanced: Custom Component Scanners 🔎

The core `pico-ioc` scanner automatically discovers components marked with decorators like `@component`, `@factory`, `@provides`, and `@configured`.

However, for advanced integrations or custom frameworks built on top of `pico-ioc`, you may need to register components based on your own custom decorators or base classes. This is where the `CustomScanner` protocol comes in.

## 1. The CustomScanner Protocol

You implement the `CustomScanner` protocol and pass an instance to `init(custom_scanners=[...])`. The scanner is responsible for deciding if an object should be registered and providing the necessary metadata for the registration.

The protocol defines two methods:
1. `should_scan(obj: Any) -> bool`: Quick filter to check if the object is relevant to this scanner.
2. `scan(obj: Any) -> Optional[Tuple[KeyT, Provider, ProviderMetadata]]`: Detailed logic to build the component's provider and metadata.

!!! tip "Scanning Functions"
    Unlike the built-in scanner which looks primarily for classes, your `CustomScanner` receives **every** member of the module (classes, functions, and objects). This allows you to create decorators for standalone functions (e.g., `@task`, `@job`) and register them as components.

## 2. Step-by-Step Example: Custom Decorator

Let's create a custom decorator `@domain_model` that should register a class as a `prototype` component.

### Step 1: Define the Custom Decorator

The decorator only needs to attach a marker attribute, similar to `pico-ioc`'s internal markers.

```python
# custom_domain_lib/decorators.py
from typing import Callable, Any

CUSTOM_DOMAIN_MARKER = "_custom_domain_marker"

def domain_model(cls: type) -> type:
    """Marks a class as a domain component."""
    setattr(cls, CUSTOM_DOMAIN_MARKER, True)
    return cls
```

### Step 2: Implement the CustomScanner

The scanner checks for the marker and constructs a `DeferredProvider` and `ProviderMetadata`.

```python
# custom_domain_lib/scanner.py
import inspect
from typing import Any, Optional, Tuple
from pico_ioc import (
    CustomScanner, DeferredProvider, ProviderMetadata, analyze_callable_dependencies
)
from .decorators import CUSTOM_DOMAIN_MARKER

class DomainScanner(CustomScanner):
    def should_scan(self, obj: Any) -> bool:
        # Only interested in classes decorated with our marker
        return inspect.isclass(obj) and getattr(obj, CUSTOM_DOMAIN_MARKER, False)

    def scan(self, cls: type) -> Optional[Tuple[type, DeferredProvider, ProviderMetadata]]:
        # 1. Determine the component's dependencies (from __init__)
        deps = analyze_callable_dependencies(cls.__init__)
        
        # 2. Define the Provider
        # The builder function uses pico.build_class to create the instance
        provider = DeferredProvider(
            lambda pico, loc, c=cls, d=deps: pico.build_class(c, loc, d)
        )
        
        # 3. Define the Metadata
        metadata = ProviderMetadata(
            key=cls,
            provided_type=cls,
            concrete_class=cls,
            factory_class=None,
            factory_method=None,
            qualifiers=set(),
            primary=False,
            lazy=False,
            infra="custom-domain",
            pico_name=getattr(cls, "__name__", None),
            scope="prototype", # Force prototype scope for domain models
            dependencies=deps
        )

        # 4. Return the registration tuple
        return cls, provider, metadata
```

### Step 3: Apply and Run

The application code uses the custom decorator, and the main entry point passes an instance of the scanner to `init()`.

```python
# my_app/models.py
from custom_domain_lib.decorators import domain_model

# Assume another service exists
class UserService:
    pass

@domain_model # <-- The custom decorator
class UserEntity:
    def __init__(self, user_service: UserService):
        self.user_service = user_service
        print("UserEntity CREATED via DomainScanner!")

# main.py
from pico_ioc import init
from custom_domain_lib.scanner import DomainScanner
from my_app.models import UserEntity

# 1. Instantiate the custom scanner
domain_scanner = DomainScanner()

# 2. Initialize the container
container = init(
    modules=["my_app.models"],
    custom_scanners=[domain_scanner] # <-- Register the scanner
)

# 3. Resolve the custom component
user_entity_instance = container.get(UserEntity)

# Output:
# UserEntity CREATED via DomainScanner!
# ... dependencies (UserService) are also injected.
```

## 3\. Considerations and Best Practices

  - Order of execution: Custom scanners run *before* the built-in scanner. If a custom scanner registers a component for a key (e.g., `UserEntity`), the built-in scanner might be skipped for that key if precedence rules apply (e.g., if the built-in scanner had an `@component(on_missing_selector=UserEntity)`).
  - `ProviderMetadata`: Carefully populate this dataclass, especially `key`, `provided_type`, `concrete_class`, `infra` (e.g., `"custom-domain"`), and `scope`.
  - `DeferredProvider`: Always use `DeferredProvider` in `scan` so that dependency resolution (which requires a fully configured container/locator) is deferred until `container.get` is called.

<!-- end list -->

