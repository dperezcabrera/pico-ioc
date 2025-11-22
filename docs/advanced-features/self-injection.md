# Self-injection of the Pico IoC container

This page introduces the self-injection feature: the ability for a component to receive the Pico IoC container itself as a dependency. It explains what the feature is, why it exists, and how to use it safely and effectively.

## What is self-injection?

Self-injection is a mechanism where the container binds itself into the dependency graph so it can be injected into components. If a component’s constructor has a parameter named `container` (or otherwise mapped by the binding rules), Pico injects the exact container instance that is building the component.

This is verified in tests by:
- Ensuring the container is injectable into a component (`test_container_is_injectable`).
- Ensuring the injected instance is the very same container performing the resolution (`test_injected_container_is_self`).

A minimal example component:

```python
class ServiceNeedsContainer:
    def __init__(self, container):
        self._container = container
```

When resolved, `self._container` will be the same object reference as the container that created the component.

## When should I use it?

Self-injection is an advanced feature. It is useful when a component must:
- Perform late-bound or dynamic lookups that cannot be expressed via static constructor injection.
- Act as a factory, composing different services based on runtime signals or configuration.
- Integrate with plugin systems where available implementations are discovered at runtime.

Prefer explicit dependency injection whenever possible. Self-injection couples your component to the container and can drift toward the Service Locator anti-pattern if overused. Use it sparingly and only at architectural boundaries where indirection is warranted.

## How to use self-injection

The container automatically makes itself available for injection. No special registration is required beyond creating and using the container normally.

### 1) Define a component that needs the container

Use a constructor parameter named `container` to receive the container instance:

```python
class ServiceNeedsContainer:
    def __init__(self, container):
        self._container = container

    def build_late_bound(self, cls, **overrides):
        # Example of a late-bound resolution using the container
        return self._container.resolve(cls, **overrides)
```

If your project uses type hints and your implementation supports type-based binding for the container, you can annotate the parameter with the container type. Name-based injection (parameter named `container`) is sufficient in many setups.

### 2) Create the container and resolve the component

Create a Pico container and resolve your component as usual. The container will inject itself into the `container` parameter.

```python
from pico import Container  # Example import; adjust to your package

container = Container()

# Register any other services your application needs...
# container.register(Greeter)
# container.register(SomeOtherService)

# Resolve the component that needs the container
service = container.resolve(ServiceNeedsContainer)

# Use the service; it can perform late-bound resolutions on demand
# greeter = service.build_late_bound(Greeter)
```

If your API differs (for example, using `get`, `build`, or `create` instead of `resolve`, or `add`/`bind` instead of `register`), adapt the calls accordingly. The key behavior is unchanged: the container injects itself.

### 3) Verify identity (optional, recommended in tests)

When unit testing, assert that the injected container is the same instance:

```python
def test_injected_container_is_self():
    container = Container()
    service = container.resolve(ServiceNeedsContainer)
    assert service._container is container  # Identity, not just equality
```

This mirrors the behavior validated by `test_injected_container_is_self`, confirming correct self-injection semantics.

## Design notes and caveats

- Identity guarantee: The injected container is the exact instance performing the resolution. In hierarchies (parent/child containers), the instance injected is the one that resolved the component.
- Scope and lifetime: The container is typically a root-scoped singleton in applications. Avoid storing the container in long-lived global state beyond the application scope.
- Avoid overuse: Prefer explicit constructor injection for stable dependencies. Self-injection is best reserved for dynamic composition, extensibility points, and boundary-layer orchestration.
- Testability: Components that rely on the container are harder to unit test in isolation. Consider injecting lightweight factory interfaces or callables as alternatives when feasible.

By following these practices, you can leverage self-injection for advanced composition scenarios without sacrificing clarity and maintainability.