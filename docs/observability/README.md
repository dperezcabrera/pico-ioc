# Observability

Welcome to the Observability section.

In a complex, production-grade application, you need tools to monitor, trace, and debug the container's behavior at runtime. `pico-ioc` provides built-in tools for these challenges.

This section gives you an overview of what you can observe, how to trace container activity safely in multi-container scenarios, and how to export the dependency graph for analysis and visualization.

---

## 📖 Table of Contents

* [1. Container Context: `as_current` (Multi-Container)](./container-context.md)
* [2. Observers & Metrics: `stats` (KPIs and Tracing Hooks)](./observers-metrics.md)
* [3. Exporting the Dependency Graph (Visualization)](./exporting-graph.md)

---

## What you will find here

- Multi-container context handling
  - Understand how to scope observability to the correct container instance using `as_current`.
  - Learn safe patterns for concurrent and nested container usage.

- Observers and metrics
  - Capture container-level KPIs and lifecycle events with `stats`.
  - Install lightweight hooks to trace resolutions, lifetimes, and failures.

- Graph export for visualization
  - Export the dependency graph to external tools for auditing and debugging.
  - Identify cycles, heavy paths, and hot spots for optimization.

---

## When to use these tools

- During development: to understand wiring, detect accidental singletons, or trace resolution order.
- In testing: to assert dependency graphs and capture timing/usage statistics.
- In production: to monitor container activity, build dashboards of resolution KPIs, and aid in incident investigations.

All features are designed to be:
- Opt-in and minimally intrusive.
- Safe to use in applications with multiple container instances.
- Suitable for both local debugging and production observability pipelines.

---

## Terminology

- Container: the dependency injection container instance from `pico-ioc`.
- Context: the active container used for lookups and tracing in multi-container scenarios.
- Observer/Stats: hooks and counters that record container activity (e.g., resolutions, cache hits/misses, failures).
- Dependency graph: the static/dynamic view of how types/providers depend on each other.

---

## Next steps

- If your app uses more than one container (or creates containers per request/task), start with Container Context to ensure data is attributed correctly.
- If you need to track KPIs or emit tracing information, continue with Observers & Metrics.
- If you need to inspect or visualize wiring and dependencies, go to Exporting the Dependency Graph.
