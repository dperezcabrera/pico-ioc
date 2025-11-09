## ADR-008: Explicit Handling of Circular Dependencies

Status: Accepted

### Context

Dependency Injection (DI) containers must ensure a clear and deterministic component lifecycle. Circular dependencies (where component A requires B, and B requires A) are an anti-pattern that often leads to inconsistent states, deadlocks, or runtime failures. The framework must detect these cycles and enforce explicit solutions, instead of attempting implicit and fragile resolution (for example, injecting lazy proxies into constructors).

### Decision

We implement a system that:

1) Detects and fails fast: During validation in init() and upon initiation of resolution (get/aget), any dependency cycle is detected and a CircularDependencyError with the full dependency chain is raised.

2) Enforces explicit cycle breaking: To resolve a cycle, developers must use well-defined cycle-breaking mechanisms, avoiding the constructor (__init__) for at least one of the dependencies.

Promoted explicit cycle-breaking mechanisms:

- Post-construction configuration via a @configure method to inject one of the dependencies after initial construction.
- Provider-based indirection: inject a provider (Callable[[], T] or Provider[T]) so the component accesses the dependency lazily only when actually needed.
- Decoupling via EventBus (see ADR-007).

### Implementation Notes

- Validation phase: The container builds a dependency graph from component descriptors in init() and runs cycle detection. Any discovered cycle causes init() to fail with CircularDependencyError, including the resolution chain.
- Resolution phase: The container tracks an active resolution stack for get/aget. If a dynamic or runtime-only path introduces a cycle, the same error is raised with the full chain.
- Error diagnostics: CircularDependencyError includes the ordered list of components/providers involved (e.g., A -> B -> C -> A) to facilitate debugging.
- Scope and async: The mechanism applies to all scopes and supports both synchronous (get) and asynchronous (aget) resolution.
- No proxy-based implicit resolution: The container will not auto-inject proxies or placeholders into __init__ to hide cycles.

### Developer Guidance

When a cycle is required by design, choose one of:
- Move one side of the reference to @configure and document the post-construction requirement.
- Inject a Provider[T] or a Callable[[], T] and access the dependency only when needed (avoid touching the provider in __init__).
- Break direct coupling via EventBus if the interaction is event-driven.

General recommendations:
- Keep constructors side-effect-free and avoid calling the container or other components from __init__.
- Prefer providers for optional or infrequently used dependencies; prefer @configure when a dependency must be set once before regular operation.
- Make cycles explicit in tests and documentation.

### Consequences

Positive:
- Ensures architectural robustness: all components are fully initialized before being used.
- Improves code clarity: dependency relationships are explicit via @configure or provider injection.
- Immediate diagnosis: CircularDependencyError provides the full resolution chain, facilitating debugging.
- Avoids partial states: objects are never used in a “construction-in-progress” state.

Negative:
- Adds boilerplate: developers must use @configure or providers to resolve valid cycles (i.e., those that are not a design flaw).
- No implicit resolution: developers must understand class architecture to avoid cycles, unlike some frameworks that attempt automatic resolution via proxies.
