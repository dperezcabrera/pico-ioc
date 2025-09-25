# FEATURE-2025-0005: Container Diagnostics

  - **Date:** 2025-09-17
  - **Status:** Draft
  - **Priority:** high
  - **Related:** RFC-XXXX (Diagnostics API), ADR-XXXX (Describe contract), PLAN-XXXX (Diagnostics rollout)

## 1\) Summary

Introduce a unified diagnostics API (`container.describe()`) that exports the initialization context, active interceptors, and the fully resolved dependency graph of a PicoContainer.
This enables developers to debug dependency wiring, auto-generate architecture documentation, and analyze the effective runtime configuration.

-----

## 2\) Goals

  - Provide a deterministic, JSON-serializable snapshot of the container state.
  - Support graph export (nodes/edges) including policies, qualifiers, and scopes.
  - Ensure safe redaction of sensitive configuration values.
  - Offer alternative output formats (Mermaid/DOT) for visualization.

-----

## 3\) Non-Goals

  - No implicit tracing or runtime profiling (outside of snapshot export).
  - No persistence layer for diagnostics (caller decides where to store/export).
  - No “scan the world” of inactive/discarded providers by default (unless `include_inactive=True`).

-----

## 4\) User Impact / Stories (Given/When/Then)

  - **Given** a container initialized with components and overrides, **when** I call `container.describe()`, **then** I receive a JSON-compatible object with initialization context, interceptors, and dependency graph.
  - **Given** a failing container init, **when** I call `container.describe()`, **then** I get a partial snapshot with `status="failed"` and error details.
  - **Given** a container with a circular dependency, **when** I call `container.describe()`, **then** the graph successfully renders and clearly marks the circular edge.
  - **Given** I want to visualize dependencies, **when** I call `container.describe(format="mermaid")`, **then** I get a ready-to-render Mermaid graph.
  - **Given** two identical init calls, **when** I compare snapshots, **then** IDs and ordering are stable.

-----

## 5\) Scope & Acceptance Criteria

  - **In scope:**
      - Container metadata (context, interceptors, graph).
      - Safe redaction and filters.
      - Provenance details (`declared_at`, `provided_by`).
      - Export helpers (Mermaid, DOT).
  - **Out of scope:**
      - Performance profiling.
      - Instance inspection.
      - Dynamic mutation APIs.
  - **Acceptance:**
      - [ ] AC1: `describe()` returns `schema_version`, `generated_at`, `status`, `initialization_context`, `active_interceptors`, and `dependency_graph`.
      - [ ] AC2: Output is deterministic for the same inputs (stable IDs + ordering).
      - [ ] AC3: Sensitive values from config components are redacted by default.
      - [ ] AC4: Partial snapshots are produced if initialization fails, including error details. (See Appendix B).
      - [ ] AC5: Support `format="dict"|"mermaid"|"dot"`.
      - [ ] AC6: Provenance is available (`declared_at` includes decorator, `policy_resolutions` includes decisions and reasons).
      - [ ] AC7: Edges capture `parameter_name`, `annotation`, `required`, and `source_site`.
      - [ ] AC8: Configurable filters (`only_types`, `only_tags`, `include_inactive`) are applied during graph construction for efficiency.
      - [ ] AC9: Export size is manageable via filters (scalability guardrail).
      - [ ] AC10: Circular dependencies are detected gracefully and marked in the graph output.
      - [ ] AC11: Logs and metrics confirm API use (telemetry).

-----

## 6\) API / UX Contract

```python
def PicoContainer.describe(
    self,
    *,
    include_values: bool = False,
    include_inactive: bool = False,
    only_types: list[str] | None = None,
    only_tags: list[str] | None = None,
    redact_patterns: list[str] | None = None,
    format: str = "dict"  # "dict" | "mermaid" | "dot"
) -> dict | str: ...
```

### Example

```python
container = init("myapp")
snapshot = container.describe()
print(snapshot["dependency_graph"]["nodes"])
```

### Determinism & IDs

  - **Node IDs:** Generated as `blake2b(..., digest_size=8).hexdigest()`. The hashed content will be a stable representation of the key, implementation, qualifiers, and tags. Non-hashable keys will be handled via their string representation.
  - **Display Key Formatting:**
      - **Class/Type:** `module.ClassName`
      - **String:** `str:"the_string_key"`
      - **Other:** `repr(key)` as a fallback.
  - **Ordering:** All lists (nodes, edges, interceptors, etc.) within the output must be sorted by a deterministic key (e.g., node ID, class name) to ensure stable output.

-----

## 7\) Rollout & Guardrails

  - Rollout in minor version, no breaking changes.
  - Redaction ON by default, explicit opt-in for values.
  - Rollback path: feature flag `DIAGNOSTICS_API_ENABLED`.
  - Ordering and `schema_version` guarantee backward compatibility.

-----

## 8\) Telemetry

  - Log every call at DEBUG level with snapshot size and format.
  - Metrics: count of describe calls, avg snapshot size.
  - Optional `trace_id` embedded for correlation.

-----

## 9\) Risks & Open Questions

  - **Risk:** Large graphs → heavy snapshots.
      - **Mitigation:** Filters are applied *during* graph construction (not after) to minimize memory and CPU usage. Lazy export for formats.
  - **Risk:** Secrets leaking if values exported.
      - **Mitigation:** Redaction is ON by default. Patterns are configurable.
  - **Decision:** The `policy` module will be enhanced to produce an "audit trail" of its decisions, which `describe()` will consume for the `policy_resolutions` field. This is necessary for full transparency.

-----

## 10\) Test Strategy

  - **Unit tests:** deterministic IDs, redactions, filters, ordering, display key formatting.
  - **Integration tests:** scopes, lazy components, overrides, conditionals.
  - **Error cases:** partial init, invalid providers, **circular dependency detection**.
  - **Export tests:** valid Mermaid/DOT syntax.
  - **Regression tests:** diff snapshots across runs must be stable.

-----

## 11\) Milestones

  - **M1 Ready:** 2025-09-17 (spec refined).
  - **M2 Planned:** implementation branch + tests + export helpers.
  - **M3 Shipped:** merged in release 1.x, docs updated.

-----

## 12\) Documentation Impact

  - Update `GUIDE.md` with usage examples for debugging.
  - Add `FEATURE_DIAGNOSTICS.md` with a detailed schema reference.
  - Extend `ARCHITECTURE.md` with a Mermaid/DOT visualization of the library's own components.

-----

## 13\) Implementation Notes

  - **`diagnostics.py` Module:** The core logic for building the snapshot will reside in a new `src/pico_ioc/diagnostics.py` module to keep `container.py` clean.
  - **Diagnostic Resolver:** A dedicated class or set of functions will be created to inspect component dependencies (`__init__` signatures, factory functions) without triggering `container.get()`. This resolver must be capable of safely parsing complex type annotations and detecting circular dependencies.
  - **Context Passing:** The `PicoContainerBuilder` will pass a structured `InitializationContext` object to the `PicoContainer` upon build, making it available for the `describe()` method.

-----

## Appendix A: Example Snapshot (JSON)

```json
{
  "schema_version": "1.0",
  "generated_at": "2025-09-17T21:30:00Z",
  "status": "ok",
  "container_id": "pc_41b9f2aa",
  "build_fingerprint": "...",
  "initialization_context": { "...": "..." },
  "active_interceptors": [ "...": "..." ],
  "dependency_graph": {
    "nodes": [
      {
        "id": "n_a1b2c3d4",
        "display_key": "myapp.ServiceA",
        "key": "myapp.ServiceA",
        "type": "component",
        "implementation": "myapp.ServiceA",
        "lazy": false,
        "qualifiers": ["Primary"],
        "tags": ["http", "critical"],
        "declared_at": {
          "module": "myapp.services",
          "file": "services.py",
          "line": 15,
          "decorator": "@component"
        },
        "policy_resolutions": [
          {"policy": "@primary", "decision": "selected", "reason": "Component is primary."}
        ]
      },
      {
        "id": "n_b5e8f7g6",
        "display_key": "myapp.FallbackService",
        "key": "myapp.FallbackService",
        "type": "component",
        "implementation": "myapp.FallbackService",
        "lazy": false,
        "qualifiers": [],
        "tags": [],
        "declared_at": { "...": "..." },
        "policy_resolutions": [
          {"policy": "@primary", "decision": "discarded", "reason": "A primary component 'myapp.ServiceA' already exists for the base type."}
        ]
      }
    ],
    "edges": [
      {
        "source": "n_a1b2c3d4",
        "target": "n_d9e8f7g6",
        "parameter_name": "repo",
        "dependency_type": "direct",
        "required": true,
        "is_circular": false,
        "annotation": "Annotated[Repository, Qualifier('sql')]",
        "source_site": {"file": "services.py", "line": 20}
      },
      {
        "source": "n_c1a1b1c1",
        "target": "n_d2b2c2d2",
        "parameter_name": "service_d",
        "dependency_type": "direct",
        "required": true,
        "is_circular": true,
        "annotation": "ServiceD",
        "source_site": {"file": "service_c.py", "line": 10}
      }
    ]
  }
}
```

## Appendix B: Example of a Failed Snapshot

```json
{
  "schema_version": "1.0",
  "generated_at": "2025-09-17T21:35:00Z",
  "status": "failed",
  "container_id": null,
  "build_fingerprint": "...",
  "initialization_context": {
    "function": "init",
    "root_package": "myapp",
    "profiles": ["dev"],
    "...": "..."
  },
  "error": {
    "type": "NameError",
    "message": "No provider found for key 'myapp.MissingDependency' (required by myapp.ServiceA.__init__ -> dep)",
    "stacktrace": [
      "File \".../pico_ioc/resolver.py\", line 123, in _resolve_param",
      "File \".../pico_ioc/builder.py\", line 99, in build"
    ]
  },
  "dependency_graph": null,
  "active_interceptors": []
}
```
