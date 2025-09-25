# Protocols Reference

This page describes the Python protocols (`typing.Protocol`) used by `pico-ioc` for extension points. You can implement these protocols to customize the container's behavior or integrate with external systems.

---

## **`MethodInterceptor`** 🎭

Used for implementing Aspect-Oriented Programming (AOP). Classes implementing this protocol can be applied to component methods using the `@intercepted_by` decorator.

```python
from typing import Any, Callable, Protocol

class MethodCtx:
    """Context object passed to the interceptor."""
    instance: object       # The component instance being called
    cls: type              # The class of the component instance
    method: Callable       # The original bound method being intercepted
    name: str              # The name of the method being called
    args: tuple            # Positional arguments passed to the method
    kwargs: dict           # Keyword arguments passed to the method
    container: Any         # The PicoContainer instance
    local: Dict[str, Any]  # A dict for interceptors to share state during one call
    request_key: Any | None # The current request scope ID, if applicable

class MethodInterceptor(Protocol):
    def invoke(
        self, 
        ctx: MethodCtx, 
        call_next: Callable[[MethodCtx], Any]
    ) -> Any:
        """
        Wraps the original method call.

        Args:
            ctx: The MethodCtx providing call information.
            call_next: A callable that proceeds to the next interceptor
                       or the original method. You *must* call this.

        Returns:
            The result of the original method, potentially modified.
        """
        ... # Your logic before/after call_next(ctx)
````

**Note:** The `invoke` method can be `async def` if the intercepted method is `async`. `pico-ioc` will handle `await`ing `call_next(ctx)` correctly.

-----

## **`ContainerObserver`** 👀

Used for monitoring container events. Instances are passed to `init(observers=[...])`.

```python
from typing import Protocol, Union

KeyT = Union[str, type]

class ContainerObserver(Protocol):
    def on_resolve(self, key: KeyT, took_ms: float):
        """
        Called *after* a component is successfully created and cached.
        Not called for prototype scope or cache hits.

        Args:
            key: The Key of the component that was resolved.
            took_ms: The time taken (in milliseconds) to create the component.
        """
        ...

    def on_cache_hit(self, key: KeyT):
        """
        Called when container.get() or .aget() retrieves a component
        from the cache (singleton or scoped).

        Args:
            key: The Key of the component retrieved from the cache.
        """
        ...
```

-----

## **`ScopeProtocol`** ♻️

Used for defining custom **Scopes**. Instances are passed to `init(custom_scopes={...})`.

```python
from typing import Any, Protocol, Optional
import contextvars

class ScopeProtocol(Protocol):
    def get_id(self) -> Any | None:
        """
        Returns the *current* unique ID for this scope in the active context.
        If the scope is not active, should return None.
        Used by ScopedCaches to find the correct cache instance.
        """
        ...

    # Optional methods for contextvar-based scopes:
    # def activate(self, scope_id: Any) -> Optional[contextvars.Token]: ...
    # def deactivate(self, token: Optional[contextvars.Token]) -> None: ...
```

**Note:** `pico-ioc` provides `ContextVarScope` as a standard implementation based on `contextvars`.

-----

## **`ConfigSource`** (Basic Config) ⚙️

Used by the `@configuration` system for **flat key-value** configuration. Instances are passed to `init(config=[...])`.

```python
from typing import Optional, Protocol

class ConfigSource(Protocol):
    def get(self, key: str) -> Optional[str]:
        """
        Retrieves a configuration value for the given key.

        Args:
            key: The configuration key (e.g., "APP_DEBUG").

        Returns:
            The configuration value as a string, or None if not found.
        """
        ...
```

**Implementations Provided:** `EnvSource`, `FileSource` (for flat JSON).

-----

## **`TreeSource`** (Tree Config) 🌳

Used by the `@configured` system for **nested tree-based** configuration. Instances are passed to `init(tree_config=[...])`.

```python
from typing import Mapping, Any, Protocol

class TreeSource(Protocol):
    def get_tree(self) -> Mapping[str, Any]:
        """
        Returns the entire configuration structure as a nested dictionary.
        This method might load from a file, parse YAML/JSON, etc.

        Returns:
            A nested dictionary representing the configuration tree.
        """
        ...
```

**Implementations Provided:** `JsonTreeSource`, `YamlTreeSource`, `DictSource`.

