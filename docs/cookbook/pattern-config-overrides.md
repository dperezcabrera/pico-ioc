# Configuration Cookbook

This section provides practical recipes for advanced configuration patterns using `@configured`, `configuration(...)`, and the `Value(...)` inline override mechanism.

---

## 🧩 Pin a Single Field While Loading the Rest from ENV / YAML

You can use `Annotated[..., Value(...)]` to *lock* a field value regardless of the environment or configuration source.
This is useful for constants that must remain fixed (e.g., internal timeouts, embedded defaults, or CI-only overrides).

```python
from dataclasses import dataclass
from typing import Annotated
from pico_ioc import configured, configuration, EnvSource, Value, init

@configured(prefix="APP_", mapping="auto")
@dataclass
class AppConfig:
    name: str
    # This field is always 60, ignoring APP_TIMEOUT in env or YAML
    timeout: Annotated[int, Value(60)]
    retries: int = 3

# --- Example ENV ---
# APP_NAME="pico-service"
# APP_TIMEOUT="10"
# APP_RETRIES="5"

ctx = configuration(EnvSource(prefix=""))
container = init(modules=[__name__], config=ctx)
cfg = container.get(AppConfig)

print(cfg.name)     # pico-service
print(cfg.timeout)  # 60  (forced by Value)
print(cfg.retries)  # 5   (loaded from ENV)
```

**Key idea:**
`Value(...)` has the highest precedence in the configuration chain.
Once applied, the field is no longer looked up in ENV, YAML, or overrides — it is treated as a literal.

---

## ⚙️ Combine `Value(...)` with Discriminated Unions

You can mix `Value(...)` and `Discriminator(...)` to **fix the subtype** of a union field while still sourcing the subtype’s internal fields dynamically.

This is particularly useful when your system supports multiple backends (e.g., `Postgres` or `Sqlite`), but you want to *lock* one in a specific deployment without changing the source structure.

```python
from dataclasses import dataclass
from typing import Annotated, Union
from pico_ioc import configured, configuration, DictSource, Discriminator, Value, init

@dataclass
class Postgres:
    kind: str
    host: str
    port: int

@dataclass
class Sqlite:
    kind: str
    path: str

@configured(prefix="db", mapping="tree")
@dataclass
class DbConfig:
    # Force the discriminator to always use Postgres
    model: Annotated[Union[Postgres, Sqlite], Discriminator("kind"), Value("Postgres")]

# --- Example Source ---
config_data = {
    "db": {
        "model": { "host": "db.example.com", "port": 5432 }
    }
}

ctx = configuration(DictSource(config_data))
container = init(modules=[__name__], config=ctx)
cfg = container.get(DbConfig)

print(cfg.model.kind)  # Postgres
print(cfg.model.host)  # db.example.com
```

**How it works:**

* The `Value("Postgres")` annotation *pins* the union discriminator to `"Postgres"`.
* `Discriminator("kind")` still directs the runtime to build the correct subtype (`Postgres`),
  allowing its other fields (`host`, `port`) to load normally from the configuration source.

---

✅ **Takeaway:**
`Annotated[..., Value(...)]` provides a clean, declarative way to hard-code configuration decisions
while keeping the rest of your configuration dynamic, testable, and environment-driven.

