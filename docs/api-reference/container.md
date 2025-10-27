# `PicoContainer` API Reference

This page lists the public methods of the `PicoContainer` class and the top-level `init()` function.

---

## **`init()` Function**

This is the main entry point for creating and configuring a container.

```python
import logging # Added for type hint
from typing import Any, Iterable, Optional, Dict, Tuple, List, Union # Added necessary types
from pico_ioc import ScopeProtocol, ContainerObserver, PicoContainer # Assuming these are defined here
from pico_ioc.config_builder import ContextConfig # Correct import for ContextConfig

# Define KeyT for the signature
KeyT = Union[str, type]

def init(
    modules: Union[Any, Iterable[Any]],
    *,
    profiles: Tuple[str, ...] = (),
    allowed_profiles: Optional[Iterable[str]] = None,
    environ: Optional[Dict[str, str]] = None,
    overrides: Optional[Dict[KeyT, Any]] = None,
    logger: Optional[logging.Logger] = None,
    # MODIFIED: Unified config using ContextConfig
    config: Optional[ContextConfig] = None,
    custom_scopes: Optional[Dict[str, ScopeProtocol]] = None,
    validate_only: bool = False, # Added missing parameter
    container_id: Optional[str] = None,
    observers: Optional[List[ContainerObserver]] = None
) -> PicoContainer: ... # Added return type hint
```

  * **`modules`**: An iterable of modules or package names (strings) to scan for components.
  * **`profiles`**: A tuple of active profile names (e.g., `"prod"`, `"test"`). Used by conditional decorators.
  * **`allowed_profiles`**: (Optional) If set, raises `ConfigurationError` if any profile in `profiles` is not in this list.
  * **`environ`**: (Optional) A dictionary to use instead of `os.environ`. Used for testing conditionals.
  * **`overrides`**: (Optional) A dictionary mapping **Keys** to specific instances or provider functions, replacing any discovered components for those keys. Used primarily for testing.
  * **`logger`**: (Optional) A custom logger instance. Defaults to `pico_ioc.LOGGER`.
  * **`config`**: (Optional) A **`ContextConfig`** object created by the `configuration(...)` builder. This object encapsulates all configuration sources (like environment variables, files, dictionaries), overrides, and rules for mapping them to `@configured` classes. This replaces the previous separate `config` and `tree_config` arguments.
  * **`custom_scopes`**: (Optional) A dictionary mapping custom scope names (strings) to `ScopeProtocol` implementations.
  * **`validate_only`**: (Default: `False`) If `True`, performs all scanning and validation steps but returns a container without creating instances or running lifecycle methods. Useful for quick startup checks.
  * **`container_id`**: (Optional) A specific ID string to assign to this container. If `None`, a unique ID is automatically generated.
  * **`observers`**: (Optional) A list of objects implementing the `ContainerObserver` protocol. These observers will receive events like `on_resolve` and `on_cache_hit` for monitoring and tracing purposes.
  * **Returns**: A configured `PicoContainer` instance ready to resolve components.

-----

## **`PicoContainer` Instance Methods**

### `get(key: KeyT) -> Any`

Synchronously retrieves or creates a component instance for the given **Key**. Raises `ProviderNotFoundError` or `ComponentCreationError`. Caches instances based on scope.

  * **`key`**: The class type or string name of the component to retrieve.
  * **Returns**: The component instance.

-----

### `aget(key: KeyT) -> Any`

Asynchronously retrieves or creates a component instance for the given **Key**. Correctly handles `async def` providers and `__ainit__` methods. Raises `ProviderNotFoundError` or `ComponentCreationError`. Caches instances based on scope.

  * **`key`**: The class type or string name of the component to retrieve.
  * **Returns**: The component instance (awaitable).

-----

### `has(key: KeyT) -> bool`

Checks if a provider is registered for the given **Key** or if an instance exists in the cache for the current scope.

  * **`key`**: The class type or string name to check.
  * **Returns**: `True` if the key can be resolved, `False` otherwise.

-----

### `activate() -> contextvars.Token`

Manually activates this container in the current context. Returns a token needed for `deactivate()`. Prefer using `with container.as_current():`.

  * **Returns**: A `contextvars.Token` for restoring the context.

-----

### `deactivate(token: contextvars.Token) -> None`

Manually deactivates this container, restoring the previous context using the token from `activate()`.

  * **`token`**: The token returned by `activate()`.

-----

### `as_current() -> ContextManager[PicoContainer]`

Returns a context manager (`with container.as_current(): ...`) that activates this container for the duration of the `with` block. This is the preferred way to manage the **Container Context**.

  * **Yields**: The container instance (`self`).

-----

### `activate_scope(name: str, scope_id: Any) -> Optional[contextvars.Token]`

Activates a specific **Scope** (e.g., `"request"`) with a given ID. Returns a token if the scope uses `contextvars`. Prefer `with container.scope():`.

  * **`name`**: The name of the scope to activate (e.g., `"request"`).
  * **`scope_id`**: A unique identifier for this instance of the scope (e.g., a request ID string).
  * **Returns**: An optional `contextvars.Token`.

-----

### `deactivate_scope(name: str, token: Optional[contextvars.Token]) -> None`

Deactivates a specific **Scope** using the token returned by `activate_scope`.

  * **`name`**: The name of the scope to deactivate.
  * **`token`**: The token returned by `activate_scope`.

-----

### `scope(name: str, scope_id: Any) -> ContextManager[PicoContainer]`

Returns a context manager (`with container.scope("request", "id-123"): ...`) that activates a specific **Scope** for the duration of the `with` block. This is the preferred way to manage scopes like `"request"`.

  * **`name`**: The name of the scope to activate.
  * **`scope_id`**: A unique identifier for this scope instance.
  * **Yields**: The container instance (`self`).

-----

### `cleanup_all() -> None`

Synchronously calls all methods decorated with `@cleanup` on all cached singleton and scoped components managed by this container.

-----

### `cleanup_all_async() -> Awaitable[None]`

Asynchronously calls all methods decorated with `@cleanup` (including `async def` methods) on all cached components.

  * **Returns**: An awaitable.

-----

### `shutdown() -> None`

Performs a full shutdown:

1.  Calls `cleanup_all()`.
2.  Removes the container from the global registry (making it inaccessible via `PicoContainer.get_current()` or `all_containers()`).

-----

### `stats() -> Dict[str, Any]`

Returns a dictionary containing runtime statistics and metrics about the container (e.g., uptime, resolve counts, cache hit rate).

  * **Returns**: A dictionary of stats.

-----

### `health_check() -> Dict[str, bool]`

Executes all methods decorated with `@health` on cached components and returns a status report. Methods raising exceptions are reported as `False` (unhealthy).

  * **Returns**: A dictionary mapping `'ClassName.method_name'` to a boolean health status.

-----

### `export_graph(path: str, *, include_scopes: bool = True, include_qualifiers: bool = False, rankdir: str = "LR", title: Optional[str] = None) -> None`

Exports the container's component dependency graph to a `.dot` file (Graphviz format) for visualization. Note: This method generates the `.dot` file content; rendering it requires the Graphviz tool.

  * **`path`**: The full path (including filename, typically with a `.dot` extension) where the graph file will be saved.
  * **`include_scopes`**: (Default: `True`) If `True`, adds scope information (e.g., `[scope=request]`) to the node labels.
  * **`include_qualifiers`**: (Default: `False`) If `True`, adds qualifier information (e.g., `\\n⟨q⟩`) to the node labels.
  * **`rankdir`**: (Default: `"LR"`) Sets the layout direction for Graphviz (e.g., `"LR"` for Left-to-Right, `"TB"` for Top-to-Bottom).
  * **`title`**: (Optional) A title string to display at the top of the graph.
  * **Returns**: `None`.

-----

## **`PicoContainer` Class Attributes / Methods (Static)**

### `get_current() -> Optional[PicoContainer]`

(Class method) Returns the `PicoContainer` instance currently active in this context (set via `as_current()` or `activate()`), or `None` if no container is active.

  * **Returns**: The active `PicoContainer` or `None`.

-----

### `get_current_id() -> Optional[str]`

(Class method) Returns the `container_id` of the currently active container, or `None`.

  * **Returns**: The active container's ID string or `None`.

-----

### `all_containers() -> Dict[str, PicoContainer]`

(Class method) Returns a dictionary mapping all currently active (not shut down) container IDs to their `PicoContainer` instances.

  * **Returns**: A dictionary of all registered containers.

