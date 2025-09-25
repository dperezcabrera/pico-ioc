# Exporting the Dependency Graph 📈

Understanding the full dependency graph of your application can be crucial for debugging, refactoring, and verifying the architecture. `pico-ioc` provides a utility to export a visual representation of the dependency graph of an initialized container.

---

## How it Works

The `container.export_graph()` method generates a `.dot` file (Graphviz format) representing all components, their dependencies, and their scopes. This `.dot` file can then be rendered into various image formats (like PNG, SVG) using the `graphviz` tool.

### Prerequisites

To use this feature, you need:

1.  **`graphviz` Python package:** Install `pico-ioc` with the `graphviz` extra:
    ```bash
    pip install pico-ioc[graphviz]
    ```
    This will install the `graphviz` Python library, which is a wrapper for the native tool.

2.  **Graphviz native tool:** You also need the `graphviz` command-line tool installed on your system.
    * **macOS (Homebrew):** `brew install graphviz`
    * **Linux (apt):** `sudo apt-get install graphviz`
    * **Windows:** Download from [graphviz.org](https://graphviz.org/download/) and ensure it's added to your system's PATH.

---

## Basic Usage

You call `export_graph()` on an initialized container instance.

```python
# my_app.py
from pico_ioc import component, init
from pico_ioc.container import DependencyResolverError

@component
class ConfigService:
    def get_setting(self) -> str:
        return "some_value"

@component
class AuthService:
    def __init__(self, config: ConfigService):
        self.config = config

@component
class UserService:
    def __init__(self, auth: AuthService, config: ConfigService):
        self.auth = auth
        self.config = config

@component
class AppRunner:
    def __init__(self, user_service: UserService):
        self.user_service = user_service

# Initialize the container
container = init(modules=[__name__])

# Export the graph
# The 'path' argument specifies the output file (e.g., 'my_graph.dot')
# and can include a directory.
# The 'format' argument specifies the output image format (e.g., 'png', 'svg', 'jpeg').
container.export_graph(path="./dependency_graph.png", format="png")

print("Dependency graph exported to dependency_graph.png")
```

When you run `my_app.py`, a file named `dependency_graph.png` (or whatever format you choose) will be generated in the specified location.

### `export_graph` Parameters

  * `path: str`: The full path for the output file (e.g., `./graphs/app_dependencies.png`). The extension determines the output format. You can also specify a `.dot` extension if you only want the raw Graphviz source.
  * `format: Optional[str] = None`: The output format for the graph (e.g., `"png"`, `"svg"`, `"jpeg"`, `"pdf"`). If `None`, the format is inferred from the `path` extension. If the path has no extension or is `.dot`, then `format` defaults to `"dot"`.
  * `include_unresolved: bool = False`: If `True`, components that could not be resolved (e.g., due to missing dependencies if `init(fail_on_error=False)` was used) will still be included in the graph, marked in red.
  * `show_scopes: bool = True`: If `True`, component nodes will be labeled with their scope (e.g., `(singleton)`, `(request)`).
  * `show_lazy: bool = True`: If `True`, lazy components will be marked (e.g., `(lazy)`).
  * `rankdir: str = "LR"`: Graphviz `rankdir` attribute, controlling layout direction (e.g., `"TB"` for top-to-bottom, `"LR"` for left-to-right).

```text
┌───────────┐      ┌───────────────┐
│    App    │ ───> │  UserService  │
└───────────┘      └───────────────┘
       │                   │
       │                   │
       ▼                   ▼
┌───────────┐      ┌───────────┐
│   Config  │ <─── │  Database │
└───────────┘      └───────────┘
```

-----

## Example of an Exported Graph

Here's an example of what a simple dependency graph might look like:

http://googleusercontent.com/image_generation_content/0

**Legend:**

  * **Blue nodes (default):** Singleton or other standard scopes.
  * **Green text:** Indicates a context-aware scope (e.g., `(request)`).
  * **Red text:** Indicates a `lazy` component.
  * **Orange text:** Indicates a `prototype` scope.

-----

## Visualizing Unresolved Dependencies

If you initialize your container with `fail_on_error=False`, `pico-ioc` will attempt to build the graph even with errors. You can then use `include_unresolved=True` to visualize the problematic components.

```python
from pico_ioc import component, init
from pico_ioc.container import DependencyResolverError

@component
class MissingDependency:
    def __init__(self, non_existent_service: "NonExistentService"): # This will fail
        self.non_existent_service = non_existent_service

@component
class WorkingService:
    pass

container = init(modules=[__name__], fail_on_error=False) # Don't raise error immediately

# Export, including the component with the missing dependency
container.export_graph(path="./unresolved_graph.png", format="png", include_unresolved=True)

print("Graph with unresolved dependencies exported to unresolved_graph.png")
```

In the generated graph, `MissingDependency` would be visually highlighted (e.g., with a red border or text) to indicate it could not be fully resolved.

## Next Steps

This concludes the section on Observability. You now know how to manage container contexts, get metrics, trace resolutions, and visualize your entire application.

The next section provides practical, copy-paste recipes for integrating `pico-ioc` with popular web frameworks.

  * **[Integrations Overview](./integrations/README.md)**: Learn how to use `pico-ioc` with FastAPI, Flask, and more.

