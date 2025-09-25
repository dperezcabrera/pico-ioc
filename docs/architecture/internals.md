# Internal Architecture Deep-Dive

This document describes the internal "How-it-works" of `pico-ioc`, intended for contributors and architects. It details the core components and algorithms that power the container.

---

## 1. Core Components

The framework is built from a few key internal components, all orchestrated by the `PicoContainer`.

```text
┌─────────────────────────────────────────────────────┐
│                 PicoContainer (Facade)              │
├─────────────────────────────────────────────────────┤
│ ComponentFactory  │  ScopedCaches  │  ScopeManager  │
├─────────────────────────────────────────────────────┤
│      ComponentLocator (Metadata) │  Registrar       │
├─────────────────────────────────────────────────────┤
│         ConfigResolver     │ ObjectGraphBuilder     │
├─────────────────────────────────────────────────────┤
│             UnifiedComponentProxy (AOP)             │
└─────────────────────────────────────────────────────┘
```


  * **`PicoContainer`**: The public API and facade. It orchestrates `get`/`aget` calls, manages scope and container contexts, and holds references to the other components.
  * **`Registrar`**: A short-lived object used only during `init()`. It scans modules, discovers all components, evaluates `@conditional` logic, and populates both the `ComponentFactory` and the `ComponentLocator`'s metadata.
  * **`ComponentFactory`**: A simple dictionary that stores the final "recipe" (a `Provider` callable, often a `DeferredProvider`) for creating each component.
  * **`ComponentLocator`**: An queryable index of all final component metadata. This is used for introspection and to resolve type-based or `Qualifier`-based list injections.
  * **`ConfigResolver` / `ObjectGraphBuilder`**: The engine for the `@configured` feature. They load, merge, and parse configuration trees (e.g., YAML/JSON) into `dataclass` graphs.
  * **`ScopeManager` / `ScopedCaches`**: Manages the lifecycle and storage of component instances. `ScopeManager` handles *which* scope is active (using `contextvars`), and `ScopedCaches` provides the *storage* for that scope (e.g., the singleton cache vs. a request-scope cache).
  * **`UnifiedComponentProxy`**: The dynamic proxy class used to implement `lazy` loading and AOP (`@intercepted_by`).

```mermaid
sequenceDiagram
    participant User
    participant Container
    participant Factory
    participant Registrar
    participant Proxy
    
    User->>Container: get(ServiceA)
    Container->>Container: Check cache
    alt Cache Miss
        Container->>Factory: Get provider for ServiceA
        Factory->>Registrar: Resolve dependencies
        Registrar->>Container: get(ServiceB)
        Container->>Factory: Get provider for ServiceB
        Factory-->>Container: ServiceB instance
        Container->>Proxy: Wrap if @intercepted_by
        Proxy-->>Container: Proxied ServiceB
        Container-->>Registrar: ServiceB ready
        Registrar->>Factory: Build ServiceA with ServiceB
        Factory-->>Container: ServiceA instance
        Container->>Cache: Store ServiceA
    else Cache Hit
        Container->>Cache: Return cached
    end
    Container-->>User: ServiceA instance
```

-----

## 2\. The Initialization Flow (`init()`)

When you call `init()`, the `Registrar` executes the following sequence:

1.  **Scan**: `_iter_input_modules` walks packages (if given) to find all modules for scanning.
2.  **Discover**: `Registrar.register_module` inspects every member of every module for decorators (`@component`, `@factory`, `@configured`, etc.).
3.  **Queue Candidates**: All discovered components are queued as *candidates* in `Registrar._candidates`. Conditional logic (`@conditional`) is evaluated here. Any component that fails its condition is discarded.
4.  **Select & Bind**: `Registrar.select_and_bind` iterates all candidates for each key. It selects the "best" one (respecting `primary` and `@configured` prefix-matching) and "binds" its `Provider` callable into the `ComponentFactory`.
5.  **Promote Scopes**: `_promote_scopes` runs to prevent scope-leaks (see below).
6.  **Apply Fallbacks**: `on_missing` components are registered *only if* their target key is still missing after the main binding phase.
7.  **Validate**: `_validate_bindings` performs a "dry run" of the dependency graph. It inspects all `__init__` and factory method dependencies and cross-references them with the `ComponentFactory` to ensure a provider exists for every required dependency. This is what enables **fail-fast** startup validation.
8.  **Finalize**: The `PicoContainer` is created and the finalized `ComponentFactory` and `ComponentLocator` (built from the final metadata) are attached to it.

-----

## 3\. The Resolution Algorithm (`get`/`aget`)

Resolution is handled by `PicoContainer.get(key)` and `aget(key)`.

1.  **Check Cache**: The container identifies the correct cache for the component's scope (e.g., `_singleton` cache, or the cache for `request:req-123`). If an instance exists, it's returned immediately.
2.  **Check Cycle**: The requested `key` is checked against the `_resolve_chain` (a `contextvars.ContextVar`). If the `key` is already in the chain, a `CircularDependencyError` is raised.
3.  **Push to Stack**: The `key` is added to the `_resolve_chain`.
4.  **Get Provider**: The `ComponentFactory.get(key)` is called to get the `Provider` callable (the "recipe").
5.  **Create Instance**:
      * The `Provider` is called. For `DeferredProvider`, this triggers the builder function.
      * The builder function (e.g., `_build_class`) calls `_resolve_args` to find dependencies for the component's `__init__` or factory method.
      * `_resolve_args` is **recursive**: it calls `pico.get()` for each dependency, starting this flow over at step 1.
      * For `aget`, if the provider or its `__ainit__` is a coroutine, it is `await`ed.
6.  **Wrap Proxy**: The new instance is passed to `_maybe_wrap_with_aspects` to wrap it in a `UnifiedComponentProxy` *only if* it has `@intercepted_by` methods or is `lazy`.
7.  **Put in Cache**: The (possibly proxied) instance is stored in the correct cache (from step 1).
8.  **Pop from Stack**: The `key` is removed from `_resolve_chain`.
9.  **Return Instance**.

-----

## 4\. Internals: Configuration Tree Binding

The `@configured` system, managed by `config_runtime.py`, is separate from the basic `@configuration` provider.

  * **`ConfigResolver`**: This class is initialized by `Registrar` with all discovered `TreeSource`s (e.g., `YamlTreeSource`). When first accessed, it:

    1.  Loads all sources (e.g., YAML files) into dictionaries.
    2.  Performs a deep merge of all dictionaries, in order.
    3.  Walks the entire merged tree to interpolate variables (e.g., `${ENV:VAR}` and `${ref:path.to.key}`).
    4.  Caches the final, resolved configuration tree.

  * **`ObjectGraphBuilder`**: This class is given the `ConfigResolver` and a target `type`. When its `build_from_prefix` method is called (by the component's provider):

    1.  It asks the `ConfigResolver` for the sub-tree at that `prefix`.
    2.  It recursively "walks" the target `type` (e.g., a `dataclass`) and the config sub-tree simultaneously.
    3.  It coerces all primitive values (str to int, str to bool, etc.).
    4.  It recursively builds nested `dataclass`es.
    5.  It correctly handles `List[...]`, `Dict[...]`, `Union[...]`, and `Annotated[Union[...], Discriminator(...)]` to build the complete object graph.

-----

## 5\. Internals: Scope Management

  * **`ScopeManager`**: A simple registry mapping scope names (e.g., `"request"`) to a `ScopeProtocol` implementation. For web scopes, it uses `ContextVarScope`, which wraps a `contextvars.ContextVar`.

      * `activate(scope_id)` calls `_var.set(scope_id)`.
      * `get_id()` calls `_var.get()`.

  * **`ScopedCaches`**: This class holds the actual component instances.

      * **`_singleton`**: A single `ComponentContainer` (a dict) for all `singleton` components.
      * **`_by_scope`**: A `dict` mapping scope names (e.g., `"request"`) to an `OrderedDict`.
      * This `OrderedDict` maps a *scope ID* (e.g., `"req-123"`) to its own `ComponentContainer`. It is used as an LRU cache to evict component caches from old, inactive scopes (e.g., old HTTP requests).

-----

## 6\. Internals: AOP & Lazy Loading

Both features are powered by the **`UnifiedComponentProxy`**.

  * **`lazy`**: When `get()` is called for a `lazy` component, the proxy is created *instead* of the real object.

      * `_target` is `None`.
      * `_creator` is the component's real provider function.
      * On the *first attribute access* (e.g., `proxy.some_method()`), `__getattr__` calls `_get_real_object()`.
      * `_get_real_object()` executes the `_creator`, saves the result to `_target`, and returns it.
      * All subsequent access hits the (now populated) `_target`.

  * **AOP**: When `get()` is called for a component with `@intercepted_by` methods, the real object is created, then wrapped by the proxy.

      * `_target` is set immediately to the real instance.
      * `_creator` is `None`.
      * On *every* attribute access, `__getattr__` is called.
      * If the attribute is a method with `_pico_interceptors_`, the proxy builds a wrapper function (using `dispatch_method`) that executes the interceptor chain and calls the original method.
      * If the attribute is not intercepted, it's returned directly from `_target`.

  * **Serialization**: `__reduce_ex__` is implemented to ensure that `pickle` serializes the *real object* (`_target`), not the proxy, allowing proxied objects to be sent across processes.

-----

## 7\. Internals: ComponentLocator

The `ComponentLocator` is an introspection tool built from the `Registrar`'s final metadata. It maintains several inverted indexes (as `dict`s) to allow for fast querying:

  * `"qualifier"`: `Qualifier` $\rightarrow$ `List[KeyT]`
  * `"primary"`: `bool` $\rightarrow$ `List[KeyT]`
  * `"infra"`: `str` $\rightarrow$ `List[KeyT]` (e.g., "component", "factory")

The fluent API (`.with_qualifier_any()`, etc.) and the list injection logic in `_resolve_args` use these indexes to perform fast lookups.

-----

## 8\. Advanced Internal Mechanisms

### 8.1. Automatic Scope Promotion

The `Registrar._promote_scopes` method prevents scope leaks (e.g., a `singleton` depending on a `request`-scoped object). It iterates all `singleton` components and inspects their dependencies. If a singleton depends on a component with a narrower scope (e.g., `request`), the singleton's *own* scope is automatically "promoted" to `request`.

### 8.2. Event Bus

The `EventBus` is registered as a normal component (from `pico_ioc.event_bus`). It maintains a dictionary mapping `Event` types to a sorted list of `_Subscriber` callables (found via `AutoSubscriberMixin`). The `publish` method iterates this list, handling `async` and sync subscribers and applying the `ExecPolicy` (e.g., running sync subscribers in a `ThreadPoolExecutor` or `asyncio.create_task` for `ExecPolicy.TASK`).

-----

## 9\. Design Patterns Used

  * **Inversion of Control (IoC)**: Container manages the lifecycle and wiring.
  * **Dependency Injection (DI)**: Constructor/method injection based on type hints.
  * **Service Locator**: `ComponentLocator` for querying, and `PicoContainer.get_current()` for contextual access.
  * **Proxy Pattern**: `UnifiedComponentProxy` for lazy loading and AOP.
  * **Chain of Responsibility**: Interceptor chain (`dispatch_method`).
  * **Factory Pattern**: `@factory` and `@provides`.
  * **Strategy Pattern**: Multiple implementations (e.g., `Database`) with `primary` selecting the default.
  * **Observer Pattern**: `ContainerObserver` for monitoring.
  * **Publisher/Subscriber**: The `EventBus`.

