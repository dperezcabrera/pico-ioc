# Configuration: Basic Concepts

Pico-IOC provides a unified system for managing configuration, designed to handle various use cases by binding data to your Python classes (typically `dataclasses`). This system revolves around the `@configured` decorator and the `configuration(...)` builder function.

## 1. The Unified Configuration Model

Instead of separate systems for flat and nested data, Pico-IOC uses a single, powerful approach:

- Decorator: `@configured`
  - This decorator marks a class (usually a `dataclass`) as a configuration object.
  - It uses parameters like `prefix` and `mapping` (`"auto"`, `"flat"`, `"tree"`) to control how configuration values are found and mapped to the class fields (explained in the Binding Data guide).
- Configuration Builder: `configuration(...)`
  - This function gathers and processes various configuration sources in a defined order.
  - It accepts different source types (environment variables, files, dictionaries).
  - It returns a `ContextConfig` object, which encapsulates the final, merged configuration state.
- Sources: You use specific source classes with the `configuration(...)` builder:
  - `EnvSource`: Loads flat key-value pairs from environment variables.
  - `FlatDictSource`: Loads flat key-value pairs from a dictionary.
  - `JsonTreeSource`: Loads nested configuration from a JSON file.
- Initialization: The `ContextConfig` object returned by `configuration(...)` is passed to the `init()` function via the `config` argument.

This unified system allows you to manage both simple environment variables and complex, hierarchical settings consistently.

## Passing Sources to the Container

You define all your configuration sources using the `configuration(...)` builder and pass its result to `init()`. The order matters – sources listed later generally override sources listed earlier according to specific precedence rules.

```python
import os
from dataclasses import dataclass
from pico_ioc import init, configuration, configured, EnvSource, JsonTreeSource

# --- Define a component that uses configuration ---
@configured(prefix="APP_", mapping="auto")
@dataclass
class AppConfig:
    PORT: int
    HOST: str = "localhost"

@configured(prefix="database", mapping="auto")
@dataclass
class DbConfig:
    host: str

# --- Example: Define sources using the builder ---
with open("config.json", "w") as f:
    f.write('{"database": {"host": "db.prod.com"}}')
os.environ['APP_PORT'] = '8080'

config_context = configuration(
    EnvSource(prefix=""),
    JsonTreeSource("config.json")
)

# --- Initialize the container with the unified config ---
container = init(
    modules=[__name__],
    config=config_context
)

# --- Verify the configuration was loaded ---
app_cfg = container.get(AppConfig)
db_cfg = container.get(DbConfig)

print(f"App running on: {app_cfg.HOST}:{app_cfg.PORT}")
print(f"Database host: {db_cfg.host}")

# --- Cleanup example files ---
os.remove("config.json")
del os.environ['APP_PORT']
```
