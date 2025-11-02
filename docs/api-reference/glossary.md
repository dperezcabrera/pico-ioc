# Glossary

This glossary defines the core terms used within the `pico-ioc` framework and documentation.

---

## **Binding**
The act of associating a **Key** (like a class type or string name) with a specific **Provider** within the container during the `init()` process. This tells the container *how* to create an instance when that key is requested.

---

## **Component** 🧩
Any object managed by the `pico-ioc` container. Typically, these are your application's classes (services, repositories, controllers, etc.) registered using decorators like `@component` or created via a `@factory`.

---

## **Configuration Source** (`ConfigSource` / `TreeSource`) ⚙️
An object that provides configuration values. Sources are passed to the `configuration(...)` builder function to create a `ContextConfig`.
* **Flat Sources** (like `EnvSource`, `FlatDictSource`): Provide flat key-value pairs (e.g., `APP_PORT=8080`).
* **Tree Sources** (like `YamlTreeSource`, `JsonTreeSource`, `DictSource`): Provide nested configuration trees (e.g., from a YAML file).

---

## **Container** (`PicoContainer`) 📦
The main object that manages the lifecycle and dependencies of your components. It's created by `init()` and used to retrieve components via `get()` or `aget()`.

---

## **Container Context** 🌐
A mechanism (`contextvars`-based) that tracks which `PicoContainer` instance is currently "active" for a given thread or `asyncio` task. Managed via `with container.as_current()`. Crucial for multi-container patterns (like multi-tenant apps) and observability. Each container has a unique `container_id`.

---

## **Factory** 🏭
A class decorated with `@factory` whose methods (decorated with `@provides`) act as recipes for creating components. Used for complex instantiation logic or registering third-party objects.

---

## **Interceptor** (`MethodInterceptor`) 🎭
A component used for Aspect-Oriented Programming (AOP). It wraps around a method call (when applied via `@intercepted_by`) to add cross-cutting behavior (like logging, caching, or transaction management) before and after the original method executes.

---

## **Key** 🔑
An identifier used to request a component from the container. Usually a class type (e.g., `UserService`) or a string name (e.g., `"database_connection_string"`).

---

## **Observer** (`ContainerObserver`) 👀
A class that can be registered with the container (via `init(observers=[...])`) to listen for internal events like component resolution (`on_resolve`) or cache hits (`on_cache_hit`). Used for monitoring, metrics, and tracing.

---

## **Provider** 🛠️
A callable (function or object with `__call__`) stored internally by the container. When called, it produces an instance of a specific component. The `ComponentFactory` maps keys to providers.

---

## **Qualifier** (`Qualifier`)🏷️
A **string tag** used to differentiate between multiple components implementing the same interface or type. Qualifiers are applied using the `qualifiers=['TAG', ...]` parameter within the `@component`, `@factory`, or `@provides` decorators. They allow requesting a specific **filtered list** of components using `typing.Annotated[List[Interface], Qualifier('TAG')]`.

---

## **Resolution** 🔗
The process `pico-ioc` undertakes when you call `container.get(key)` or `aget(key)`. It involves finding the correct provider for the key, recursively resolving all its dependencies, creating the instance(s), and returning the final object.

---

## **Scope** ♻️
Determines the lifecycle and caching strategy for a component instance. Key scopes include:
* **`singleton`**: (Default) One instance per container. Created once and cached forever.
* **`prototype`**: A new instance is created *every time* the component is requested. Never cached.
* **`request`** (or `session`, etc.): One instance per active scope ID (e.g., per HTTP request). Cached for the duration of that scope.

