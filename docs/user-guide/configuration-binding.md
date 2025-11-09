# Configuration: Binding Data with `@configured`

This guide explains how to bind configuration data to your Python classes (typically `dataclasses`) using the unified `@configured` decorator, as defined in ADR-0010.
A single decorator supports both flat (key–value) and tree (nested) configuration structures.

---

## 1. Unified Configuration Model

Define your configuration shape as a `dataclass` and use `@configured` to tell pico-ioc how to populate it from various sources.

- Decorator: `@configured(prefix: str = "", mapping: Literal["auto", "flat", "tree"] = "auto")`
  - prefix — namespace for configuration keys (e.g. `"MYAPP_"` for flat, `"app"` for tree).
  - mapping — determines how configuration keys map to dataclass fields (`"auto"`, `"flat"`, `"tree"`).
- Sources: Combine multiple configuration providers (environment, files, dicts) via the `configuration(...)` builder.
- Initialization: Pass the `ContextConfig` returned by `configuration(...)` into `init(config=...)`.

Notes:
- Auto detection: `"auto"` behaves as `"flat"` for simple dataclasses (only primitive fields) and as `"tree"` when nested or complex fields are present.
- The prefix applies to the root of the config domain:
  - Flat: key prefix, typically uppercase with underscores.
  - Tree: top-level object name in structured sources (e.g., `app:` in YAML).

---

## 2. Binding Modes (`mapping` parameter)

### mapping="flat" (or "auto" for simple dataclasses)

Use for flat key–value environments (e.g., `os.environ`).

- Lookup: Keys like `PREFIX_FIELDNAME` (usually uppercase).
- Auto detection: `"auto"` acts as `"flat"` if all fields are primitive (str, int, float, bool).
- Coercion: Strings are automatically cast to the target field type.

Example (flat mapping):

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

Field naming conventions:
- Field `service_port` maps to `MYAPP_SERVICE_PORT`.
- Case-insensitive value parsing for booleans (`"true"`, `"False"`, etc.).
- Missing keys fall back to dataclass defaults (if provided).

---

### mapping="tree" (or "auto" for nested dataclasses)

Use for hierarchical sources like YAML/JSON or structured environment variables.

- Lookup: Nested under the given prefix (e.g., `app:` in YAML).
- Auto detection: `"auto"` acts as `"tree"` if the dataclass contains nested dataclasses, lists, dicts, or unions.
- Features: Supports nested dataclasses, lists, dicts, discriminated unions, and interpolation.

Example (tree mapping with YAML):

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

print(cfg.service_name)                  # My Awesome Service
print(cfg.database.credentials.password) # secret123
```

Structured environment variables (tree mapping via env):
- Many setups support double-underscore separators to express nesting:
  - `APP__DATABASE__HOST="db.example.com"`
  - `APP__DATABASE__PORT="5432"`
  - `APP__FEATURES__0__NAME="FeatureA"`
- Use `@configured(prefix="APP", mapping="tree")` with `EnvSource`.

---

## 3. Combining Sources and Precedence

Use the `configuration(...)` builder to compose multiple sources. Typical patterns:
- Base config from a file (YAML/JSON).
- Environment variables to override file values.
- In-memory dicts for tests or explicit overrides.

Example:

```python
from pico_ioc import configuration, YamlTreeSource, EnvSource, DictSource, init

overrides = {"app": {"service_name": "Override Name"}}

ctx = configuration(
    YamlTreeSource("config.yml"),
    EnvSource(prefix=""),  # overrides file values
    DictSource(overrides)  # highest precedence overrides
)

container = init(modules=[__name__], config=ctx)
```

Precedence:
- When multiple sources define the same setting, later sources in the `configuration(...)` call override earlier ones.
- Field-level `Value` annotations (see below) have the highest precedence and bypass sources entirely.

---

## 4. Advanced Binding with `Annotated`

Python’s `typing.Annotated` enables metadata-based extensions to field behavior.

### Discriminator for Union types

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

Notes:
- The discriminator field (`"kind"`) must be present in the input and in each union subtype.
- Values must match the subtype’s identifier (e.g., `"Postgres"` vs `"Sqlite"`).

### Value for field-level overrides

`Value` provides the highest precedence override — a field annotated with `Value(...)` always uses that constant, ignoring environment variables, files, or in-memory overrides.

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

## 5. Defaults, Optional fields, and Validation

- Defaults: Dataclass defaults are used when a value is missing in all sources.
- Optional: Use `Optional[T]` (or `T | None`) for nullable fields; missing keys become `None` unless defaulted.
- Post-init validation: Add `__post_init__` to perform custom checks and raise errors early.

Example:

```python
from dataclasses import dataclass
from typing import Optional
from pico_ioc import configured

@configured(prefix="APP_", mapping="flat")
@dataclass
class HttpConfig:
    host: str
    port: int = 80
    base_path: Optional[str] = None

    def __post_init__(self):
        if not (1 <= self.port <= 65535):
            raise ValueError("port must be between 1 and 65535")
```

---

## 6. Error Handling and Type Coercion

- Missing required keys: If a required field (without default) is missing, binding fails with a descriptive error.
- Type coercion:
  - Numbers: `"8080"` → `int(8080)`
  - Booleans: `"true"/"false"`, `"1"/"0"` → `bool`
  - Lists/dicts (tree sources): parsed according to the structured format (YAML/JSON).
- Union and discriminator mismatches produce errors indicating the offending path and expected variants.

---

## 7. Tips and Conventions

- Keep prefixes consistent:
  - Flat: `MYAPP_` for env.
  - Tree: `app` for file-based configs.
- Prefer `"auto"` for most cases; switch to explicit `"flat"` or `"tree"` when needed.
- For environment-only tree configs, use double-underscore separators to express nested structure.
- Use `DictSource` for tests to avoid filesystem and environment dependencies.

---

This guide unifies configuration patterns supported by `@configured` and `configuration(...)` according to ADR-0010, covering flat and tree mappings, multiple-source composition and precedence, discriminated unions, and inline constant overrides using `Annotated[..., Value(...)]`.
