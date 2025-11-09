# Decorators Reference

This page provides a quick reference for all decorators provided by `pico-ioc`.

---

## Core Registration Decorators: `@component`, `@factory`, `@provides`

These decorators register classes and functions as providers within the container. They share common parameters for lifecycle, selection, and conditional registration.

### `@component(cls=None, *, ...)`

Marks a class as a component managed by the container. Typically applied directly on the class.

- `cls`: The class being decorated (applied automatically when used as `@component`).

Example:
- Register a service class as a singleton component.

### `@factory(cls=None, *, ...)`

Marks a class as a factory for creating other components. Methods inside the factory should use `@provides`. The factory itself is a component and can declare dependencies.

- `cls`: The factory class being decorated.

Example:
- A factory class providing multiple implementations via `@provides`.

### `@provides(*args, **kwargs)`

Marks a function or method as the provider for a specific Key. Can be applied to module-level functions or methods within a `@factory` class (instance methods or `@staticmethod`).

- `key` (optional positional): The Key (class type or string) the method provides. If omitted, it is typically inferred from the function’s return type hint.
- `**kwargs`: Accepts the common parameters listed below.

Example:
- A provider function returning a configured client instance.

### Common parameters for `@component`, `@factory`, `@provides`

- `name: str | None` (default `None`)
  - Explicit component name/key. Defaults to class name or inferred `key` for `@provides`.
- `qualifiers: Iterable[str]` (default `()`)
  - Qualifier tags for disambiguation, especially when injecting lists (e.g., `Annotated[List[Type], Qualifier(...)]`).
- `scope: str` (default `"singleton"`)
  - Component lifetime: `"singleton"`, `"prototype"`, `"request"`, `"session"`, `"transaction"`, or a custom scope supported by your container configuration.
- `primary: bool` (default `False`)
  - Marks this component as the preferred candidate when multiple providers match a type.
- `lazy: bool` (default `False`)
  - Defers singleton instantiation until first use (`get`/`aget`).
- `conditional_profiles: Iterable[str]` (default `()`)
  - Enables the component only if one of the specified profiles is active (as configured via `init(profiles=...)`).
- `conditional_require_env: Iterable[str]` (default `()`)
  - Enables the component only if all specified environment variables exist and are non-empty.
- `conditional_predicate: Callable[[], bool] | None` (default `None`)
  - Custom function returning `True`/`False` to control conditional activation.
- `on_missing_selector: str | type | None` (default `None`)
  - Registers this component only if no other provider for the `selector` key/type is found. Acts as a fallback.
- `on_missing_priority: int` (default `0`)
  - Priority for `on_missing` providers when multiple fallbacks target the same selector (higher wins).

---

## Configuration Decorator

### `@configured(target: Any = "self", *, prefix: str = "", mapping: str = "auto")`

Marks a `dataclass` as a configuration object to be populated from the unified configuration system defined via `init(config=ContextConfig(...))` (created by the `configuration(...)` builder). Supports both flat (key-value) and tree (nested) mapping.

- `target` (optional): The class to be configured. Defaults to `"self"` (the decorated class itself).
- `prefix`:
  - Flat mapping: A prefix prepended to field names when looking up keys (e.g., with `prefix="APP_"` and field `host`, look up `APP_HOST`).
  - Tree mapping: The top-level key in the configuration tree to map from (e.g., `prefix="app"` maps from an `app:` section). If empty (`""`), maps from the root.
- `mapping`:
  - `"auto"` (default):
    - If any field type is a `dataclass`, `list`, `dict`, or `Union`, treat as tree.
    - If all field types are primitives (`str`, `int`, `float`, `bool`), treat as flat.
  - `"flat"`: Forces flat mapping. Keys are looked up as `PREFIX_FIELDNAME` (commonly UPPER_CASE in sources like environment variables).
  - `"tree"`: Forces tree mapping. Expects a nested structure under `prefix`. Path segments in env-like sources are joined by `__` (e.g., `APP_DB__HOST`).

This decorator works with the `configuration(...)` builder, which defines sources and precedence rules for populating the dataclass.

---

## Lifecycle Decorators

### `@configure(fn)`

Marks a method on a component to be called immediately after the component instance is created and dependencies are injected (including after `__ainit__` if present), but before it is returned by `get`/`aget`. The method may be synchronous or `async def`.

Typical uses:
- Validate configuration and dependencies.
- Initialize derived state or open connections.

### `@cleanup(fn)`

Marks a method on a component to be called when `container.cleanup_all()` or `container.cleanup_all_async()` is invoked. Use this to release resources (e.g., close connections, flush buffers). The method may be synchronous or `async def`.

---

## Health & AOP Decorators

### `@health(fn)`

Marks a method on a component as a health check. These methods are executed by `container.health_check()`. The method should take no arguments (besides `self`) and return a truthy value or raise an exception on failure. Can be synchronous or `async def`.

Use cases:
- Verify connectivity to external systems.
- Check internal invariants.

### `@intercepted_by(*interceptor_classes: type[MethodInterceptor])`

Applies one or more AOP interceptors (which must be registered components) to a method. Interceptors run before and/or after the original method, forming a chain.

- `*interceptor_classes`: The class types of the `MethodInterceptor` components to apply.

Common patterns:
- Logging and metrics collection.
- Transaction or retry policies.
- Authorization checks.

---

## Event Bus Decorator

### `@subscribe(event_type: Type[Event], *, priority: int = 0, policy: ExecPolicy = ExecPolicy.INLINE, once: bool = False)`

Marks a method (often within a class using `AutoSubscriberMixin`) to be called when an event of the specified type is published on the EventBus. The handler can be synchronous or `async def`.

- `event_type`: The specific `Event` subclass to listen for.
- `priority` (default `0`): Higher numerical priority handlers run first.
- `policy` (default `ExecPolicy.INLINE`): Controls execution strategy:
  - `ExecPolicy.INLINE`: Run synchronously in the publisher’s context (awaited if async).
  - `ExecPolicy.TASK`: Run as a background `asyncio.Task` (fire-and-forget).
  - `ExecPolicy.THREADPOOL`: Run synchronous handlers in a thread pool executor.
- `once` (default `False`): If `True`, the handler runs only once and is then automatically unsubscribed.

Typical uses:
- React to domain events.
- Fire side effects in response to state changes.
- Decouple producers and consumers.
