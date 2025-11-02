# ADR-0010: Unified Configuration via `@configured` and `ContextConfig`

**Status:** Accepted

---

## Context

Before **v2.0.0**, Pico-IoC offered two parallel mechanisms for configuration binding:
`@configuration` for flat sources and `@configured` for nested (tree) sources.
Each required a different initialization argument (`config` vs `tree_config`), duplicating both user cognitive load and internal logic.
Inconsistent ordering, normalization, and documentation made the developer experience error-prone.

Since adoption of v2.0.0 was still limited, we took the opportunity to introduce a breaking but cleaner unification, simplifying the configuration model for the long term.

**Rationale for `Value`:**
During testing and real-world deployments, we observed recurring cases where a few configuration fields needed to be *statically fixed* regardless of the environment (e.g., embedded secrets in CI, non-configurable defaults, or deterministic test fixtures).
The previous system required extra patching or post-processing.
Introducing `Annotated[..., Value(...)]` provides an explicit, type-safe, and framework-agnostic mechanism to declare immutable constants inside `@configured` classes, ensuring reproducibility and clarity while still coexisting with dynamic configuration sources.

---

## Decision

Configuration is unified around a single decorator (`@configured`) and a single runtime entry point (`configuration(...) → ContextConfig → init(config=...)`).

1. **Remove `@configuration`.**
   Only `@configured` remains.

2. **Enhance `@configured`:**

   * Signature:

     ```python
     @configured(prefix: str = "", mapping: Literal["auto","flat","tree"] = "auto")
     ```
   * Auto-detection rules:

     * If any field is a dataclass, list, dict, or `Union` → treat as `tree`.
     * If all fields are primitives (`str`, `int`, `float`, `bool`) → treat as `flat`.
     * Explicit `mapping` always overrides auto-detection.

3. **Introduce `configuration(...)` → `ContextConfig`:**

   * Accepts an ordered list of configuration sources (environment, YAML, JSON, dicts, CLI adapters, etc.).
   * Supports `overrides` and explicit values for final patching.
   * Defines deterministic precedence:
     **`Value(...)` > `overrides` > sources (left to right).**

4. **Normalize casing and key mapping:**

   * Internal attributes use `snake_case`.
   * Environment variables use `UPPER_CASE`.
   * Tree mapping uses `__` as a path separator (e.g., `APP_DB__HOST`).
   * Flat mapping uses `PREFIX_FIELD`.

5. **Unify coercion and discriminator logic** across flat and tree modes via `config_runtime`.

6. **Add Inline Field Overrides via `Annotated[..., Value(...)]`:**

   * `Value` can be applied as metadata to any field to force a constant value.
   * When present, it *short-circuits lookup*, bypassing all configuration sources.
   * Used for secrets templating in tests, static defaults, or environment-independent fallbacks.

7. **Single entry point:**

   ```python
   init(modules=[...], config=ContextConfig(...))
   ```

---

## Consequences

### Positive ✅

* **Cleaner Mental Model:**
  One decorator (`@configured`) and one initialization path (`configuration(...) → ContextConfig`) for all configuration types.

* **Deterministic Configuration:**
  Explicit, documented precedence across heterogeneous sources, with `Value(...)` providing the top-level override.

* **Inline Overrides:**
  `Annotated[..., Value(...)]` offers a standard Pythonic way to hard-code constants or test values without relying on environment setup.

* **First-Class ENV Integration:**
  Environment sources remain intuitive, with predictable normalization rules (`APP_DB_URL` → `app.db.url`).

* **Unified Mapping Strategy:**
  Flat vs. tree behavior becomes a runtime mode, not a separate decorator, reducing conceptual duplication.

* **Improved Testability:**
  The immutable, preprocessed `ContextConfig` makes configuration deterministic and easy to mock or inspect.

### Negative ⚠️

* **Breaking Change:**
  Removes `@configuration` and the old `config` argument from `init()`. Users must migrate to the unified model.

* **Migration Effort:**
  Existing classes must adopt `@configured`, update field names to match conventions, and use the `configuration(...)` builder.

* **Learning Curve:**
  Developers must understand the `mapping` modes, `ContextConfig`, and the new `Annotated[..., Value(...)]` mechanism.

* **Convention Reliance:**
  `"auto"` mode relies on consistent naming and type hints for accurate mapping inference.

---

## Alternatives Considered

* **Keep both decorators:** Rejected — duplicates logic and confuses users.
* **Force tree-mode only:** Rejected — flat ENV/CLI setups would become cumbersome.
* **Detect mode by field name casing:** Rejected — type-shape inference is more robust.

---

## Implementation Sketch

* Add `ContextConfig` and `configuration(...)` in `config_builder.py`.
* Extend `@configured` to record `prefix` and `mapping` in `PICO_META`.
* For `flat` mode: query normalized keys (`PREFIX_FIELD`).
* For `tree` mode: deep-merge sources into a composite tree and instantiate via `config_runtime`.
* Implement and document `Value(...)` and `Discriminator(...)` metadata in `config_runtime`.

---

## Migration

* Remove `@configuration` and the `tree_config` argument from `init()`.
* Replace existing usages with `@configured`.
* Update documentation and provide examples demonstrating `configuration(...)` and `Value(...)`.
* Optional: provide a script to rewrite decorators automatically.

---

## Examples

```python
from dataclasses import dataclass
from typing import Annotated
from pico_ioc import configured, configuration, EnvSource, Value, init

@configured(prefix="APP_", mapping="auto")
@dataclass
class HttpCfg:
    host: str
    port: int
    debug: bool = False
    timeout: Annotated[int, Value(60)]  # Inline override

ctx = configuration(EnvSource(prefix=""))
c = init(modules=[__name__], config=ctx)
```

```python
from dataclasses import dataclass
from typing import Annotated, Union
from pico_ioc import configured, configuration, EnvSource, Discriminator, init

@dataclass
class Postgres:
    kind: str
    host: str
    port: int

@dataclass
class Sqlite:
    kind: str
    path: str

@configured(prefix="DB_", mapping="tree")
@dataclass
class DbCfg:
    model: Annotated[Union[Postgres, Sqlite], Discriminator("kind")]

ctx = configuration(EnvSource(prefix=""))
c = init(modules=[__name__], config=ctx)
```

