# DECISIONS.md — pico-ioc

This document records **technical and architectural decisions** made for pico-ioc.  
Each entry has a rationale and implications. If a decision is revoked, it should be marked as **[REVOKED]** with a link to the replacement.

---

## ✅ Current Decisions

### 1. Minimum Python version: **3.10**
- **Decision**: Drop support for Python 3.8 and 3.9. Require Python **3.10+**.
- **Rationale**:  
  * Uses `typing.Annotated` and `typing.get_type_hints(..., include_extras=True)`.  
  * Simplifies code paths and avoids backports/conditionals.  
  * Encourages modern typing practices.
- **Implications**:  
  * Users on older runtimes must upgrade.  
  * CI/CD matrix only tests Python 3.10+.

---

### 2. Resolution order: **name-first**
- **Decision**: Parameter name has precedence over type annotation.  
- **Order**: **param name → exact type → MRO fallback → string token**.
- **Rationale**:  
  * Matches ergonomic use-cases (config by name).  
  * Keeps deterministic behavior and avoids ambiguity.
- **Implications**:  
  * Breaking change from earlier versions (<0.5.0).  
  * Documented in README and GUIDE.

---

### 3. Lifecycle: **singleton per container**
- **Decision**: Every provider produces exactly one instance per container.  
- **Rationale**:  
  * Matches common Python app architecture (config, DB clients, service classes).  
  * Simple mental model, cheap lookups.  
- **Implications**:  
  * No per-request or session scopes at the IoC level (delegate that to frameworks).  
  * Lazy proxies supported via `lazy=True`.

---

### 4. Fail-fast bootstrap
- **Decision**: All eager components are instantiated immediately after `init()`.  
- **Rationale**:  
  * Surfaces missing dependencies early.  
  * Avoids hidden runtime errors deep into request handling.  
- **Implications**:  
  * Slower startup if many components are eager.  
  * Recommended to keep constructors cheap.

---

### 5. Plugins: **explicit registration**
- **Decision**: Plugins must be passed explicitly to `init(..., plugins=(...))`.  
- **Rationale**:  
  * Keeps scanning predictable and avoids magical discovery.  
  * Encourages explicit boundaries in app wiring.
- **Implications**:  
  * More verbose in user code, but safer and testable.  
  * `@plugin` decorator only marks, does not auto-register.

---

### 6. Public API helper (`export_public_symbols_decorated`)
- **Decision**: Auto-export all decorated classes/components/plugins via `__getattr__`/`__dir__`.  
- **Rationale**:  
  * Reduces `__init__.py` boilerplate.  
  * Encourages convention-over-configuration.  
- **Implications**:  
  * Explicit imports may be replaced by dynamic export.  
  * Errors in scanning are suppressed (non-fatal).

---

### 7. Overrides in `init()`
- **Decision**: `init(..., overrides={...})` allows binding custom providers/instances at bootstrap time.
- **Rationale**:  
  * Simplifies unit testing and ad-hoc mocking.  
  * Avoids creating dedicated override modules when only a few dependencies need to be replaced.  
  * Keeps semantics explicit: last binding wins.
- **Implications**:  
  * Overrides are applied **before eager instantiation** — ensuring replaced providers never run.  
  * Accepted formats:
    - `key: instance` → constant binding
    - `key: provider_callable` → non-lazy binding
    - `key: (provider_callable, lazy_bool)` → binding with explicit laziness
  * If `reuse=True`, calling `init(..., overrides=...)` again applies overrides on the cached container.

---

### 8. Scoped subgraphs (`scope`)
- **Decision**: Introduce `scope(...)` API to build a container restricted to the dependency subgraph of given root components.  
- **Rationale**:  
  * Enables lightweight unit/integration tests without bootstrapping the whole app.  
  * Supports deterministic overrides (fakes, mocks) per scope.  
  * Keeps the lifecycle model unchanged (still singleton per container).  
- **Implications**:  
  * `scope(...)` is not a new lifecycle scope — it is a *bounded container*.  
  * Parameters: `roots`, `modules`, `overrides`, `include/exclude tags`, `strict`, `lazy`.  
  * Can be used as context manager to ensure clean teardown.  
  * Useful outside tests as well (CLI tools, benchmarks, isolated utilities).
- Tag filtering: `scope()` supports `include_tags` / `exclude_tags`. Untagged providers are neutral; `exclude_tags` takes precedence when both match.
---

## ❌ Won’t-Do Decisions

### 1. Alternative scopes (request/session)
- **Decision**: no additional scopes beyond *singleton per container* will be implemented.  
- **Rationale**:  
  * The simplicity of the current model (one instance per container) is a core value of pico-ioc.  
  * Web frameworks (Flask, FastAPI, etc.) already manage request/session lifecycles.  
  * Adding scopes would introduce unnecessary complexity and ambiguity about object ownership.  

---

### 2. Asynchronous providers
- **Decision**: no support for `async def` components or asynchronous resolution inside the container.  
- **Rationale**:  
  * Keeping the library **100% synchronous** preserves the current API (`container.get(...)` is always immediate).  
  * Async support would require event-loop integration, `await` semantics, and multiple runtime strategies → breaking simplicity.  
  * If a dependency needs async initialization, it should be handled inside the component itself, not by the container.  

---

### 3. Hot reload / dynamic re-scan
- **Decision**: no hot reload or dynamic re-scan of modules will be supported.  
- **Rationale**:  
  * Contradicts the **fail-fast** philosophy (surface errors at startup).  
  * Breaks the **determinism** guarantee (container is immutable after `init()`).  
  * Makes debugging harder: old instances may linger, state may become inconsistent, resources may leak.  
  * Development-time hot reload is already handled by frameworks (`uvicorn --reload`, etc.).  

---

📌 **Summary:** pico-ioc stays **simple, deterministic, and fail-fast**.  
Features that add complexity (alternative scopes, async providers, hot reload) are intentionally excluded. 

---

## 📜 Changelog of Decisions

- **2025-08**: Dropped Python 3.8/3.9 support, minimum 3.10.  
- **2025-08**: Clarified resolution order as *name-first*.  
- **2025-08**: Documented lifecycle, plugins, and fail-fast policy.  
- **2025-09**: Added `init(..., overrides)` feature for test/mocking convenience.
- **2025-09**: Added `scope(...)` for subgraph containers, primarily for testing and lightweight scenarios.

