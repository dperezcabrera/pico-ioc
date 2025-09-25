# Configuration: Basic Concepts

Pico-IOC provides two distinct systems for managing configuration, designed to handle different use cases: Tree-Based and Flat Key-Value.

## 1. Tree-Based Configuration (Recommended)

This is the primary, most powerful configuration system, introduced in **ADR-0002**. It is designed to bind complex, nested configuration structures (like JSON or YAML files) directly into graphs of Python objects (typically dataclasses).

* **Decorator:** `@configured`
* **Sources:** Use `TreeSource` implementations:
    * `JsonTreeSource(path: str)`: Loads configuration from a JSON file.
    * `YamlTreeSource(path: str)`: Loads configuration from a YAML file (requires `PyYAML`).
    * `DictSource(data: Mapping)`: Loads configuration from an in-memory dictionary.
* **Key Features:**
    * Builds complex object graphs from nested data.
    * Supports `List`, `Dict`, `Union`, `Enum`, and nested dataclasses.
    * Supports interpolation of environment variables (e.g., `"${ENV:DB_PASSWORD}"`).
    * Supports internal references (e.g., `"${ref:path.to.other.key}"`).
    * Supports type discrimination for unions.

This system is ideal for managing application settings, service configurations, and any complex, hierarchical data.

## 2. Flat Key-Value Configuration

This is the classic, simpler configuration system. It is designed to bind "flat" key-value pairs (like environment variables) to the fields of a single dataclass.

* **Decorator:** `@configuration`
* **Sources:** Use `ConfigSource` implementations:
    * `EnvSource(prefix: str = "")`: Loads configuration from environment variables.
    * `FileSource(path: str, prefix: str = "")`: Loads from a flat JSON file.
* **Key Features:**
    * Simple, direct mapping from keys to dataclass fields.
    * Keys are typically matched as `PREFIX` + `FIELD_NAME.upper()`.
    * Performs basic type coercion (str, int, float, bool).

This system is best suited for simple applications or for capturing basic settings like port numbers or API keys from the environment.

## Passing Sources to the Container

You provide configuration sources during the container's initialization using the `config` (for Flat) and `tree_config` (for Tree-Based) arguments in the `init()` function.

```python
from pico_ioc import init, EnvSource
from pico_ioc.config_runtime import JsonTreeSource
import my_app_module

container = init(
    my_app_module,
    
    # Sources for @configuration
    config=(
        EnvSource(prefix="APP_"), 
    ),
    
    # Sources for @configured
    tree_config=(
        JsonTreeSource("config.json"),
    )
)
```

The container automatically merges multiple sources of the same type. For `tree_config`, sources listed later will deeply merge over sources listed earlier.

