# Exporting the Dependency Graph 📈

Understanding the full dependency graph of your application can be crucial for debugging, refactoring, and verifying the architecture. `pico-ioc` provides a utility to export a representation of the dependency graph of an initialized container in the Graphviz DOT format.

---

## How it Works

The `container.export_graph()` method generates the content for a `.dot` file. This file describes the graph structure (nodes representing components, edges representing dependencies). You can then use the Graphviz tool (which needs to be installed separately) to render this `.dot` file into various visual formats (like PNG, SVG, PDF).

### Prerequisites

To render the generated `.dot` file into an image, you need the Graphviz command-line tool installed on your system.
* macOS (Homebrew): `brew install graphviz`
* Linux (apt): `sudo apt-get update && sudo apt-get install graphviz`
* Windows: Download from graphviz.org and ensure the `dot` command is added to your system's PATH.

To verify your installation, run: `dot -V`

---

## Basic Usage

Call `export_graph()` on an initialized container instance, specifying the path where you want to save the `.dot` file.

```python
# my_app.py
from pico_ioc import component, init

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

container = init(modules=[__name__])

dot_file_path = "./dependency_graph.dot"
container.export_graph(path=dot_file_path, title="My Application Graph")

print(f"Dependency graph definition exported to {dot_file_path}")
print(f"To render as PNG, run: dot -Tpng {dot_file_path} -o dependency_graph.png")
```

When you run `my_app.py`, a file named `dependency_graph.dot` will be generated. You then use the `dot` command-line tool to create the visual image (for example: `dependency_graph.png`).

### export_graph Parameters

* `path: str`: The full path (including filename, typically ending in `.dot`) where the Graphviz definition file will be saved.
* `include_scopes: bool = True`: If `True`, adds scope information (e.g., `[scope=request]`) to the node labels in the `.dot` file.
* `include_qualifiers: bool = False`: If `True`, adds qualifier information (e.g., `\n⟨q⟩`) to the node labels in the `.dot` file.
* `rankdir: str = "LR"`: Sets the layout direction hint for Graphviz (e.g., `"LR"` for Left-to-Right, `"TB"` for Top-to-Bottom) in the `.dot` file.
* `title: Optional[str] = None`: An optional title string to include in the graph definition.

---

## Rendering the Graph

Use the `dot` command to render the `.dot` file into different formats:

* PNG: `dot -Tpng dependency_graph.dot -o dependency_graph.png`
* SVG: `dot -Tsvg dependency_graph.dot -o dependency_graph.svg`
* PDF: `dot -Tpdf dependency_graph.dot -o dependency_graph.pdf`

Tip: If the graph is large, consider SVG for easier zooming and inspection.

---

## Example of a Rendered Graph

Rendering the generated `.dot` file (e.g., with `dot -Tpng dependency_graph.dot -o graph.png`) might produce an image like this for a simple dependency structure:

Node Labels (controlled by parameters):
* Component Name: Always shown (e.g., `UserService`).
* Scope: Added if `include_scopes=True` (e.g., `UserService\n[scope=singleton]`).
* Qualifiers: Added if `include_qualifiers=True` and qualifiers exist (e.g., `MyService\n⟨payment⟩`).

Layout direction is controlled via `rankdir` (default `LR`), which helps readability for wider graphs.

---

## Visualizing Potential Issues

While the current implementation focuses on exporting the graph of successfully resolved bindings during `init`, you can use the visual graph to:
* Identify overly complex dependency chains.
* Spot components with too many responsibilities (many outgoing arrows).
* Verify that components are assigned the expected scopes.
* Visually trace how dependencies flow through your application.

---

## Troubleshooting

* The `dot` command is not found:
  * Ensure Graphviz is installed and on your PATH. Verify with `dot -V`.
  * On Windows, reopen the terminal after installation so PATH changes apply.

* Graph looks cluttered or unreadable:
  * Try `rankdir="TB"` to stack components top-to-bottom.
  * Render to SVG for better zooming and panning.

* Missing nodes or edges:
  * Ensure the container is fully initialized before calling `export_graph()`.
  * Verify your modules list in `init(modules=[...])` includes all components you expect.

---

## Next Steps

This concludes the section on Observability. You now know how to manage container contexts, get metrics, trace resolutions, and visualize your application's structure.

The next section provides practical, copy-paste recipes for integrating `pico-ioc` with popular web frameworks.

* Integrations Overview: ../integrations/README.md
