# ADR-0011: Extensible Component Scanning via Custom Scanners

Status: Accepted

## Context

The original component scanning mechanism in `pico-ioc` was designed as a closed system. It strictly looked for specific internal decorators (`@component`, `@factory`, `@provides`, `@configured`) and hardcoded logic within `ComponentScanner`.

This rigidity created significant challenges for third-party extensions (such as `pico-agent` or web frameworks):
1.  **Global Mutable State:** Extensions were forced to use global registries (e.g., `_PENDING_AGENTS` lists) to track decorated objects, leading to thread-safety issues and test contamination.
2.  **Fragile Hacks:** Extensions often relied on stack frame inspection to guess the caller's module, which is unreliable.
3.  **Lack of Hooks:** There was no clean way to intercept the scanning phase to register objects based on custom logic (e.g., registering a function decorated with `@task` as a prototype component).

We needed a standardized, stateless extension point to allow third-party libraries to participate in the discovery phase.

## Decision

We introduce the `CustomScanner` protocol and expose a new `custom_scanners` argument in the `init()` API.

1.  **Protocol Definition:** We define a `CustomScanner` protocol with `should_scan(obj)` and `scan(obj)` methods. This delegates the responsibility of pattern matching and metadata construction to the extension author.
2.  **Priority Scanning:** The `ComponentScanner` iteration logic is modified to prioritize these custom scanners.
    * The scanner iterates through all module members once.
    * For **every** member (whether it is a Class, Function, or other object), it first checks the registered `custom_scanners`.
    * If a custom scanner claims the object (returns a binding), the built-in native scanning logic is skipped for that object.
3.  **Injection via Init:** Users or frameworks pass instances of these scanners into the container via `init(..., custom_scanners=[...])`.

## Details

### The Protocol

```python
class CustomScanner(Protocol):
    def should_scan(self, obj: Any) -> bool:
        """Return True if this scanner handles the given object."""
        ...

    def scan(self, obj: Any) -> Optional[Tuple[KeyT, Provider, ProviderMetadata]]:
        """
        Constructs the binding artifacts.
        Returns (key, provider, metadata) or None.
        """
        ...
```

### Scanning Logic

The internal loop in `ComponentScanner.scan_module` effectively works as follows:

```python
for name, obj in inspect.getmembers(module):
    # 1. Custom Scanners take precedence over everything
    if self._try_custom_scanners(obj):
        continue

    # 2. Native logic (Component, Factory, Configured, Provides)
    # ...
```

This ensures that a custom scanner can override default behavior or register objects that `pico-ioc` would normally ignore (like standalone functions decorated with custom markers).

## Consequences

### Positive

  - **Decoupling:** Extensions no longer need to depend on `pico-ioc` internals or global state.
  - **Flexibility:** Enables support for function-based components (e.g., tasks, agents) and custom class decorators.
  - **Safety:** Scanners are scoped to the container instance, ensuring thread safety and isolation during tests.
  - **Performance:** Single-pass iteration over module members allows for efficient discovery without repeated `inspect` calls.

### Negative

  - **Complexity:** Increases the API surface area of `init()`.
  - **Manual Wiring:** Without a wrapper (like `pico-stack`), users must manually instantiate and pass scanner instances to `init()`.

## Alternatives Considered

  - **Global Registry Hooks:** Rejected due to testing isolation issues and "magic" global state.
  - **Inheritance (`class MyScanner(ComponentScanner)`):** Rejected because it tightly couples extensions to the internal implementation of the default scanner and makes composing multiple extensions difficult.

<!-- end list -->

