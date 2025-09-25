# ADR-003: Context-Aware Scopes 🌐

**Status:** Accepted

## Context

Many applications, especially web services, need components whose lifecycle is tied to a specific **context**, like an individual HTTP request or a user's session. Imagine needing a unique `UserContext` object for each logged-in user making requests simultaneously. The standard **`singleton`** (one instance forever) and **`prototype`** (new instance every time) scopes aren't suitable for managing state within these temporary contexts. We needed a way to create "scoped singletons" – ensuring exactly **one instance per active context**. 👨‍💻👩‍💼

---

## Decision

We introduced **context-aware scopes** built upon Python's **`contextvars`**:

1.  **`ScopeProtocol`:** Defined a minimal interface for custom scope implementations, requiring only `get_id() -> Any | None` to return the identifier of the *currently active* scope instance.
2.  **`ContextVarScope`:** Provided a standard implementation using `contextvars.ContextVar`. This allows tracking the active scope ID within async tasks and threads correctly. It includes helper methods like `activate(id)` and `deactivate(token)`.
3.  **`ScopeManager`:** An internal registry holding `ScopeProtocol` implementations for named scopes (e.g., `"request"`, `"session"`). It provides the core logic for activating, deactivating, and retrieving the current ID for any registered scope.
4.  **`scope="..."` Parameter:** Components are assigned to a specific scope using the `scope` parameter within the main registration decorators (`@component`, `@factory`, `@provides`). For example: `@component(scope="request")`.
5.  **`ScopedCaches`:** Modified the internal caching mechanism to handle multiple caches keyed by `(scope_name, scope_id)`. It uses an LRU (Least Recently Used) strategy to automatically evict caches for older, inactive scope IDs, preventing memory leaks. 🧠💾
6.  **Container API:** Added convenient methods for managing scopes:
    * `container.activate_scope(name, id)` and `deactivate_scope(name, token)` for manual control.
    * The preferred `with container.scope(name, id):` **context manager** for easy, safe activation and deactivation within a block.
    * Pre-registered common web scopes like `"request"`, `"session"`, and `"transaction"` for convenience.

---

## Consequences

**Positive:** 👍
* Enables safe and isolated management of **context-specific state** (e.g., holding data for a single web request without interfering with others). ✅
* Integrates naturally with **`asyncio`** due to the use of `contextvars`, making it suitable for modern async web frameworks. 🔄
* Provides a clean and developer-friendly API for activating/deactivating scopes, especially the `with container.scope():` manager. ✨
* **Extensible:** Users can define and register their own custom scopes via `init(custom_scopes={...})`. 🔧

**Negative:** 👎
* Relies on **`contextvars`**, which requires careful handling, especially regarding context propagation across thread boundaries if not managed automatically by frameworks. 🤔
* Requires **explicit scope activation/deactivation** in the application's entry points (e.g., web middleware). `pico-ioc` itself doesn't automatically detect the start/end of a request; the framework integration needs to call the container's scope methods. 🚦
* Can potentially increase memory usage if a very large number of scope instances remain active simultaneously, although the `ScopedCaches` LRU mechanism helps mitigate this by discarding caches for inactive scope IDs. 📈📉

