# Configuration: Binding Data with `@configured`

This guide explains how to bind configuration data to your Python classes (typically `dataclasses`) using the unified `@configured` decorator, as defined in **ADR-0010**.
This single decorator supports both **flat** (key-value) and **tree** (nested) configuration structures.

---

## 1. Unified Configuration Model

The core idea is to define your configuration shape as a `dataclass` and use `@configured` to tell **pico-ioc** how to populate it from various sources.

* **Decorator:** `@configured(prefix: str = "", mapping: Literal["auto", "flat", "tree"] = "auto")`

  * `prefix` — namespace for configuration keys (e.g. `"APP_"` for flat, `"app"` for tree).
  * `mapping` — determines how configuration keys map to dataclass fields (`"auto"`, `"flat"`, `"tree"`).
* **Sources:** Combine multiple configuration providers (environment, files, dicts) via the `configuration(...)` builder.
* **Initialization:** Pass the `ContextConfig` returned by `configuration(...)` into `init(config=...)`.

---

## 2. Binding Modes (`mapping` parameter)

### `mapping="flat"` (or `"auto"` for simple dataclasses)

Used for flat key-value environments (e.g. `os.environ`).

* **Lookup:** Keys like `PREFIX_FIELDNAME` (usually uppercase).
* **Auto-Detection:** `"auto"` behaves as `"flat"` if all fields are primitive.
* **Coercion:** Strings are automatically cast to the target type.

**Example (Flat Mapping):**

```bash
export MYAPP_SERVICE_HOST="api.example.com"
export MYAPP_SERVICE_PORT="8080"
export MYAPP_DEBUG_MODE="true"
```

```python
import os
from dataclasses import dataclass
from pico_ioc import configured, configuration, EnvSource, init

@configured(prefix="MYAPP_", mapping="auto")
@dataclass
class ServiceSettings:
    service_host: str
    service_port: int
    debug_mode: bool
    timeout: int = 30

os.environ.update({
    "MYAPP_SERVICE_HOST": "api.example.com",
    "MYAPP_SERVICE_PORT": "8080",
    "MYAPP_DEBUG_MODE": "true"
})

ctx = configuration(EnvSource(prefix=""))
container = init(modules=[__name__], config=ctx)
settings = container.get(ServiceSettings)

print(settings.service_host)  # api.example.com
print(settings.service_port)  # 8080
print(settings.debug_mode)    # True
print(settings.timeout)       # 30
```

---

### `mapping="tree"` (or `"auto"` for nested dataclasses)

For hierarchical sources like YAML, JSON, or structured environment variables.

* **Lookup:** Nested under the given prefix.
* **Auto-Detection:** `"auto"` acts as `"tree"` if the dataclass has nested or complex fields.
* **Features:** Supports nested dataclasses, lists, dicts, unions, interpolation, etc.

**Example (Tree Mapping):**

```yaml
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
```

```python
import os
from dataclasses import dataclass, field
from typing import List
from pico_ioc import configured, configuration, YamlTreeSource, init

os.environ["DB_PASS"] = "secret123"

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

@configured(prefix="app", mapping="auto")
@dataclass
class AppConfig:
    service_name: str
    database: DatabaseConfig
    features: List[FeatureFlag] = field(default_factory=list)

ctx = configuration(YamlTreeSource("config.yml"))
container = init(modules=[__name__], config=ctx)
cfg = container.get(AppConfig)

print(cfg.service_name)                 # My Awesome Service
print(cfg.database.credentials.password) # secret123
```

---

## 3. Advanced Binding with `Annotated`

Python’s `typing.Annotated` enables metadata-based extensions to field behavior.

### `Discriminator` for `Union` Types

`Discriminator` chooses which subtype to instantiate based on a field value.

```python
from dataclasses import dataclass
from typing import Annotated, Union
from pico_ioc import configured, configuration, DictSource, Discriminator, init

@dataclass
class Postgres:
    kind: str
    host: str
    port: int

@dataclass
class Sqlite:
    kind: str
    path: str

@configured(prefix="DB", mapping="tree")
@dataclass
class DbCfg:
    model: Annotated[Union[Postgres, Sqlite], Discriminator("kind")]

config_data = {"DB": {"model": {"kind": "Postgres", "host": "localhost", "port": 5432}}}
ctx = configuration(DictSource(config_data))
container = init(modules=[__name__], config=ctx)
db = container.get(DbCfg)
print(db)
```

---

### `Value` for Field-Level Overrides

`Value` provides the **highest precedence** override — a field annotated with `Value(...)` always uses that constant, ignoring environment variables, files, or overrides.

```python
from dataclasses import dataclass
from typing import Annotated
from pico_ioc import configured, Value, configuration, EnvSource, init

@configured(prefix="SVC_", mapping="auto")
@dataclass
class ApiConfig:
    url: str
    timeout_seconds: Annotated[int, Value(60)]
    retries: int = 3

os.environ.update({
    "SVC_URL": "https://api.internal",
    "SVC_TIMEOUT_SECONDS": "10",  # ignored
    "SVC_RETRIES": "5"
})

ctx = configuration(EnvSource(prefix=""))
container = init(modules=[__name__], config=ctx)
api_cfg = container.get(ApiConfig)

print(api_cfg.url)             # https://api.internal
print(api_cfg.timeout_seconds) # 60 (from Value)
print(api_cfg.retries)         # 5 (from ENV)
```

---

This guide unifies all configuration patterns supported by `@configured` and `configuration(...)` according to **ADR-0010**, covering flat and tree mappings, discriminated unions, and inline constant overrides using `Annotated[..., Value(...)]`.

