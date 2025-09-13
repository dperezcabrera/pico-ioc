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

## [Unreleased]
- Upcoming improvements and fixes will be listed here.

