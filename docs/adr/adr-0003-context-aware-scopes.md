# ADR-003: Context-Aware Scopes

Status: Accepted

## Update (v2.1.3) - Removal of LRU

The original decision to use LRU (Least Recently Used) eviction for scoped caches (see point 5 below) proved unsafe for high-concurrency scenarios, such as WebSockets or long-polling. In these cases, active but "quiet" connections could be arbitrarily evicted when the container reached its limit, causing data loss (amnesia) for ongoing sessions.

**Decision:** The LRU logic was removed in version 2.1.3.
**New Behavior:** Scoped caches are now unbounded to guarantee data integrity for all active contexts.
**Requirement:** Integrators (e.g., web middleware or manual context managers) **must** explicitly call `container._caches.cleanup_scope(...)` at the end of the lifecycle to prevent memory leaks.

---

### Context

Many applications, especially web services, need components whose lifecycle is tied to a specific context, like an individual HTTP request or a user's session. Imagine needing a unique `UserContext` object for each logged-in user making requests simultaneously. The standard `singleton` (one instance forever) and `prototype` (new instance every time) scopes aren't suitable for managing state within these temporary contexts. We needed a way to create "scoped singletons" – ensuring exactly one instance per active context.

### Decision

We introduced context-aware scopes built upon Python's `contextvars`:

1) **ScopeProtocol:** Defined a minimal interface for custom scope implementations, requiring only `get_id() -> Any | None` to return the identifier of the currently active scope instance.

2) **ContextVarScope:** Provided a standard implementation using `contextvars.ContextVar`. This allows tracking the active scope ID within async tasks and threads correctly. It includes helper methods like `activate(id)` and `deactivate(token)`.

3) **ScopeManager:** An internal registry holding `ScopeProtocol` implementations for named scopes (e.g., "request", "session"). It provides the core logic for activating, deactivating, and retrieving the current ID for any registered scope.

4) **`scope="..."` parameter:** Components are assigned to a specific scope using the `scope` parameter within the main registration decorators (`@component`, `@factory`, `@provides`). For example: `@component(scope="request")`.

5) **ScopedCaches:** Modified the internal caching mechanism to handle multiple caches keyed by `(scope_name, scope_id)`.
   * *Historical Note:* Originally, this used an LRU strategy to automatically evict caches. As of v2.1.3, this is an unbounded registry requiring explicit cleanup.

6) **Container API:** Added convenient methods for managing scopes:
    - `container.activate_scope(name, id)` and `container.deactivate_scope(name, token)` for manual control.
    - The preferred `with container.scope(name, id):` context manager for easy, safe activation and deactivation within a block.
    - Pre-registered common web scopes like "request", "session", and "transaction" for convenience.

### Usage

- **Registering a scoped component:**
  - Use `@component(scope="request")` to ensure one instance per active request scope.
  - Factories and providers support scope in the same way: `@factory(scope="session")`, `@provides(scope="transaction")`.

- **Activating a scope:**
  - Prefer the context manager: `with container.scope("request", request_id):` resolve components and handle work inside the block.
  - Manual control:
    - `token = container.activate_scope("session", session_id)`
    - ...resolve and use components...
    - `container.deactivate_scope("session", token)`

- **Custom scopes:**
  - Define a custom scope by implementing `ScopeProtocol` (providing `get_id()`) or by using `ContextVarScope`.
  - Register at initialization via `init(custom_scopes={"tenant": ContextVarScope(...)})`.
  - Use `@component(scope="tenant")` for components that should be unique per tenant.

- **Async compatibility:**
  - Scopes rely on `contextvars`, so active scope IDs propagate correctly across `asyncio` tasks spawned within the same context.
  - For thread pools or manual threading, activate the scope within each worker execution or ensure framework integration propagates context.

### Implementation Notes

- **Scope identifiers:**
  - Scope IDs must be stable and hashable; they are used as part of the cache key (scope_name, scope_id).
  - Choose IDs that uniquely represent the current context (e.g., a UUID for requests, a user/session ID for sessions).

- **Cache management:**
  - `ScopedCaches` maintains a distinct cache per `(scope_name, scope_id)` pairing.
  - *Updated v2.1.3:* Cleanup is manual via `cleanup_scope`.

- **Safety:**
  - The context manager ensures scopes are correctly deactivated even if exceptions occur inside the block.
  - Manual activate/deactivate requires pairing the token returned by `activate_scope` with `deactivate_scope` to avoid leaks.

### Consequences

**Positive:**
- Enables safe and isolated management of context-specific state (e.g., holding data for a single web request without interfering with others).
- Integrates naturally with `asyncio` due to the use of `contextvars`, making it suitable for modern async web frameworks.
- Provides a clean and developer-friendly API for activating/deactivating scopes, especially the `with container.scope():` manager.
- Extensible: Users can define and register their own custom scopes via `init(custom_scopes={...})`.

**Negative:**
- Relies on `contextvars`, which requires careful handling, especially regarding context propagation across thread boundaries if not managed automatically by frameworks.
- Requires explicit scope activation/deactivation in the application's entry points (e.g., web middleware). The container itself doesn't automatically detect the start/end of a request; the framework integration needs to call the container's scope methods.
- **Memory Management:** Without the automatic LRU (removed in v2.1.3), there is a risk of memory leaks if the integration layer fails to call `cleanup_scope` after the context ends.

### Alternatives Considered

- **Thread-local storage:**
  - Rejected due to poor compatibility with `asyncio` and cross-thread propagation issues in modern Python web runtimes.

- **Global registries keyed by request/session:**
  - Rejected for complexity, manual cleanup requirements, and weaker isolation compared to `contextvars`.

- **Prototype-only components:**
  - Rejected because they cannot guarantee a single instance per context, leading to duplicated state and higher allocation overhead.

### Migration

- **Existing singleton components that should be per-request or per-session:**
  - Add `scope="request"` or `scope="session"` to their registration decorators.
  - Ensure the application activates the corresponding scope in middleware/entry points.

- **Framework integration:**
  - Web frameworks should activate the "request" scope at the start of request handling and deactivate it at the end.
  - **Update:** Frameworks must also ensure `container._caches.cleanup_scope("request", id)` is called in a `finally` block.
