# Configuration: Binding Data

This guide details how to bind configuration data to your classes using both the Tree-Based (`@configured`) and Flat (`@configuration`) systems.

## 1. Binding with `@configured` (Tree-Based)

This system maps a nested dictionary (from JSON/YAML) to an object graph, starting from a specified prefix.

### Example

Assume you have a `config.yml` file:

```yaml
app:
  service_name: "My Awesome Service"
  database:
    driver: "postgresql"
    host: "db.example.com"
    port: 5432
    credentials:
      username: "admin"
      password: "${ENV:DB_PASS}" # Interpolates from environment
  
  features:
    - name: "FeatureA"
      enabled: true
    - name: "FeatureB"
      enabled: false
````

You can bind this structure to Python dataclasses:

```python
from dataclasses import dataclass
from typing import List, Optional
from pico_ioc import configured, init
from pico_ioc.config_runtime import YamlTreeSource

@dataclass
class DbCredentials:
    username: str
    password: str

@dataclass
class DatabaseConfig:
    driver: str
    host: str
    port: int
    credentials: DbCredentials

@dataclass
class FeatureFlag:
    name: str
    enabled: bool

# This class binds to the "app" key in the YAML
@configured(target="AppConfig", prefix="app")
@dataclass
class AppConfig:
    service_name: str
    database: DatabaseConfig
    features: List[FeatureFlag]

# --- Initialization ---
container = init(
    modules=[__name__],
    tree_config=(
        YamlTreeSource("config.yml"),
    )
)

# --- Usage ---
# The container can now inject "AppConfig"
config = container.get("AppConfig")
print(config.database.host) # "db.example.com"
print(config.features[0].name) # "FeatureA"
```

### Advanced Binding

The Tree-Based system supports:

  * **Nested Dataclasses:** As seen with `DatabaseConfig`.
  * **Collections:** `List[T]`, `Dict[str, T]`, `Mapping[str, T]`.
  * **Primitives:** `str`, `int`, `float`, `bool`, and `Any`.
  * **Enums:** Automatically matches string values to Enum members by name.
  * **Unions & Discrimination:**
      * For `Union[A, B]`, the system tries to bind to `A`, then `B`.
      * You can specify a discriminator field (e.g., `"$type"`) in the data to explicitly select the class.
      * You can also use `Annotated[Union[A, B], Discriminator("my_type_field")]` for custom discriminator fields.

-----

## 2\. Binding with `@configuration` (Flat Key-Value)

This system maps flat keys, like environment variables, to the fields of a single dataclass.

### Example

Assume you have the following environment variables:

```bash
export MYAPP_SERVICE_HOST="api.example.com"
export MYAPP_SERVICE_PORT="8080"
export MYAPP_DEBUG_MODE="true"
```

You can bind these to a dataclass:

```python
from dataclasses import dataclass
from typing import Optional
from pico_ioc import configuration, init, EnvSource

@configuration(prefix="MYAPP_")
@dataclass
class ServiceSettings:
    # Mapped from MYAPP_SERVICE_HOST
    service_host: str
    
    # Mapped from MYAPP_SERVICE_PORT (and coerced to int)
    service_port: int
    
    # Mapped from MYAPP_DEBUG_MODE (and coerced to bool)
    debug_mode: bool
    
    # Will use default, as MYAPP_TIMEOUT is not set
    timeout: int = 30

# --- Initialization ---
container = init(
    modules=[__name__],
    config=(
        EnvSource(), # Scans all env vars
    )
)

# --- Usage ---
# The container injects the dataclass type directly
settings = container.get(ServiceSettings)
print(settings.service_host) # "api.example.com"
print(settings.service_port) # 8080
print(settings.debug_mode)   # True
```

### Mapping and Coercion

  * **Mapping:** The key is found by combining the `prefix` from `@configuration` with the uppercase name of the field (e.g., `prefix` + `field.name.upper()`).
  * **Coercion:** The system automatically coerces string values from the source into the declared field type.
      * `int(val)`
      * `float(val)`
      * `bool(val)`: Truthy values are "1", "true", "yes", "on", "y", "t".
      * `str(val)`
      * `Optional[T]` is supported.

