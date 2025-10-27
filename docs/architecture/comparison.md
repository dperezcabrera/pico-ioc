# Comparison to Other Libraries

Choosing a dependency injection (DI) framework for Python involves considering different philosophies and feature sets. `pico-ioc` makes specific design choices (as outlined in [Design Principles](./design-principles.md)) that differentiate it from other popular libraries like `dependency-injector`, `punq`, or the DI mechanism built into web frameworks like FastAPI.

This comparison helps you understand `pico-ioc`'s strengths and typical use cases relative to alternatives.

---

## Feature Comparison Matrix

| Feature                 | pico-ioc          | dependency-injector | punq             | FastAPI `Depends`   |
| :------------------------ | :---------------: | :-----------------: | :--------------: | :---------------: |
| **Primary Style** | Decorators + TH¹  | Declarative Code² | Decorators + TH¹ | Function Wrappers |
| **Type Hint Based** | ✅ Yes            | ⚠️ Partial³       | ✅ Yes           | ✅ Yes            |
| **Startup Validation** | ✅ Yes (Eager)    | ❌ No (Runtime)   | ❌ No (Runtime)  | ❌ No (Runtime)   |
| **Circular Dep. Check** | ✅ Yes (Startup)  | ✅ Yes (Runtime)  | ✅ Yes (Runtime) | ✅ Yes (Runtime)  |
| **Async Support** | ✅ Native (`aget`) | ✅ Yes⁴           | ❌ No            | ✅ Native         |
| **AOP (Interceptors)** | ✅ Built-in       | ❌ No             | ❌ No            | ❌ No             |
| **Scopes (Singleton)** | ✅ Yes            | ✅ Yes            | ✅ Yes           | ✅ Yes⁵           |
| **Scopes (Prototype)** | ✅ Yes            | ✅ Yes            | ✅ Yes           | ✅ Via `use_cache=False` |
| **Scopes (ContextVar)** | ✅ Built-in       | ✅ Yes            | ❌ No            | ✅ Native (Request)|
| **Configuration Binding** | ✅ Unified Tree+Flat | ✅ Basic (KV)     | ❌ Manual        | ❌ Manual         |
| **Qualifiers/Tags** | ✅ Yes            | ✅ Yes (Providers) | ❌ No            | ❌ No             |
| **List Injection** | ✅ Yes (`Annotated`) | ✅ Yes (`List`)   | ❌ No            | ⚠️ Manual⁶       |
| **Lazy Loading (`lazy`)** | ✅ Built-in       | ✅ Yes            | ❌ No            | ❌ No             |
| **Conditional Binding** | ✅ Full (Profile+) | ✅ Basic (Config) | ❌ No            | ❌ No             |
| **Observability (Context)**| ✅ Built-in       | ❌ Manual         | ❌ Manual        | ❌ Manual         |
| **Observability (Stats)** | ✅ Built-in       | ❌ Manual         | ❌ Manual        | ❌ Manual         |
| **Testing Overrides** | ✅ `init(overrides)` | ✅ Yes            | ✅ Yes           | ✅ Via `dependency_overrides` |
| **Python Version** | 3.10+           | 3.7+            | 3.7+           | 3.7+            |

**Notes:**
¹ Relies heavily on decorators applied directly to classes/methods and uses type hints for injection.
² Primarily uses declarative Python code (often in separate `containers.py` files) to define providers and wiring.
³ `dependency-injector` can use type hints but doesn't rely on them as the primary mechanism for resolution; its provider syntax is central.
⁴ `dependency-injector` supports async providers, but core resolution and lifecycle management might have nuances compared to a fully async-native design.
⁵ FastAPI `Depends` caches results per-request by default, effectively acting as a request-scoped singleton.
⁶ List injection in FastAPI typically requires manual aggregation or custom dependency logic.

---

## Philosophical Differences & Use Cases

### `pico-ioc`

* **Focus:** Startup safety, async-native, AOP, observability, advanced unified configuration, modern Python (3.10+).
* **Philosophy:** Inspired by robust enterprise frameworks (like Spring/Guice), prioritizing early error detection (fail-fast validation), explicit configuration via decorators and type hints, and built-in support for complex application patterns (async, AOP, context management). Treats DI as a core architectural tool for the entire application.
* **Strengths:**
    * **Startup Safety:** Catches most wiring errors (`InvalidBindingError`, `CircularDependencyError`) before runtime.
    * **Async Native:** Seamless integration with `asyncio` across resolution (`aget`), lifecycle (`__ainit__`, async cleanup), and AOP.
    * **AOP:** Built-in method interception (`@intercepted_by`) for cross-cutting concerns.
    * **Unified Configuration:** Powerful `@configured` binding handling both flat (ENV-like) and tree (YAML/JSON) sources via `configuration(...)` builder, with clear precedence and normalization rules. # <-- UPDATE THIS POINT
    * **Observability:** Designed for monitoring via `stats()`, `ContainerObserver`, and `container_id` context.
* **Weaknesses:**
    * Requires Python 3.10+.
    * Feature set might be overkill for very simple scripts.
    * Relies heavily on decorators, which might not suit all style preferences.
* **Best For:** Medium-to-large applications, async web services (FastAPI/Flask), microservices, systems where reliability, testability, and maintainability are crucial, applications needing AOP or complex, unified configuration patterns.

### `dependency-injector`

* **Focus:** Flexibility, declarative provider configuration, maturity, broad Python version support.
* **Philosophy:** Provides a flexible, code-based declarative system for defining providers and their relationships, often centralized in dedicated container modules. Less emphasis on direct decoration of business logic classes.
* **Strengths:**
    * Mature, widely adopted, and stable.
    * Supports Python 3.7+.
    * Flexible provider types (Factory, Singleton, Configuration, etc.).
    * Good support for various scopes.
* **Weaknesses:**
    * Wiring errors typically occur at runtime when a dependency is first accessed.
    * Can lead to boilerplate code in container definition files.
    * Lacks built-in AOP and the unified tree/flat configuration binding found in `pico-ioc` post-ADR-0010.
* **Best For:** Projects preferring explicit, centralized wiring definitions separate from business logic, applications needing Python 3.7-3.9 support, situations where runtime error detection is acceptable.

### `punq`

* **Focus:** Simplicity, minimalism, type-hint driven.
* **Philosophy:** Aims for a minimal API surface, relying almost entirely on type hints for dependency resolution with basic decorators for registration.
* **Strengths:**
    * Very easy to learn and use for basic DI.
    * Clean integration with type hints.
    * Supports Python 3.7+.
* **Weaknesses:**
    * Lacks many advanced features found in `pico-ioc` or `dependency-injector` (e.g., advanced scopes, async support, AOP, configuration binding, qualifiers, conditional registration, startup validation).
    * Errors occur at runtime.
* **Best For:** Smaller applications or scripts where only basic constructor injection is needed and advanced container features are unnecessary.

### FastAPI `Depends` (Framework-Native DI)

* **Focus:** Web request dependencies, request lifecycle integration.
* **Philosophy:** Specifically designed to inject dependencies *into FastAPI route handlers*, managing resources tied to the lifespan of an HTTP request (path params, request body, headers, request-scoped services).
* **Strengths:**
    * Seamless integration with the FastAPI framework and request lifecycle.
    * Excellent for handling web-specific dependencies (request data, security credentials).
    * Naturally supports `async` dependencies within routes.
* **Weaknesses:**
    * Not intended for managing application-wide singletons or complex object graphs outside the web layer.
    * Lacks features like AOP, qualifiers, advanced conditional logic, application-wide startup validation, or sophisticated configuration binding. # <-- MAYBE UPDATE THIS POINT
    * Can tightly couple business logic to the web framework if used exclusively for all layers of the application.
* **Best For:** Managing dependencies directly related to the HTTP request/response cycle within FastAPI applications. Often used *in conjunction* with a dedicated application-layer DI container like `pico-ioc`, where FastAPI handles route injection and `pico-ioc` manages deeper service and repository layers.

---

## Conclusion

`pico-ioc` is designed for developers building complex, modern Python applications who value **startup safety**, **native async support**, **testability**, and **advanced features** like AOP and structured, unified configuration. Its emphasis on fail-fast validation and observability makes it particularly well-suited for production-grade systems where reliability and maintainability are paramount. It requires Python 3.10+ due to its reliance on modern `typing` features.

---

## Next Steps

This concludes the Architecture section. Explore the API Reference for detailed documentation on specific functions and decorators.

* **[API Reference Overview](../api-reference/README.md)**: Quick lookup for all public APIs.

