# Decorators Reference

This page provides a quick reference for all decorators provided by `pico-ioc`.

---

## **Core Registration Decorators: `@component`, `@factory`, `@provides`**

These decorators are used to register your classes and methods as providers for components within the container. They share many common parameters for controlling lifecycle, selection, and conditional registration.

### `@component(cls=None, *, ...)`

Marks a class as a component to be managed by the container. This is the most common decorator.
* **`cls`**: The class being decorated (usually applied automatically).

### `@factory(cls=None, *, ...)`

Marks a class as a factory for creating other components. Factory methods should use `@provides`. The factory itself becomes a component and can have dependencies.
* **`cls`**: The factory class being decorated (usually applied automatically).

### `@provides(key: Any, *, ...)`

Marks a method *inside* a `@factory` class as the provider for a specific **Key**.
* **`key`**: The **Key** (class type or string) that this method provides an instance for.

### Common Parameters for `@component`, `@factory`, `@provides`

| Parameter                 | Type                         | Default       | Description                                                                                             | Applies To            |
| :------------------------ | :--------------------------- | :------------ | :------------------------------------------------------------------------------------------------------ | :-------------------- |
| `name`                    | `str \| None`                | `None`        | Optional explicit component name/key. Defaults to class name or `key` for `@provides`.                   | All                   |
| `qualifiers`              | `Iterable[str]`              | `()`          | Qualifier tags for disambiguation when injecting lists (`Annotated[List[Type], Qualifier(...)]`).        | All                   |
| `scope`                   | `str`                        | `"singleton"` | Component lifetime: `"singleton"`, `"prototype"`, `"request"`, `"session"`, `"transaction"`, or custom. | All                   |
| `primary`                 | `bool`                       | `False`       | Marks this component as the preferred candidate when multiple implementations match a type.              | All                   |
| `lazy`                    | `bool`                       | `False`       | Defers singleton instantiation until first use (`get`/`aget`).                                            | All                   |
| `conditional_profiles`    | `Iterable[str]`              | `()`          | Enables the component only if one of the specified profiles is active (`init(profiles=...)`).             | All                   |
| `conditional_require_env` | `Iterable[str]`              | `()`          | Enables the component only if all specified environment variables exist and are non-empty.              | All                   |
| `conditional_predicate`   | `Callable[[], bool] \| None` | `None`        | Custom function returning `True`/`False` to control conditional activation.                             | All                   |
| `on_missing_selector`     | `str \| type \| None`        | `None`        | Registers this component only if no other provider for the `selector` key/type is found. Acts as a fallback. | `@component`, `@factory` |
| `on_missing_priority`     | `int`                        | `0`           | Priority for `on_missing` providers when multiple fallbacks target the same selector (higher wins).   | `@component`, `@factory` |

---

## **Configuration Decorators**

### `@configuration(cls=None, *, prefix: Optional[str] = None)`

Marks a `dataclass` as a configuration object to be populated from flat key-value `ConfigSource`s (like `EnvSource`).
* **`prefix`**: (Optional) A prefix added to the dataclass field names when looking up keys (e.g., `prefix="APP_"` looks for `APP_DEBUG` for field `DEBUG`).

### `@configured(target: Any, *, prefix: Optional[str] = None)`

Registers a provider that binds a nested configuration tree (from `TreeSource`s like `YamlTreeSource`) to a target `dataclass` or class graph.
* **`target`**: The root `dataclass` or class type to instantiate and populate.
* **`prefix`**: The top-level key in the configuration tree to map from (e.g., `"app"` for an `app:` section in YAML). If `None`, maps from the root.

---

## **Lifecycle Decorators**

### `@configure(fn)`

Marks a method on a component to be called immediately *after* the component instance is created and dependencies are injected (including after `__ainit__` if present), but before it's returned by `get`/`aget`. Can be `async def`.

### `@cleanup(fn)`

Marks a method on a component to be called when `container.cleanup_all()` or `container.cleanup_all_async()` is invoked. Used for releasing resources (e.g., closing connections). Can be `async def`.

---

## **Health & AOP Decorators**

### `@health(fn)`

Marks a method on a component as a health check. These methods are executed by `container.health_check()`. The method should take no arguments (except `self`) and return a truthy value or raise an exception on failure.

### `@intercepted_by(*interceptor_classes: type[MethodInterceptor])`

Applies one or more AOP **Interceptors** (which must be registered components themselves) to a method. The interceptors run before and after the original method call, forming a chain.
* **`*interceptor_classes`**: The class types of the `MethodInterceptor` components to apply.

---

## **Event Bus Decorator**

### `@subscribe(event_type: Type[Event], *, priority: int = 0, policy: ExecPolicy = ExecPolicy.INLINE, once: bool = False)`

Marks a method (usually within an `AutoSubscriberMixin` class) to be called when an event of the specified type is published on the `EventBus`. Can be `async def`.
* **`event_type`**: The specific `Event` subclass to listen for.
* **`priority`**: (Optional) Handlers with higher numerical priority run first. Default `0`.
* **`policy`**: (Optional) Controls execution strategy:
    * `ExecPolicy.INLINE` (Default): Handler runs synchronously in the publisher's context (awaited if async).
    * `ExecPolicy.TASK`: Handler runs as a background `asyncio.Task` ("fire and forget").
    * `ExecPolicy.THREADPOOL`: Sync handler runs in a thread pool executor.
* **`once`**: (Optional) If `True`, the handler runs only once and is then automatically unsubscribed.

