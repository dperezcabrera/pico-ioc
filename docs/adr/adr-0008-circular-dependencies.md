## ADR-008: Explicit Handling of Circular Dependencies

**Status:** Accepted

### Context

Dependency Injection ($\text{DI}$) containers must ensure a clear component lifecycle. **Circular dependencies** (where component A requires B, and B requires A) are an anti-pattern that leads to inconsistent states or runtime failures. The framework must detect these cycles and enforce an explicit solution, rather than attempting implicit and potentially fragile resolution (like lazy *proxy* injection into constructors).

### Decision

We decided to implement a system that will:

1.  **Detect and Fail-Fast**: During validation in `init()` and upon initiation of resolution (`get`/`aget`), any dependency cycle will be detected, and a `CircularDependencyError` with the full dependency chain will be raised.
2.  **Enforce Cycle Breaking**: To resolve a cycle, developers must use **explicit, well-defined cycle-breaking mechanisms**, avoiding the constructor (`__init__`) for at least one of the dependencies.

The promoted explicit cycle-breaking mechanisms are:

* Using the **`@configure`** method to inject one of the dependencies after the initial construction.
* Injecting the provider (**`Callable[[], T]`** or **`Provider[T]`**) so that the component accesses the object lazily only when actually needed.
* Decoupling via the **`EventBus`** (see $\text{ADR-007}$).

### Consequences

**Positive:** 👍

* **Ensures architectural robustness:** All components are fully initialized before being used.
* **Improves code clarity:** The dependency relationship is made explicit via `@configure` or provider injection.
* **Immediate diagnosis:** `CircularDependencyError` provides the full resolution chain, facilitating debugging.
* **Avoids partial states:** Objects are never used in a "construction-in-progress" state.

**Negative:** 👎

* **Adds boilerplate:** Developers must manually use `@configure` or providers to resolve valid cycles (i.e., those that are not a design flaw).
* **No implicit resolution:** The developer must understand the class's architecture to avoid cycles, unlike some frameworks that automatically resolve via proxies.
