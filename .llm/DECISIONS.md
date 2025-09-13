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
- With `reuse=True`, subsequent `init(..., overrides=...)` mutates cached bindings.

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

### 11) **Interceptors API** (lifecycle hooks)
**Decision**: Introduce **interceptors** to observe/modify wiring.  
**Hooks**: `on_resolve`, `on_before_create`, `on_after_create` (may wrap/replace), `on_invoke`, `on_exception`.  
**Rationale**: Structured logging, metrics/timing, tracing, audit trails, guards/policies, safe wrappers (retry/circuit breaker) without full AOP complexity.  
**Implications**:
- Deterministic ordering via `order` (lower runs first).  
- Register at bootstrap (`init(..., interceptors=[...])`) or programmatically (`container.add_interceptor(...)`).  
- `on_exception` must re-raise if you don’t intend to mask errors.

---

### 12) **Conditional providers** (profiles)
**Decision**: `@conditional(require_env=(...), predicate=callable)` activates providers based on environment vars or logic.  
**Rationale**: Profile-driven wiring (`PROFILE=test/prod/ci`), optional integrations (Redis/S3) without code changes.  
**Implications**:
- If no active provider satisfies a required type → **bootstrap error** (or at resolution if lazy).  
- Multiple candidates may be active (use qualifiers/collections to select).  
- Works seamlessly with `scope(...)`; conditionals apply before traversal.

---

### 13) Deterministic registration: **last-wins**
**Decision**: For a given key, the **last** registered provider is the active one.  
**Rationale**: Predictable overrides by module ordering; simple mental model.  
**Implications**: Document ordering in tests; use `init([app, test_overrides])` to replace prod bindings.

---

### 14) Concurrency & safety
**Decision**: Container is immutable after `init()`; caches are isolated and safe across threads/tasks; no global singletons.  
**Rationale**: Avoid shared mutable state; enable safe parallel use.  
**Implications**: Make your **own** instances thread/async-safe if they’re shared.

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
- **2025-09-14**: Added **Interceptors API** and **Conditional providers (profiles)** as first-class features; documented last-wins registration and concurrency stance.

---

**Summary**: pico-ioc remains **simple, deterministic, and fail-fast**.  
We favor typed wiring, explicit registration, and small, composable primitives (overrides, scope, interceptors, conditionals) instead of heavyweight AOP or multi-scope lifecycles.

