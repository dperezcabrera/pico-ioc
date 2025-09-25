# ADR-004: Observability Features

**Status:** Accepted

## Context

As applications grow or adopt multi-container patterns (like multi-tenant), debugging, monitoring, and tracing become critical. V1 lacked built-in mechanisms for understanding the container's internal state, performance, or context. We needed features to make the container observable.

---

## Decision

We introduced several **observability-focused features**:

1.  **Unique Container ID (`container_id`):** Every `PicoContainer` instance receives a unique ID upon creation (or accepts one via `init(container_id=...)`).
2.  **Container Context (`as_current`, `get_current`, `shutdown`):** Implemented a `contextvars`-based system (see [ADR-003](./adr-0003-context-aware-scopes.md)) to track the "active" container. This allows logs/traces to be tagged with the `container_id` and enables multi-container patterns. `shutdown()` was added to explicitly deregister a container. `all_containers()` provides a global view.
3.  **Built-in Stats (`container.stats()`):** Added a method to return a dictionary of basic runtime metrics (uptime, resolve count, cache hits, component count, active profiles).
4.  **Observer Protocol (`ContainerObserver`):** Defined a protocol with methods like `on_resolve(key, took_ms)` and `on_cache_hit(key)`. Users can implement this protocol and pass instances to `init(observers=[...])` to receive real-time events, enabling integration with tracing systems (like OpenTelemetry) or custom monitoring.
5.  **Dependency Graph Export (`container.export_graph()`):** Added a method to export the container's resolved dependency graph to a `.dot` file (specified by the `path` argument) for visualization with Graphviz. Options allow controlling labels (`include_scopes`, `include_qualifiers`, `title`) and layout (`rankdir`).

---

## Consequences

**Positive:** 👍
* Greatly improves debuggability, especially in complex or multi-container scenarios.
* Provides basic metrics out-of-the-box via `stats()`.
* Enables sophisticated tracing and monitoring via the `ContainerObserver` hook.
* `export_graph()` offers valuable architectural insights and debugging aid.
* Establishes a foundation for reliable multi-tenant and hot-reload patterns.

**Negative:** 👎
* Adds slight overhead for context management (`contextvars`).
* `ContainerObserver` is a low-level API requiring careful implementation.
* `export_graph()` adds an optional dependency (`graphviz`).
