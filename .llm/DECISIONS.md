# DECISIONS.md — pico-ioc

This document records **technical and architectural decisions** for pico-ioc.  
Each entry includes a rationale and implications. If a decision is later changed, mark it **[REVOKED]** and link to the replacement.

---

## ✅ Current Decisions

### 1) Minimum Python version: **3.10**
**Decision**: Require Python **3.10+**; drop 3.8/3.9.  
**Rationale**: `typing.Annotated` + `get_type_hints(..., include_extras=True)` simplify internals and enable qualifiers/collections.  
**Implications**: Users on older runtimes must upgrade; CI matrix targets 3.10+.

---

### 2) Resolution order: **param name → exact type → MRO → string token**
**Decision**: Name-first resolution with deterministic fallback.  
**Rationale**: Ergonomic for common configs by name; still strongly typed.  
**Implications**: Documented behavior; potential behavior change from older pre-1.0 versions.

---

### 3) Lifecycle model: **singleton per container**
**Decision**: One instance per key per container.  
**Rationale**: Matches typical Python app composition (config/clients/services); simple and fast.  
**Implications**: No request/session scopes at IoC level; use framework facilities if needed. `lazy=True` is available but not default.

---

### 4) Fail-fast bootstrap
**Decision**: Instantiate eager components after `init()`; surface errors early.  
**Rationale**: Deterministic startup; no hidden runtime surprises.  
**Implications**: Keep constructors cheap; push heavy I/O to explicit start/serve phases.

---

### 5) Keys: **typed keys preferred; string tokens allowed but discouraged**
**Decision**: Prefer class/type keys (e.g., `Flask`) over string tokens.  
**Rationale**: Better IDE support, fewer collisions, clearer intent.  
**Implications**: String tokens remain for interop, but are a last resort.

---

### 6) Qualifiers & collection injection are **first-class**
**Decision**: Support `Annotated[T, Q]` and `list[Annotated[T, Q]]` for filtering.  
**Rationale**: Enables side-by-side implementations (primary/fallback) without custom registries.  
**Implications**: Stable registration order is preserved for lists; empty lists are valid.

---

### 7) Plugins are **explicitly registered**
**Decision**: No magical discovery; pass plugins to `init(..., plugins=(...))`.  
**Rationale**: Predictability and testability.  
**Implications**: Slightly more verbose, but boundaries stay explicit.

---

### 8) Public API helper (`export_public_symbols_decorated`)
**Decision**: Provide a helper to auto-export decorated symbols in a package’s `__init__.py`.  
**Rationale**: Reduces boilerplate; favors convention over configuration.  
**Implications**: Dynamic export is opt-in; does not auto-register providers by itself.

---

### 9) Overrides in `init(...)`
**Decision**: `init(..., overrides={...})` replaces bindings at bootstrap.  
**Rationale**: Simple unit testing/mocking without extra modules.  
**Implications**:
- Applied **before eager instantiation** → replaced providers never run.  
- Accepted forms:  
  - `key: instance` (constant)  
  - `key: callable` (provider, non-lazy)  
  - `key: (callable, lazy_bool)` (provider with explicit laziness)  
- If `reuse=True`, calling `init()` with different `overrides` will generate a new fingerprint and build a new container, not mutate the cached one.

---

### 10) Scoped subgraphs with `scope(...)`
**Decision**: Provide `scope(...)` to build a bounded container limited to the dependency subgraph of given roots.  
**Rationale**: Faster, deterministic unit/integration setups; great for CLIs/benchmarks.  
**Implications**:
- **Not** a new lifecycle: still singleton-per-container.  
- Supports `include_tags`/`exclude_tags` (tags from `@component(..., tags=...)` / `@provides(..., tags=...)`).  
- `strict=True` fails if deps are outside subgraph.  
- Works as a context manager to ensure clean teardown.

---

### 11) **Infrastructure-based Interceptor API**
**Decision**: Provide an extension mechanism for AOP and lifecycle hooks through **manually registered interceptors**. Instead of auto-discovery, interceptors are activated within `@infrastructure` components, giving developers explicit control over their application and order.
**Kinds & Hooks**:
- **`MethodInterceptor`**: Implements `invoke(self, ctx: MethodCtx, call_next)`. Wraps method calls on components for Aspect-Oriented Programming (AOP).
- **`ContainerInterceptor`**: Implements container lifecycle hooks:
    - `around_resolve(self, ctx: ResolveCtx, call_next)`
    - `around_create(self, ctx: CreateCtx, call_next)`
**Rationale**: This approach is more explicit and predictable than magic auto-discovery. It makes the wiring process easier to debug and ensures that the order of interceptors is controlled by the developer via the `order` parameter in `@infrastructure`.
**Implications**:
- Interceptors are plain Python classes that implement a protocol; they do not require a decorator.
- Their activation is tied to the lifecycle of the `@infrastructure` components that register them.

---

### 12) **Conditional providers** (profiles, env, predicate)
**Decision**: `@conditional(profiles=(...), require_env=(...), predicate=callable)` activates providers based on environment vars or logic.  
**Rationale**: Profile-driven wiring (`PROFILE=test/prod/ci`), optional integrations (Redis/S3) without code changes.  
**Implications**:
- If no active provider satisfies a required type → **bootstrap error** (or at resolution if lazy).  
- Multiple candidates may be active (use qualifiers/collections to select).  
- Works seamlessly with `scope(...)`; conditionals apply before traversal.

---

### 13) Deterministic Provider Selection: **Policy-driven, preferring @primary**
**Decision**: When multiple providers implement the same base type, the selection is not a simple "last-wins". Instead, a policy is applied:
1.  If one or more candidates are decorated with `@primary`, the first one found will be chosen.
2.  If no candidates are marked as primary, the selection may fall back to providers decorated with `@on_missing`, or other aliasing logic.
A true "last-wins" only occurs when binding the *exact same key* multiple times, which overwrites the previous provider entry.
**Rationale**: This provides more explicit control over which implementation is the default, making the dependency graph more predictable than relying solely on scan order.
**Implications**: To select a default implementation for an interface, use `@primary`. Module ordering is a less reliable mechanism for this purpose.

---

### 14) Concurrency & safety
**Decision**: Container is immutable after `init()`; caches are isolated and safe across threads/tasks; no global singletons.  
**Rationale**: Avoid shared mutable state; enable safe parallel use.  
**Implications**: Make your **own** instances thread/async-safe if they’re shared.

---

### 15) Configuration Injection
**Decision**: Provide `@config_component` for strongly typed configuration classes, populated from ordered `ConfigSource`s (`EnvSource`, `FileSource`, etc.).  
**Rationale**: Type-safe configuration with minimal boilerplate, supporting both automatic autowiring by field name and manual overrides (`Env`, `File`, `Path`, `Value`).  
**Implications**:
- Precedence is explicit: `overrides` > sources (in order) > field defaults.
- Missing required fields (no default and not resolvable) raise `NameError`.
- Supported formats: env vars, JSON, INI, dotenv, YAML (if available).
- Encourages using `dataclass(frozen=True)` for immutable, validated settings.

---

### 16) Container Diagnostics API (`describe()`)

**Decision**: Add a unified diagnostics method `container.describe(...)` that exports the initialization context, active interceptors, and the fully resolved dependency graph.  
**Rationale**: Developers need a deterministic way to introspect the container state for debugging, documentation, and architectural analysis. A stable schema with IDs, provenance, and safe redaction makes this reliable and auditable.  
**Implications**:
- Public API: `container.describe(include_values=False, include_inactive=False, only_types=None, only_tags=None, redact_patterns=None, format="dict")`.
- Default output is JSON-serializable with `schema_version`, `generated_at`, `status`, `initialization_context`, `active_interceptors`, and `dependency_graph`.
- Sensitive values are **redacted by default**; explicit opt-in required via `include_values=True`.
- Deterministic IDs and ordering allow snapshot diffs across runs.
- Alternative outputs supported (`mermaid`, `dot`) for visualization.
- Large graphs can be filtered (`only_types`, `only_tags`) to keep snapshots manageable.
- Partial snapshots with `status="partial"` are returned if initialization fails, including error metadata.

---

## ❌ Won’t-Do Decisions

### A) Alternative scopes (request/session)
**Decision**: No extra lifecycles beyond singleton-per-container.  
**Rationale**: Keep model simple; delegate per-request/session to frameworks.  
**Implications**: Avoids ownership ambiguity and complexity.

---

### B) Asynchronous providers (`async def`)
**Decision**: Not supported inside the container.  
**Rationale**: Simplicity and determinism; no loop coupling in core.  
**Implications**: If async init is required, handle it inside your component explicitly.

---

### C) Hot reload / dynamic re-scan
**Decision**: Not supported.  
**Rationale**: Conflicts with fail-fast and immutability; complicates debugging.  
**Implications**: Use framework/dev tools for code reload (e.g., `uvicorn --reload`).

---

## 🗃️ Deprecated / Revoked

_No entries currently._

---

## 📜 Changelog of Decisions

- **2025-08**: Minimum Python 3.10; name-first resolution; fail-fast clarified; typed keys preferred.  
- **2025-09-08**: Introduced `init(..., overrides)` with defined precedence and laziness semantics.  
- **2025-09-13**: Added `scope(...)` for bounded containers with tag pruning and strict mode.  
- **2025-09-14**: Replaced auto-discovered interceptors with an infrastructure-based registration model. Added **Conditional providers** as a first-class feature.

---

**Summary**: pico-ioc remains **simple, deterministic, and fail-fast**.  
We favor typed wiring, explicit registration, and small, composable primitives (overrides, scope, infrastructure, conditionals) instead of heavyweight AOP or multi-scope lifecycles.

