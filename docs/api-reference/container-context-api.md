# Container Context API

The Container Context API provides runtime context management and lifecycle utilities for PicoContainer instances. It ensures each container has a unique identifier, supports activation and deactivation, exposes a context-manager for setting a “current” container, maintains a global registry of all containers, and reports useful statistics such as container ID, profiles, and resolution metrics.

## What is this?

- Context management: Temporarily mark a container as the current context using a context manager.
- Lifecycle control: Explicitly activate and deactivate containers to manage their usage window.
- Identity and registry: Each container gets a unique container ID and is tracked in a global registry.
- Statistics: Inspect runtime stats about a container, including its ID, profiles, and resolution-related metrics.

These capabilities make it easier to coordinate dependency resolution across different parts of your application, especially when multiple containers or profiles are involved.

## Key features

- Unique container IDs to distinguish instances.
- `activate()` and `deactivate()` lifecycle methods.
- `as_current()` context manager to set the current container within a scope.
- A registry that lists all instantiated containers.
- `stats()` reporting container metadata and resolution metrics.

## Getting started

Create a container and check its unique ID.

```python
from pico import PicoContainer

# Create a new container (optionally with profiles)
container = PicoContainer(profiles=['dev'])  # profiles are optional

# Each container has a unique ID
print(container.container_id)  # e.g., 'c-7f3a2b1e'
```

## Managing lifecycle: activate and deactivate

Use `activate()` to mark the container as active. Call `deactivate()` when done to cleanly release the context.

```python
container.activate()

# Use the container while active...
service = container.resolve('my_service')

# When finished, deactivate to clean up
container.deactivate()
```

Typical usage patterns:

- Activate before performing a batch of resolutions or configuration.
- Deactivate to ensure the container is no longer considered active and any scoped resources are released.

## Using the current context (context manager)

The `as_current()` method returns a context manager that sets the container as the current context for the duration of the `with` block.

```python
from pico import PicoContainer

container = PicoContainer()

with container.as_current():
    # Inside this block, the 'current' container refers to 'container'
    current = PicoContainer.current()
    assert current is container

# Outside the block, the previous current (if any) is restored
assert PicoContainer.current() is not container
```

This pattern is useful for code that implicitly depends on the current container without passing instances around explicitly.

## Container IDs and the global registry

Every container gets a unique ID, and all containers are tracked by a registry that you can inspect at runtime.

```python
from pico import PicoContainer

c1 = PicoContainer()
c2 = PicoContainer()

assert c1.container_id != c2.container_id  # IDs are unique

# Inspect the registry of all containers
all_containers = PicoContainer.registry()
assert c1 in all_containers and c2 in all_containers
print([c.container_id for c in all_containers])
```

Use the registry to introspect or manage multiple containers in complex applications.

## Statistics

Use `stats()` to retrieve information about a container. Stats include the container ID, configured profiles, and resolution metrics.

```python
container = PicoContainer(profiles=['dev', 'feature-x'])

# After some resolution activity...
_ = container.resolve('my_service')
_ = container.resolve('another_service')

info = container.stats()
print(info['container_id'])  # Unique ID
print(info['profiles'])      # ['dev', 'feature-x']
print(info['resolutions'])   # e.g., {'success': 2, 'failures': 0} or similar
```

Stats are useful for monitoring, debugging, and diagnostics, providing insight into how and where the container is being used.

## Best practices

- Prefer `with container.as_current():` for code that relies on an ambient “current” container to avoid leaking context across scopes.
- Pair `activate()` with `deactivate()` to clearly define lifecycle and prevent unintended usage.
- Use profiles to segregate configurations and inspect them via `stats()` for validation.
- Leverage the registry when coordinating multiple containers, such as in tests or multi-tenant scenarios.

---

## Auto-generated API

::: pico_ioc.api