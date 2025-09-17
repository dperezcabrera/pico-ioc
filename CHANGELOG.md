# Changelog

All notable changes to this project will be documented in this file.

---

## [1.0.0] — 2025-08-28

### 🚀 Highlights
- **Dropped legacy runtimes**
  - Minimum Python version is now **3.10+**
  - Simplifies internals by relying on `typing.Annotated` and `include_extras=True`

- **Qualifiers support**
  - Components can be tagged with `Qualifier` via `@qualifier(Q)`
  - Enables fine-grained grouping of implementations

- **Collection injection**
  - Inject `list[T]` or `tuple[T]` to receive all registered implementations
  - Supports filtered injection with `list[Annotated[T, Q]]`

### 🔌 Core principles reaffirmed
- **Singleton per container** — no request/session scopes
- **Fail-fast bootstrap** — eager instantiation by default
- **Explicit plugins** — passed to `init()` directly, no magic auto-discovery
- **Public API helper** — `export_public_symbols_decorated` keeps `__init__.py` clean

### ❌ Won’t-do decisions
- Alternative scopes (request/session)
- Async providers (`async def`)
- Hot reload / dynamic re-scan

These were evaluated and **rejected** to keep pico-ioc simple, deterministic, and testable.

---

## [1.1.0] — 2025-09-08

### ✨ New
- **Overrides in `init()`**
  - Added `overrides` argument to `init(...)` for ad-hoc mocking/testing.
  - Accepted formats:
    - `key: instance` → constant binding
    - `key: callable` → non-lazy provider
    - `key: (callable, lazy_bool)` → provider with explicit laziness
  - Applied **before eager instantiation**, so replaced providers never run.
  - If `reuse=True`, calling `init(..., overrides=...)` again mutates the cached container.

### 📚 Docs
- Updated **README.md**, **GUIDE.md**, **OVERVIEW.md**, **DECISIONS.md**, and **ARCHITECTURE.md** to document overrides support.

---

## [1.2.0] — 2025-09-13

### ✨ New
- **Scoped subgraphs with `scope()`**
  - Added `pico_ioc.scope(...)` to build a container limited to a dependency subgraph.
  - Useful for unit tests, integration-lite scenarios, and CLI tools.
  - Parameters:
    - `roots=[...]` → define entrypoints of the subgraph
    - `modules=[...]` → packages to scan
    - `overrides={...}` → inject fakes/mocks
    - `strict=True` → fail if dependency not in subgraph
    - `lazy=True` → instantiate on-demand
  - Can be used as a context manager for clean setup/teardown.
  - `scope(..., include_tags=..., exclude_tags=...)` to prune the subgraph by provider tags from `@component(tags=...)` / `@provides(..., tags=...)`.

### 🧪 Testing
- New pytest-friendly fixture examples with `scope(...)` for lightweight injection.

---

## [1.3.0] — 2025-09-14

### ✨ New
- **`@interceptor` Decorator**: Interceptors are declared in-place using the `@interceptor` decorator on a class or a provider method. The scanner discovers and activates them automatically based on their metadata (`kind`, `order`, `profiles`, etc.). This simplifies the bootstrap process and co-locates cross-cutting concerns with their implementation.

- **Conditional providers**
  - `@conditional(require_env=("VAR",))` activates a component only if env vars are present.
  - `@conditional(predicate=callable)` enables fine-grained activation rules.
  - Useful for switching between implementations (e.g., Redis/Memcached) depending on environment.

### 📚 Docs
- Added **GUIDE_CREATING_PLUGINS_AND_INTERCEPTORS.md** with examples for the new auto-registration system.
- Updated **ARCHITECTURE.md** to reflect the new bootstrap sequence.

---

## [1.4.0] — 2025-09-16

### ✨ New
- **Configuration Injection**
  - Added `@config_component` for strongly typed settings classes.
  - Supports environment variables and property files (YAML, JSON, INI, dotenv).
  - Automatic field autowiring by name, with manual overrides (`Env`, `File`, `Path`, `Value`).
  - Precedence: `overrides` > declared config sources > field defaults.
  - Strict mode: missing required fields (no default and not resolvable) raise `NameError`.

### 🧪 Testing
- Added tests for precedence (env > file > default), dotted-path resolution, lazy instantiation, and required-field validation.


### 📚 Docs
- Added **GUIDE-CONFIGURATION-INJECTION.md** with examples for the new configuration injection system.

---

## [1.5.0] — 2025-09-17

### 🚨 Breaking
- **Removed legacy `@interceptor` API**  
  The old `before/after/error` style is no longer supported.  
  → Interceptors must be migrated to the new `MethodInterceptor.invoke` / `ContainerInterceptor.around_*` contracts.  

### ✨ New
- **`@infrastructure` decorator**
  - Enables bootstrap-time configuration via dedicated infrastructure classes.
  - Provides a safe façade (`infra.query`, `infra.intercept`, `infra.mutate`) to explore and mutate the model.
  - Deterministic ordering (`order=`) for infrastructure execution.
- **Around-style interceptors**
  - `MethodInterceptor.invoke(ctx, call_next)` for sync/async method interception.
  - `ContainerInterceptor.around_resolve` and `around_create` for lifecycle interception.
  - Enforced guardrails: must call `call_next` at most once; default cap of 16 interceptors per method.

### 🧪 Testing
- Added unit tests for `Select` DSL (tag/profile/class/method filters).
- Integration tests for interceptor chain order (sync + async).
- Negative tests for empty `where` and cap-exceeded cases.

### 📚 Docs
- Updated **GUIDE.md** and added **GUIDE-INFRASTRUCTURE.md** with migration examples.  
- Updated **DECISIONS.md** to record the removal of legacy interceptor support.  
- Release notes include a migration guide for existing interceptor users.

---

## [Unreleased]
- Upcoming improvements and fixes will be listed here.

