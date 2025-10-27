# Configuration: Basic Concepts

Pico-IOC provides a **unified system** for managing configuration, designed to handle various use cases by binding data to your Python classes (typically `dataclasses`). This system revolves around the `@configured` decorator and the `configuration(...)` builder function.

## 1. The Unified Configuration Model

Instead of separate systems for flat and nested data, Pico-IOC uses a single, powerful approach:

* **Decorator:** `@configured`
    * This decorator marks a class (usually a `dataclass`) as a configuration object.
    * It uses parameters like `prefix` and `mapping` (`"auto"`, `"flat"`, `"tree"`) to control how configuration values are found and mapped to the class fields (explained in the [Binding Data](./configuration-binding.md) guide).
* **Configuration Builder:** `configuration(...)`
    * This function gathers and processes various configuration sources in a defined order.
    * It accepts different source types (environment variables, files, dictionaries).
    * It returns a `ContextConfig` object, which encapsulates the final, merged configuration state.
* **Sources:** You use specific source classes with the `configuration(...)` builder:
    * `EnvSource`: Loads flat key-value pairs from environment variables.
    * `FlatDictSource`: Loads flat key-value pairs from a dictionary.
    * `JsonTreeSource`: Loads nested configuration from a JSON file.
    * `YamlTreeSource`: Loads nested configuration from a YAML file (requires `PyYAML`).
    * `DictSource`: Loads nested configuration from an in-memory dictionary.
* **Initialization:** The `ContextConfig` object returned by `configuration(...)` is passed to the `init()` function via the `config` argument.

This unified system allows you to manage both simple environment variables and complex, hierarchical settings consistently.

## Passing Sources to the Container

You define all your configuration sources using the `configuration(...)` builder and pass its result to `init()`. The order matters – sources listed later generally override sources listed earlier according to specific precedence rules (see [Configuration Specification](../specs/spec-configuration.md)).

```python
import os
from pico_ioc import init, configuration, EnvSource, JsonTreeSource
# Assume my_app_module contains components including @configured classes

# --- Example: Define sources using the builder ---
# Create a dummy config.json for the example
with open("config.json", "w") as f:
    f.write('{"database": {"host": "db.prod.com"}}')
os.environ['APP_PORT'] = '8080' # Example environment variable

config_context = configuration(
    # Load environment variables first (lower precedence)
    EnvSource(prefix="APP_"),

    # Load JSON file next (higher precedence for overlapping keys)
    JsonTreeSource("config.json"),

    # You could add more sources here (e.g., YamlTreeSource, DictSource)
    # or overrides={'some_key': 'forced_value'}
)

# --- Initialize the container with the unified config ---
container = init(
    modules=[my_app_module], # Scan your application modules
    config=config_context    # Pass the ContextConfig object
)

# --- Cleanup example files ---
os.remove("config.json")
del os.environ['APP_PORT']

# Now, any @configured classes within my_app_module will be populated
# based on the merged sources defined in config_context.
````

This approach provides a single point for defining how your application reads its configuration, regardless of whether the target class uses flat or tree mapping.


