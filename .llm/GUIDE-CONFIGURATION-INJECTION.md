# GUIDE-CONFIGURATION-INJECTION

`pico-ioc` includes a powerful and flexible configuration injection system that allows you to decouple your application's configuration in a type-safe way. You can load values from environment variables, files (YAML, JSON, INI, .env), and more.

## 1\. Basic Concepts

Configuration injection is built on three pillars:

1.  **`@config_component`**: A decorator to mark a class (preferably a `dataclass`) that will hold your configuration values.
2.  **`ConfigSource`**: Objects that tell `pico-ioc` *where* to find configuration values (e.g., `EnvSource` for environment variables, `FileSource` for files).
3.  **The `config` parameter in `pico.init()`**: An ordered tuple of `ConfigSource`s. The first source that contains a key wins.

## 2\. Basic Usage: Autowiring

In the most common use case, `pico-ioc` can populate the fields of your configuration class automatically.

#### Step 1: Define Your Configuration Class

Use `@config_component` and, optionally, a prefix for environment variables.

```python
# in settings.py
from dataclasses import dataclass
from pico_ioc import config_component

@config_component(prefix="APP_")
@dataclass(frozen=True)
class Settings:
    # Will look for APP_DB_URL or DB_URL in the environment, or db_url in files.
    db_url: str

    # Will look for APP_TIMEOUT or TIMEOUT, or timeout in files.
    timeout: int = 10  # Default value if not found in any source

    # Will look for APP_DEBUG or DEBUG, or debug in files.
    debug: bool = False
```

#### Step 2: Provide the Sources on Initialization

Imagine you have these files:

**`config.yml`**

```yaml
db_url: "postgresql://user:pass@host:5432/prod_db"
timeout: 30
```

**Environment Variables**

```shell
export APP_DEBUG=true
export APP_DB_URL="postgresql://user:pass@host:5432/env_db"
```

Now, initialize the container, specifying the priority order of the sources.

```python
# in main.py
from pico_ioc import init
from pico_ioc.config import EnvSource, FileSource
from .settings import Settings

container = init(
    __name__,
    config=(
        # 1. First, look in environment variables with the "APP_" prefix
        EnvSource(prefix="APP_"),
        
        # 2. If not found, look in config.yml
        FileSource("config.yml"),
    ),
)

# Request your configuration like any other component!
settings = container.get(Settings)

print(f"Database URL: {settings.db_url}") # -> postgresql://user:pass@host:5432/env_db (from environment)
print(f"Timeout: {settings.timeout}")     # -> 30 (from file, as it's not in the environment)
print(f"Debug: {settings.debug}")       # -> True (from environment)
```

## 3\. Advanced Usage: Manual Field Overrides

Sometimes, the field name in your class doesn't match the key in the configuration source, or you need more granular control. For that, you can use the `Env`, `File`, `Path`, and `Value` helpers.

```python
from dataclasses import dataclass
from pico_ioc import config_component
from pico_ioc.config import Env, File, Path, Value

@config_component
@dataclass(frozen=True)
class AdvancedSettings:
    # 1. Only look in environment variables with a specific name
    api_key: str = Env["THIRD_PARTY_API_KEY"]

    # 2. Only look for a top-level key in files
    pool_size: int = File["database.pool.size", 10] # With a default value

    # 3. Look for a nested path within a structured file (YAML/JSON)
    #    Will look in config.yml -> services -> auth -> url
    auth_service_url: str = Path.file["services.auth.url"]

    # 4. Control the source order for a specific field
    #    For this field, the file has precedence over the environment.
    region: str = Value["aws.region", sources=("file", "env"), default="eu-west-1"]
```

## 4\. Configuration Sources (`ConfigSource`)

`pico-ioc` comes with two primary sources:

  * `EnvSource(prefix: str = "")`: Reads from environment variables. The `prefix` is optional but recommended. It will look for `PREFIX_KEY` and then `KEY`.
  * `FileSource(path: str, optional: bool = False)`: Reads from a file.
      * **Supported formats**: Automatically detects YAML, JSON, INI, and `.env` (`KEY=VALUE` format).
      * **`optional=True`**: If the file does not exist, it won't raise an error. This is very useful for environment-specific configuration files (e.g., `config.local.yml`).

## 5\. Summary of Precedence Rules

For a given configuration field, the value is resolved in the following order:

1.  **Manual Override (`Env`, `File`, etc.)**: If used, its specific rules are followed.
2.  **Automatic Lookup**:
    1.  It searches in the **first `ConfigSource`** provided in the `config` tuple during `init()`.
    2.  If not found, it checks the **second `ConfigSource`**, and so on.
3.  **Python Default Value**: If the value is not found in any source, the default value defined in the class is used (e.g., `timeout: int = 10`).
4.  **Error**: If the value isn't found in any source and the field has no default, `pico-ioc` will raise a `NameError` when trying to create the instance. Fail-fast\!
