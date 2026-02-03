# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog (https://keepachangelog.com/en/1.0.0/),
and this project adheres to Semantic Versioning (https://semver.org/spec/v2.0.html).

---

## [2.2.1] - 2026-02-03

### Fixed 🧩

- **DOT Graph Export**: Fixed incorrect variable reference in `export_graph()` where dependency edges used `{child}` instead of `{cid}`, causing malformed DOT output when visualizing the dependency graph.
- **Race Condition in Lazy Proxy**: Fixed a race condition in `UnifiedComponentProxy._async_init_if_needed()` where concurrent async access could trigger duplicate object creation. The fix implements proper double-check locking and moves `@configure` execution outside the critical section to prevent deadlocks.
- **Silent Cleanup Failures**: Replaced silent `except Exception: pass` blocks in `ScopedCaches` cleanup methods with proper logging. Cleanup method failures are now logged at WARNING level, aiding debugging of resource leaks without crashing the application.

### Internal 🔧

- Added `logging` import and `_logger` instance to `scope.py` for structured error reporting during component cleanup.

---

## [2.2.0] - 2025-11-29

### Added ✨
- **Extensible Component Scanning (ADR-0011):** Introduced the `CustomScanner` protocol and `custom_scanners` parameter in `init()`. This opens the discovery phase to third-party extensions, allowing registration of components based on custom decorators or base classes.
- **Function-First Scanning:** Updated `ComponentScanner` to evaluate `CustomScanner` logic against *all* module members (classes and functions) before applying native logic. This enables extensions to register standalone functions (e.g., `@task`) as components.
- **Async Shutdown:** Added `container.ashutdown()` (awaitable). This fills a critical gap in the async lifecycle, ensuring that `async def @cleanup` methods are properly awaited during application teardown.

### Changed
- **Internal Cleanup:** Removed the deprecated `max_scopes_per_type` parameter from `ScopedCaches`, reflecting the removal of LRU eviction in v2.1.3.

### Docs 📚
- **Major Restructuring:** Rebuilt `mkdocs.yml` navigation to include all available documentation pages.
- **New Content:** Added missing guides for **Integrations** (Celery), **Advanced Features** (Self-Injection, AOP Proxies, Custom Scanners), and **Architecture** (Runtime Model).
- **Corrections:** Fixed discrepancies in asset filenames (`extra.js`) and standardized the format of Architecture Decision Records (ADRs).

---

## [2.1.3] - 2025-11-18

### Fixed
- **Critical:** Removed unsafe LRU eviction in `ScopedCaches`. Previously, under high concurrency (e.g., >2048 requests/websockets), active scopes could be evicted, causing data loss and premature cleanup. Scopes now persist until explicitly cleaned up.
- **Critical:** Fixed a race condition in `UnifiedComponentProxy` (AOP) where the underlying object creation wasn't fully thread-safe.
- **Critical:** Fixed a race condition in `EventBus.post()` where the queue reference could be lost during shutdown.
- **Critical:** Fixed `ScopeManager` returning a bucket for `None` IDs, which could cause state leakage between threads/tasks outside of an active context. Now raises `ScopeError`.
- Fixed `AsyncResolutionError` when accessing `lazy=True` components that require asynchronous `@configure` methods. `aget()` now hydrates proxies immediately if needed.
- Fixed a swallowed exception in `analyze_callable_dependencies` that hid configuration errors. Now logs debug information.
- Fixed recursion error in `UnifiedComponentProxy.__setattr__` when setting internal attributes.

### Changed
- **Breaking Behavior:** Users using `pico-fastapi` or manual scope management **must** ensure `container.cleanup_scope(...)` is called at the end of the lifecycle to prevent memory leaks, as the automatic LRU safety net has been removed in favor of data integrity.
- Improved integer configuration parsing to support formats like `1_000` or scientific notation in `config_runtime.py`.
- `init()` now fails fast with an `AsyncResolutionError` if a component returns an awaitable from a synchronous `@configure` method, instead of just logging a warning.

### Added
- Architectural support for asynchronous hydration of lazy proxies via `_async_init_if_needed`.

---

## [2.1.2] - 2025-11-10

### Added ✨

* **Collection & Mapping Injection:** Constructors can now request collection-like dependencies and dictionaries:

  * Supported collection origins: `List`, `Set`, `Iterable`, `Sequence`, `Collection`, `Deque` (resolved as concrete **lists** at injection time).
  * Supported mappings: `Dict[K, V]` / `Mapping[K, V]` where `K ∈ {str, type, Any}` and `V` is a component/protocol.
  * `Annotated[..., Qualifier("q")]` on the element type is honored for both collections and dict values.
* **Element-type analysis for dicts:** Dependency analysis records the dict key type and value element type for correct resolution.

### Changed

* **Analyzer:** `analyze_callable_dependencies` now recognizes a broader set of `collections.abc` origins for collections and supports dict/mapping shapes, including qualifier propagation from `Annotated` element types.
* **Container:** Dictionary injection computes keys from component metadata:

  * `Dict[str, V]` → uses `pico_name` (or string key/fallback to class `__name__`).
  * `Dict[type, V]` → uses the concrete class (or provided type).
  * `Dict[Any, V]` → chooses sensible defaults (`pico_name` → string key → class name).
* **Type imports & internals:** Expanded typing/runtime imports to support the new analysis and resolution paths.

### Fixed 🧩

* **Protocol matching:** `ComponentLocator` now checks attribute presence (including annotated attributes), reducing false positives when matching `Protocol` types.
* **Resolution guard:** `_resolve_args` safely no-ops when the locator is unavailable, avoiding edge-case errors during early initialization.

### Docs 📚

* **README:** Removed the deprecated *Integrations* entry from the docs index.
* **Architecture:** Corrected ADR links to `../adr/README.md` and references to the ADR workflow.

### Tests 🧪

* **New:** `tests/test_collection_injection.py` covering:

  * Analyzer plans for collections/dicts (including qualifiers).
  * Container resolution of lists/sets/iterables/sequences/deques as lists.
  * Dictionary injection for `Dict[str, V]` and `Dict[type, V]`.

---

## [2.1.1] - 2025-11-02

### Added

* ✨ Inline Field Overrides: Added support for overriding configuration fields directly in `@configured` classes using `Annotated[..., Value(...)]` (documented in ADR-0010).
* Container Self-Injection: `PicoContainer` is now registered as a singleton and can be injected into other components.
* Flexible `@provides`: `@provides` now supports module-level functions, `@staticmethod`, and `@classmethod` (ADR-0009), allowing for stateless providers without requiring a `@factory` instance.
* New `websocket` Scope: Added a new default scope named `websocket` to the `ScopeManager`, based on `contextvars`.

### Changed

* Simplified `custom_scopes` API: `init(custom_scopes=...)` now accepts an `Iterable[str]` of scope names (instead of a dict), automatically registering them as `ContextVarScope`.
* Strict Async Validation (Singletons): `init()` will now raise a `ConfigurationError` if a non-lazy (eager) singleton requires an async `@configure` method. This forces the developer to either use `aget()` or mark the component as `lazy=True`.
* Async Validation (Other Scopes): Components with other scopes (e.g., `request`) that have an async `@configure` will now raise an `AsyncResolutionError` if retrieved with `get()` (sync) but will resolve correctly with `aget()` (async).

### Fixed

* EventBus Thread-Safety: Fixed a bug to ensure `EventBus.post()` is fully thread-safe and correctly handles the worker's event loop context.
* Lazy Proxy and Async: The `UnifiedComponentProxy` (used for `lazy=True`) now correctly detects async `@configure` methods and raises an `AsyncResolutionError` if resolved synchronously.
* Python Version: Updated `requires-python` to `>=3.10` to reflect actual dependencies (like `contextvars` and `typing.Annotated`) and prevent installation errors.
* Internal Wiring: Cleaned up the import flow and internal logic in `api.init()` and `registrar.finalize()`.

### Docs

* User Guide & ADRs: Updated all documentation (User Guide, Glossary, ADRs) to reflect the unified configuration API (ADR-0010), removing all references to the old `@configuration` decorator.
* API Reference: Updated the `init()` signature in `container.md` to show the change to `custom_scopes` and document the `validate_only` and `observers` parameters.
* Simplified `architecture/comparison.md` and corrected minor errors.

### Tests

* Added `test_container_self_injection.py` to verify container self-injection.
* Updated assertions in log and stats tests to reflect new eager initialization and scope semantics.

---

## [2.1.0] - 2025-10-28

### Added ✨

* Unified Configuration Builder (`configuration(...)`): Introduced a new top-level function `configuration(...)` that accepts various sources (`EnvSource`, `DictSource`, `JsonTreeSource`, `YamlTreeSource`, `FlatDictSource`, etc.) and `overrides` to produce an immutable `ContextConfig` object. This centralizes configuration definition and precedence rules (ADR-0010).
* `ContextConfig` Object: A new object encapsulating the fully processed configuration state, passed to `init(config=...)`.
* Enhanced `@configured` Decorator:
    * Added `mapping: Literal["auto", "flat", "tree"]` parameter to explicitly control binding strategy.
    * Implemented `"auto"` detection: uses `"tree"` if any field is complex (dataclass, list, dict, Union), otherwise uses `"flat"`.
    * Supports unified normalization rules for keys (e.g., `ENV_VAR_NAME` <-> `field_name`, `ENV_VAR__NESTED` <-> `parent.nested`).
    * Integrates seamlessly with both flat and tree sources managed by `ContextConfig`.

### Changed ⚠️

* `init()` Signature: The `config` and `tree_config` parameters have been removed. Configuration is now passed solely through the new `config: Optional[ContextConfig]` parameter (ADR-0010).
* Configuration Precedence: Configuration loading and precedence are now strictly defined by the order of sources passed to the `configuration(...)` builder, followed by its `overrides` parameter, and finally `Annotated[..., Value(...)]` (ADR-0010).

### Removed ❌

* `@configuration` Decorator: This decorator, previously used for flat key-value binding, has been completely removed in favor of the unified `@configured` decorator (ADR-0010).
* Separate `config` (flat) and `tree_config` arguments in `init()`.

### Documentation 📚

* Updated all documentation (User Guide, API Reference, Examples, ADRs) to reflect the unified configuration system based on `@configured`, `configuration(...)`, and `ContextConfig`.
* Added `docs/specs/spec-configuration.md` detailing the unified configuration rules.
* Added migration notes related to removing `@configuration`.

### Breaking Changes ⚠️

* This release introduces significant breaking changes related to configuration management, requiring migration from the old `@configuration` decorator and `init()` arguments to the new `@configured` modes and `configuration(...)` builder (ADR-0010).

---

## [2.0.3] - 2025-10-26

### Fixed

- Injection now falls back from an annotated key to the parameter name when the annotated key is unbound, enabling resolution against string-key providers registered via `@provides("name")`.
- `ProviderNotFoundError` includes the requesting origin (component or key) to aid debugging and test assertions.
- Unified sync/async resolution path in `PicoContainer`:
  - `get()` raises `AsyncResolutionError` if a provider returns an awaitable, guiding users to `aget()`.
  - `aget()` awaits awaitables and applies aspects and caching consistently.
  - Observers receive accurate resolve timings in both paths.

### Added

- `AsyncResolutionError` to signal misuse of `get()` when a provider is async.
- More informative tracer notes for parameter binding.

### Internal

- `ComponentFactory.get()` now accepts an `origin` to enrich `ProviderNotFoundError` messages.
- Lazy proxy creation calls `factory.get(key, origin="lazy")` to attribute provenance.
- Public API exports updated to include `AsyncResolutionError`.

### Compatibility

- No public API breaking changes. Internal factory signature changed but remains encapsulated within the container/registrar.

---

## [2.0.2] - 2025-10-26

### Fixed 🧩

* `@provides` Decorator Execution
  Corrected an issue where the `@provides` decorator executed its wrapped function prematurely during module import, leading to runtime errors like `TypeError: Service() takes no arguments`.
  The decorator now properly registers provider metadata without invoking the function until dependency resolution time.

### Added ✨

* `FlatDictSource` Configuration Provider
  Introduced a lightweight configuration source for flat in-memory dictionaries.
  Supports optional key prefixing and case sensitivity control for simple, programmatic configuration injection.

### Internal 🔧

* Updated type imports and registration logic in `api.py` to support `Mapping` for the new configuration source.
* Added `FlatDictSource` to the public API (`__all__` and import namespace).

### Notes 📝

* Fully backward compatible.
* This patch release focuses on decorator correctness and configuration flexibility improvements.

---

## [2.0.1] - 2025-10-25

### Added ✨

- ADR-0009: Flexible `@provides` Support  
  Implemented support for using `@provides` in additional contexts:
  - `@staticmethod` methods within `@factory` classes  
  - `@classmethod` methods within `@factory` classes  
  - Module-level functions  
  These new provider types are discovered automatically during module scanning and participate fully in dependency resolution, validation, and graph generation.

- Dependency Graph and Validation Enhancements  
  - `_build_resolution_graph` now includes edges for all `@provides` functions, regardless of where they are defined.  
  - Fail-fast validation checks now cover static/class/module-level providers, reporting missing bindings consistently.  
  - Scope inference and promotion logic apply equally to these new provider types.

### Documentation 📚

- Expanded `docs/overview.md` to document the new flexible provider options (`@staticmethod`, `@classmethod`, module-level functions).  
- Updated `docs/guide.md` with practical examples showing when to use each style of provider.  
- Linked ADR-0009 for design rationale and migration guidance.

### Notes 📝

- This is a minor feature release introducing a major ergonomics improvement (ADR-0009).  
- Fully backward compatible with existing factories, components, and configuration mechanisms.  
- Encourages a lighter, more Pythonic style for simple provider declarations.


---

## [2.0.0] - 2025-10-23

This version marks a significant redesign and the first major public release, establishing the core architecture and feature set based on the principles outlined in the Architecture Decision Records (ADRs).

### 🚀 Highlights

* Async-Native Core: Introduced first-class `async`/`await` support across component resolution (`container.aget`), initialization (`__ainit__`), lifecycle hooks (`@configure`, `@cleanup`), AOP interceptors, and the event bus (ADR-0001).
* Tree-Based Configuration: Added `@configured` decorator and `TreeSource` protocol for binding complex, nested configuration (YAML/JSON) to dataclass graphs, including interpolation and type coercion (ADR-0002).
* Context-Aware Scopes: Implemented `contextvars`-based scopes (e.g., `"request"`, `"session"`) for managing component lifecycles tied to specific contexts (ADR-0003).
* Observability Features: Integrated container context (`container_id`, `as_current`), basic stats (`container.stats()`), observer protocol (`ContainerObserver`), and dependency graph export (`container.export_graph()`) (ADR-0004).
* Aspect-Oriented Programming (AOP): Implemented method interception via `MethodInterceptor` protocol and `@intercepted_by` decorator, using a dynamic proxy (`UnifiedComponentProxy`) (ADR-0005).
* Eager Startup Validation: Added fail-fast validation during `init()` to detect missing dependencies and configuration errors before runtime (ADR-0006).
* Built-in Event Bus: Included an asynchronous, in-process event bus (`EventBus`, `@subscribe`, `AutoSubscriberMixin`) for decoupled communication (ADR-0007).
* Explicit Circular Dependency Handling: Implemented detection and fail-fast for circular dependencies, requiring explicit resolution patterns (ADR-0008).
* Unified Decorator API: Consolidated component metadata into parameterized decorators (`@component`, `@factory`, `@provides`), removing older stacked decorators (ADR-0009).

### ✨ Added

* Core registration decorators: `@component`, `@factory`, `@provides`.
* Configuration decorators: `@configuration` (flat key-value) and `@configured` (tree-based).
* Lifecycle decorators: `@configure`, `@cleanup`.
* AOP decorator: `@intercepted_by`.
* Event bus decorator: `@subscribe`.
* Health check decorator: `@health`.
* Async resolution: `container.aget()` and `__ainit__` convention.
* Async cleanup: `container.cleanup_all_async()`.
* Qualifier support (`Qualifier` class) for list injection (`Annotated[List[Type], Qualifier(...)]`).
* Support for `lazy=True` parameter for deferred component instantiation.
* Conditional binding parameters (`conditional_profiles`, `conditional_require_env`, `conditional_predicate`).
* Fallback binding parameters (`on_missing_selector`, `on_missing_priority`).
* Primary selection parameter (`primary=True`).
* Testing support via `init(overrides={...})` and `init(profiles=(...))`.
* Container context management (`as_current`, `get_current`, `shutdown`, `all_containers`).
* Scope management API (`activate_scope`, `deactivate_scope`, `scope` context manager).
* Configuration sources: `EnvSource`, `FileSource` (flat); `JsonTreeSource`, `YamlTreeSource`, `DictSource` (tree).
* Protocols for extension: `MethodInterceptor`, `ContainerObserver`, `ScopeProtocol`, `ConfigSource`, `TreeSource`.

### ⚠️ Breaking Changes

* Complete redesign compared to any prior internal/unreleased versions. APIs are not backward compatible.
* Requires Python 3.10+.

### 📚 Docs

* Established new documentation structure including ADRs, Architecture, User Guide, Advanced Features, Cookbook, Integrations, and API Reference.

### 🧪 Testing

* Added comprehensive test suite covering core features, async behavior, AOP, configuration, scopes, and error handling.
* Introduced patterns for testing with overrides and profiles.

---

## [<2.0.0]

* Internal development and prototyping phase. Basic dependency injection concepts established. Architecture significantly reworked for the v2.0.0 release.


---
