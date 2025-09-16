# FEATURE-2025-0001: Type-Safe Configuration Injection

  - **Date:** 2025-09-16
  - **Status:** Shipped
  - **Priority:** high
  - **Related:** [ADR-0005: Type-Safe Configuration]

-----

## 1\) Summary

This feature introduces a type-safe configuration injection system for `pico-ioc`. It allows developers to define configuration settings in a dedicated class (`@config_component`), which is automatically populated from ordered sources like environment variables and property files (YAML, JSON, etc.). This simplifies managing settings across different environments and removes boilerplate `os.getenv` calls.

-----

## 2\) Goals

  - To provide a strongly-typed and centralized configuration mechanism.
  - To support multiple, ordered configuration sources, starting with environment variables and local files.
  - To offer automatic binding of configuration values to class fields by default.
  - To allow explicit, field-level overrides for custom keys or source preferences.

-----

## 3\) Non-Goals

  - This system will not support runtime reloading of configuration. Configuration is a static snapshot taken at container initialization.
  - It will not automatically scan directories for configuration files; all `FileSource`s must be explicitly declared.

-----

## 4\) User Impact / Stories (Given/When/Then)

  - **Story 1: Basic Configuration from a File**

      - **Given** a developer has a `config.yml` with `db_url: "..."`.
      - **When** they define a `Settings` class with a `db_url: str` field and initialize `pico-ioc` with `FileSource("config.yml")`.
      - **Then** the `Settings` component they retrieve from the container has its `db_url` field correctly populated from the file.

  - **Story 2: Overriding with Environment Variables**

      - **Given** a `config.yml` file sets `debug: false` and the container is initialized with `config=(EnvSource(), FileSource(...))`.
      - **When** an operator runs the application with the environment variable `APP_DEBUG=true`.
      - **Then** the injected `Settings` object has `debug` set to `True`, because `EnvSource` has higher precedence.

  - **Story 3: Mapping a Custom Key**

      - **Given** a setting is stored in a legacy environment variable named `API_SECRET`.
      - **When** the developer defines a field `api_key: str = Env["API_SECRET"]` in their config class.
      - **Then** the `api_key` field is correctly populated from the `API_SECRET` environment variable.

-----

## 5\) Scope & Acceptance Criteria

  - **In scope:**
      - `@config_component` decorator.
      - `EnvSource` and `FileSource` implementations.
      - Support for YAML, JSON, INI, and dotenv file formats.
      - Field-level overrides (`Env`, `File`, `Path`, `Value`).
      - Integration with the `pico_ioc.init` function.
  - **Out of scope:**
      - Additional source types (e.g., remote config providers like Vault or Consul).
      - Runtime configuration reloads.
  - **Acceptance:**
      - [x] `@config_component` classes are correctly identified by the scanner.
      - [x] `EnvSource` resolves values from environment variables, respecting prefixes.
      - [x] `FileSource` correctly parses supported file formats and handles the `optional` flag.
      - [x] The precedence of sources defined in `init(config=...)` is respected.
      - [x] Python default field values are used as a final fallback.
      - [x] A `NameError` is raised if a required field (with no default) cannot be resolved from any source.
      - [x] Field-level overrides (`Env`, `File`, etc.) correctly map to their specified keys and sources.

-----

## 6\) API / UX Contract

The feature introduces the following public APIs:

  - **Decorators:** `@pico_ioc.config_component(prefix: str = "")`
  - **Sources:** `pico_ioc.config.EnvSource`, `pico_ioc.config.FileSource`
  - **Field Helpers:** `pico_ioc.config.Env`, `pico_ioc.config.File`, `pico_ioc.config.Path`, `pico_ioc.config.Value`

**Example:**

```python
from dataclasses import dataclass
from pico_ioc import init, config_component
from pico_ioc.config import EnvSource, FileSource, Env

# Before: Manual, untyped, scattered
# class OldConfig:
#     DB_URL = os.getenv("DB_URL", "default_url")
#     TIMEOUT = int(os.getenv("TIMEOUT", "10"))

# After: Centralized, type-safe, declarative
@config_component(prefix="APP_")
@dataclass(frozen=True)
class Settings:
    db_url: str
    timeout: int = 10
    api_key: str = Env["LEGACY_API_KEY"]

# Bootstrap
container = init(
    "my_app",
    config=(EnvSource(prefix="APP_"), FileSource("config.yml"))
)
settings = container.get(Settings)
```

-----

## 7\) Rollout & Guardrails

  - The feature was shipped as a new, non-breaking minor feature in version **1.4.0**.
  - It is fully backward-compatible. Existing applications that do not use the `config` parameter in `init()` will continue to function without change.

-----

## 8\) Telemetry

  - The library uses the standard `logging` module. `FileSource` will log a warning if an optional file is specified but not found.
  - Success or failure of configuration loading is primarily signaled by a successful container startup or a `NameError` exception, respectively.

-----

## 9\) Risks & Open Questions

  - **Risk:** Users might be confused by the precedence rules.
      - **Mitigation:** The documentation (`GUIDE-CONFIGURATION-INJECTION.md`) includes a clear, numbered list summarizing the precedence order.
  - **Risk:** A large number of configuration files could slow down startup.
      - **Mitigation:** `FileSource` loads and parses each file only once during initialization. The performance impact is negligible for typical use cases.

-----

## 10\) Test Strategy

  - **Unit Tests:** Each `ConfigSource` is tested in isolation to verify correct parsing and value retrieval. Each field helper (`Env`, `File`, etc.) is also unit-tested.
  - **Integration Tests:** Scenarios are tested to verify the end-to-end precedence logic: `EnvSource` overriding `FileSource`, which overrides Python default values.
  - **Error Case Tests:** Tests ensure that a `NameError` is raised for missing required fields.

-----

## 11\) Milestones

  - **M1 Ready:** 2025-09-15 - Scope defined and accepted.
  - **M2 Planned:** 2025-09-15 - Implementation started.
  - **M3 Shipped:** 2025-09-16 - Feature merged, tested, and released in v1.4.0.

-----

## 12\) Documentation Impact

The following documents were created or updated:

  - **Created:** `GUIDE-CONFIGURATION-INJECTION.md`
  - **Updated:** `README.md`, `OVERVIEW.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `GUIDE.md`, `CHANGELOG.md`
