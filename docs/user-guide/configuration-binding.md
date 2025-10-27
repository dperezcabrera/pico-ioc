# Configuration: Binding Data with @configured

This guide explains how to bind configuration data to your Python classes (typically `dataclasses`) using the unified `@configured` decorator, as defined in ADR-0010. This single decorator handles both **flat** (key-value) and **tree** (nested) configuration structures.

---

## 1. Unified Configuration Model

The core idea is to define your desired configuration structure as a `dataclass` and use `@configured` to tell `pico-ioc` how to populate it from various sources.

* **Decorator:** `@configured(prefix: str = "", mapping: Literal["auto","flat","tree"]="auto")`
    * `prefix`: Specifies the namespace for the configuration (e.g., `"APP_"` for flat, `"app"` for tree).
    * `mapping`: Determines how configuration keys are matched to dataclass fields (`"auto"`, `"flat"`, `"tree"`).
* **Sources:** You define an ordered list of configuration sources (environment variables, files, dictionaries) using the `configuration(...)` builder.
* **Initialization:** You pass the result of `configuration(...)` (a `ContextConfig` object) to `init(config=...)`.

---

## 2. Binding Modes (`mapping` parameter)

The `mapping` parameter in `@configured` controls how `pico-ioc` finds values for your dataclass fields.

### `mapping="flat"` (or `"auto"` for simple dataclasses)

This mode is suitable for simple key-value sources like environment variables.

* **Key Lookup:** Looks for keys like `PREFIX_FIELDNAME` (typically uppercase in sources, e.g., `APP_HOST`).
* **Auto-Detection (`"auto"`):** If all fields in the dataclass are primitives (`str`, `int`, `float`, `bool`), `"auto"` behaves like `"flat"`.
* **Coercion:** Automatically converts string values from sources to the field's type (`int`, `bool`, etc.).

**Example (Flat Mapping):**

Assume environment variables:
```bash
export MYAPP_SERVICE_HOST="api.example.com"
export MYAPP_SERVICE_PORT="8080"
export MYAPP_DEBUG_MODE="true"
```

Bind them to a dataclass:

```python
import os
from dataclasses import dataclass
from typing import Optional
from pico_ioc import configured, configuration, EnvSource, init

# 'mapping="auto"' behaves like "flat" because all fields are primitives
@configured(prefix="MYAPP_", mapping="auto")
@dataclass
class ServiceSettings:
    # Mapped from MYAPP_SERVICE_HOST
    service_host: str
    # Mapped from MYAPP_SERVICE_PORT (coerced to int)
    service_port: int
    # Mapped from MYAPP_DEBUG_MODE (coerced to bool)
    debug_mode: bool
    # Will use default, as MYAPP_TIMEOUT is not set in env
    timeout: int = 30

# --- Setup Environment (for runnable example) ---
os.environ['MYAPP_SERVICE_HOST'] = 'api.example.com'
os.environ['MYAPP_SERVICE_PORT'] = '8080'
os.environ['MYAPP_DEBUG_MODE'] = 'true'

# --- Initialization ---
# Use the configuration builder
ctx = configuration(
    EnvSource(prefix="") # EnvSource for flat key-value lookup
)
container = init(modules=[__name__], config=ctx) # Pass context via 'config'

# --- Usage ---
settings = container.get(ServiceSettings)
print(f"Host: {settings.service_host}")   # Output: Host: api.example.com
print(f"Port: {settings.service_port}")   # Output: Port: 8080
print(f"Debug: {settings.debug_mode}")  # Output: Debug: True
print(f"Timeout: {settings.timeout}")    # Output: Timeout: 30

# --- Cleanup Environment ---
del os.environ['MYAPP_SERVICE_HOST']
del os.environ['MYAPP_SERVICE_PORT']
del os.environ['MYAPP_DEBUG_MODE']
```

### `mapping="tree"` (or `"auto"` for complex dataclasses)

This mode is ideal for nested configuration structures like YAML or JSON files, or hierarchical environment variables.

  * **Key Lookup:** Expects a nested structure under the `prefix`. Path segments are used to traverse the structure. For environment variables, segments are joined by `__` (e.g., `APP_DATABASE__CREDENTIALS__USERNAME`).
  * **Auto-Detection (`"auto"`):** If any field is a `dataclass`, `list`, `dict`, or `Union`, `"auto"` behaves like `"tree"`.
  * **Features:** Supports nested dataclasses, lists, dicts, enums, unions, interpolation, etc.

**Example (Tree Mapping):**

Assume a `config.yml` file:

```yaml
app:
  service_name: "My Awesome Service"
  database:
    driver: "postgresql"
    host: "db.example.com"
    port: 5432
    credentials:
      username: "admin"
      password: "${ENV:DB_PASS}" # Interpolates DB_PASS from environment
  features:
    - name: "FeatureA"
      enabled: true
    - name: "FeatureB"
      enabled: false
```

Bind this structure:

```python
# Create a dummy config.yml for the example
with open("config.yml", "w") as f:
    f.write("""
app:
  service_name: "My Awesome Service"
  database:
    driver: "postgresql"
    host: "db.example.com"
    port: 5432
    credentials:
      username: "admin"
      password: "${ENV:DB_PASS}"
  features:
    - name: "FeatureA"
      enabled: true
    - name: "FeatureB"
      enabled: false
""")
os.environ['DB_PASS'] = 'secret123' # Set env var for interpolation

from dataclasses import dataclass, field
from typing import List, Optional
from pico_ioc import configured, configuration, YamlTreeSource, init # Use YamlTreeSource

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

# 'mapping="auto"' behaves like "tree" due to nested dataclasses and list
@configured(prefix="app", mapping="auto")
@dataclass
class AppConfig:
    service_name: str
    database: DatabaseConfig
    features: List[FeatureFlag] = field(default_factory=list)

# --- Initialization ---
ctx = configuration(
    # YamlTreeSource provides the nested dictionary
    YamlTreeSource("config.yml")
)
container = init(modules=[__name__], config=ctx)

# --- Usage ---
config = container.get(AppConfig)
print(f"\nService Name: {config.service_name}") # Output: Service Name: My Awesome Service
print(f"DB Host: {config.database.host}")      # Output: DB Host: db.example.com
print(f"DB Password: {config.database.credentials.password}") # Output: DB Password: secret123 (interpolated)
print(f"Feature 1 Name: {config.features[0].name}") # Output: Feature 1 Name: FeatureA

# --- Cleanup ---
os.remove("config.yml")
del os.environ['DB_PASS']
```

-----

## 3\. Advanced Binding with `Annotated`

`typing.Annotated` allows adding extra metadata to fields, enabling advanced configuration scenarios.

### `Discriminator` for `Union` Types

When a field can be one of several different dataclass types (`Union`), `Discriminator` tells `@configured` which sub-field in the configuration data determines the actual type to instantiate.

```python
from dataclasses import dataclass
from typing import Annotated, Union
from pico_ioc import configured, configuration, DictSource, Discriminator, init

@dataclass
class Postgres:
    kind: str # The discriminator field
    host: str
    port: int

@dataclass
class Sqlite:
    kind: str # The discriminator field
    path: str

# Configured for tree mapping under the "DB" prefix
@configured(prefix="DB", mapping="tree")
@dataclass
class DbCfg:
    # Use Annotated and Discriminator("kind")
    model: Annotated[Union[Postgres, Sqlite], Discriminator("kind")]

# --- Example Config Data (using DictSource) ---
config_data_postgres = {
    "DB": {
        "model": {"kind": "Postgres", "host": "localhost", "port": 5432}
    }
}
config_data_sqlite = {
    "DB": {
        "model": {"kind": "Sqlite", "path": "/path/to/db.sqlite"}
    }
}

# --- Initialization (Postgres) ---
ctx_pg = configuration(DictSource(config_data_postgres))
container_pg = init(modules=[__name__], config=ctx_pg)
db_cfg_pg = container_pg.get(DbCfg)

print(f"\nDB Config (PG): {db_cfg_pg}")
# Output: DB Config (PG): DbCfg(model=Postgres(kind='Postgres', host='localhost', port=5432))
assert isinstance(db_cfg_pg.model, Postgres)

# --- Initialization (Sqlite) ---
ctx_sqlite = configuration(DictSource(config_data_sqlite))
container_sqlite = init(modules=[__name__], config=ctx_sqlite)
db_cfg_sqlite = container_sqlite.get(DbCfg)

print(f"DB Config (SQLite): {db_cfg_sqlite}")
# Output: DB Config (SQLite): DbCfg(model=Sqlite(kind='Sqlite', path='/path/to/db.sqlite'))
assert isinstance(db_cfg_sqlite.model, Sqlite)
```

### `Value` for Field-Level Overrides

`Value` provides the highest precedence override. A field annotated with `Value(...)` will *always* take that value, ignoring anything from environment variables, files, or `overrides` passed to `configuration(...)`.

```python
from dataclasses import dataclass
from typing import Annotated
from pico_ioc import configured, Value, configuration, EnvSource, init

@configured(prefix="SVC_", mapping="auto")
@dataclass
class ApiConfig:
    url: str
    # This field is FORCED to be 60, ignoring SVC_TIMEOUT in ENV
    timeout_seconds: Annotated[int, Value(60)]
    retries: int = 3

# --- Setup Environment ---
os.environ['SVC_URL'] = '[https://api.internal](https://api.internal)'
os.environ['SVC_TIMEOUT_SECONDS'] = '10' # This will be ignored
os.environ['SVC_RETRIES'] = '5'

# --- Initialization ---
ctx = configuration(EnvSource(prefix=""))
container = init(modules=[__name__], config=ctx)

# --- Usage ---
api_cfg = container.get(ApiConfig)
print(f"\nAPI URL: {api_cfg.url}")              # Output: API URL: [https://api.internal](https://api.internal)
print(f"API Timeout: {api_cfg.timeout_seconds}") # Output: API Timeout: 60 (from Value)
print(f"API Retries: {api_cfg.retries}")        # Output: API Retries: 5 (from ENV)

# --- Cleanup ---
del os.environ['SVC_URL']
del os.environ['SVC_TIMEOUT_SECONDS']
del os.environ['SVC_RETRIES']

```

-----

This revised guide focuses on the unified `@configured` decorator and the `configuration(...)` builder, providing examples for flat, tree, `Discriminator`, and `Value` bindings according to ADR-0010.
