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

### `@provides(*args, **kwargs)`

Marks a function or method as the provider for a specific **Key**. Can be used on module-level functions, or on methods within a `@factory` class (as instance methods or `@staticmethod`s).
* **`key`** (Optional, positional): The **Key** (class type or string) that this method provides an instance for. If omitted, it's often inferred from the return type hint.
* **`**kwargs`**: Accepts common parameters listed below.

### Common Parameters for `@component`, `@factory`, `@provides`

| Parameter                 | Type                          | Default       | Description                                                                                             | Applies To             |
| :------------------------ | :---------------------------- | :------------ | :------------------------------------------------------------------------------------------------------ | :--------------------- |
| `name`                    | `str \| None`                 | `None`        | Optional explicit component name/key. Defaults to class name or inferred `key` for `@provides`.         | All                    |
| `qualifiers`              | `Iterable[str]`               | `()`          | Qualifier tags for disambiguation when injecting lists (`Annotated[List[Type], Qualifier(...)]`).         | All                    |
| `scope`                   | `str`                         | `"singleton"` | Component lifetime: `"singleton"`, `"prototype"`, `"request"`, `"session"`, `"transaction"`, or custom. | All                    |
| `primary`                 | `bool`                        | `False`       | Marks this component as the preferred candidate when multiple implementations match a type.             | All                    |
| `lazy`                    | `bool`                        | `False`       | Defers singleton instantiation until first use (`get`/`aget`).                                          | All                    |
| `conditional_profiles`    | `Iterable[str]`               | `()`          | Enables the component only if one of the specified profiles is active (`init(profiles=...)`).             | All                    |
| `conditional_require_env` | `Iterable[str]`               | `()`          | Enables the component only if all specified environment variables exist and are non-empty.              | All                    |
| `conditional_predicate`   | `Callable[[], bool] \| None`  | `None`        | Custom function returning `True`/`False` to control conditional activation.                               | All                    |
| `on_missing_selector`   | `str \| type \| None`         | `None`        | Registers this component only if no other provider for the `selector` key/type is found. Acts as a fallback. | `@component`, `@factory` |
| `on_missing_priority`   | `int`                         | `0`           | Priority for `on_missing` providers when multiple fallbacks target the same selector (higher wins).     | `@component`, `@factory` |

---

## **Configuration Decorator**

### `@configured(target: Any, *, prefix: str = "", mapping: str = "auto")`

*(Note: In the code, `@configured` seems to decorate the class itself, not take a `target` argument directly. Assuming the code snippet in `src/pico_ioc/decorators.py` is the correct implementation.)*

```python
# Correct signature based on src/pico_ioc/decorators.py
def configured(target: Any = "self", *, prefix: str = "", mapping: str = "auto"):
    # Decorator factory returning the actual decorator
    def dec(cls): ...
    return dec
```

Marks a `dataclass` as a configuration object to be populated from the unified configuration system provided via `init(config=ContextConfig(...))` created by the `configuration(...)` builder. This single decorator handles both **flat** (key-value) and **tree** (nested) configuration mapping.

  * **`target`**: (Optional) The class type to be configured. Defaults to `"self"`, meaning the decorated class itself. *This parameter might be less relevant if the decorator is always applied directly to the target class.*
  * **`prefix`**:
      * For **`flat`** mapping: A prefix prepended to field names when looking up keys (e.g., `prefix="APP_"` with field `host` looks for `APP_HOST`).
      * For **`tree`** mapping: The top-level key in the configuration tree to map from (e.g., `prefix="app"` for an `app:` section in YAML). If empty (`""`), maps from the root.
  * **`mapping`**: Controls how configuration keys are mapped to the dataclass fields.
      * **`"auto"`** (Default):
          * If any field type is a `dataclass`, `list`, `dict`, or `Union`, treats as **`tree`**.
          * If all field types are primitives (`str`, `int`, `float`, `bool`), treats as **`flat`**.
      * **`"flat"`**: Forces flat mapping. Keys are looked up as `PREFIX_FIELDNAME` (typically in `UPPER_CASE` in sources like environment variables). Suitable for simple key-value sources.
      * **`"tree"`**: Forces tree mapping. Expects a nested structure under the `prefix`. Path segments in sources like environment variables are joined by `__` (e.g., `APP_DB__HOST`). Suitable for structured sources like YAML/JSON.

This decorator works in conjunction with the `configuration(...)` builder which defines the sources and precedence rules used to populate the dataclass.

-----

## **Lifecycle Decorators**

### `@configure(fn)`

Marks a method on a component to be called immediately *after* the component instance is created and dependencies are injected (including after `__ainit__` if present), but before it's returned by `get`/`aget`. Can be `async def`.

### `@cleanup(fn)`

Marks a method on a component to be called when `container.cleanup_all()` or `container.cleanup_all_async()` is invoked. Used for releasing resources (e.g., closing connections). Can be `async def`.

-----

## **Health & AOP Decorators**

### `@health(fn)`

Marks a method on a component as a health check. These methods are executed by `container.health_check()`. The method should take no arguments (except `self`) and return a truthy value or raise an exception on failure.

### `@intercepted_by(*interceptor_classes: type[MethodInterceptor])`

Applies one or more AOP **Interceptors** (which must be registered components themselves) to a method. The interceptors run before and after the original method call, forming a chain.

  * **`*interceptor_classes`**: The class types of the `MethodInterceptor` components to apply.

-----

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

