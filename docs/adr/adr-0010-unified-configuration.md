# ADR-0010: Unified Configuration via `@configured` and `ContextConfig`

**Status:** Accepted

## Context

Before v2.0.0, Pico-IoC offered two parallel mechanisms for binding configuration:
`@configuration` for flat sources and `@configured` for nested (tree) sources. Each used
a different initialization argument (`config` vs `tree_config`), duplicating both user
cognitive load and internal logic. Ordering pitfalls, normalization inconsistencies, and
documentation fragmentation made the experience error-prone.

Given that v2.0.0 is not widely adopted yet, we can introduce a breaking cleanup that
simplifies usage without harming existing users.

## Decision

We unify configuration into a single model centered on `@configured` and a runtime builder
`configuration(...)` that produces a `ContextConfig` object consumable by `init(...)`.

1. Remove `@configuration`. There is only `@configured` going forward.
2. Enhance `@configured`:
   - Signature: `@configured(prefix: str = "", mapping: Literal["auto","flat","tree"]="auto")`
   - Auto-detection rules:
     - If any field is a dataclass, list, dict, or Union → treat as `tree`.
     - If all fields are primitives (`str`, `int`, `float`, `bool`) → treat as `flat`.
     - An explicit `mapping` parameter always overrides auto-detection.
3. Introduce `configuration(...)` that returns a `ContextConfig`:
   - Accepts an ordered list of sources (ENV, dicts, files, CLI adapters, etc.).
   - Accepts `overrides` and `values` for last-mile patching.
   - Defines deterministic precedence: `Value(...)` > `overrides` > sources (left to right).
4. Normalize casing and keys:
   - Code uses `snake_case`.
   - ENV uses `UPPER_CASE`.
   - For tree mapping, `__` is the path separator in ENV (e.g. `APP_DB__HOST`).
   - For flat mapping, `PREFIX_FIELD`.
5. Apply the same coercion and discriminator logic for both flat and tree, reusing the
   existing type system from `config_runtime`.
6. `init(modules=[...], config=ContextConfig(...))` is the single entry-point for configuration.

## Consequences

Okay, here's the "Consequences" section split into Positive and Negative points, as requested:

## Consequences

**Positive:** 👍

  * **Cleaner Mental Model:** Establishes a single, coherent API with one primary decorator (`@configured`) and one way to provide configuration (`ContextConfig` via the `configuration(...)` builder).
  * **Deterministic Configuration:** Provides clear, documented rules for precedence and merging across heterogeneous sources (ENV, files, dicts), managed by the `configuration(...)` builder.
  * **First-Class Environment Variables:** Environment variables remain easy to integrate via source adapters like `EnvTreeSource`, with precise normalization rules ensuring predictable mapping to code conventions (e.g., `APP_DB_URL` -> `app.db.url`).
  * **Unified Mapping Strategy:** Flat vs. tree binding is no longer a fork in the API but a behavioral mode of `@configured`, selected either by convention (auto-detection) or explicitly (`mapping=...`), simplifying component definition.
  * **Explicit Overrides:** `Annotated[..., Value(...)]` provides a clear, standard Python mechanism for field-level overrides, enhancing explicitness when needed.
  * **Improved Testability:** The immutable, pre-processed `ContextConfig` object makes configuration state predictable and easier to mock or inspect during tests.

**Negative:** 👎

  * **Breaking Change:** Completely removes the `@configuration` decorator and the `config` argument from `init()`, requiring mandatory code changes for users relying on the old flat configuration system.
  * **Migration Effort:** Users must refactor existing `@configuration` classes to use `@configured`, ensuring field names match the `ALL_CAPS` convention for flat mapping auto-detection or explicitly setting `mapping="flat"`. They also need to adopt the `configuration(...)` builder pattern.
  * **Reliance on Convention:** The success of `mapping="auto"` for flat configurations depends on users adhering to the `ALL_CAPS` naming convention for relevant fields.
  * **Learning Curve:** Users need to learn the new `configuration(...)` builder API, the `ContextConfig` object, the `mapping` parameter, and the `Annotated[..., Value(...)]` syntax for overrides.

## Alternatives Considered

- Keep both decorators: rejected due to duplication and increased complexity.
- Always tree: rejected; common ENV/CLI patterns are more ergonomic in flat mode.
- Auto-detect based on ALL_CAPS field names: rejected; using type-shape is more robust.

## Implementation Sketch

- Add `ContextConfig` and `configuration(...)` in a dedicated module.
- Extend `@configured` to store `prefix` and `mapping` in `PICO_META`.
- For `flat`, query flat sources with normalized `PREFIX_FIELD` keys.
- For `tree`, fold sources into a merged tree (deep-merge) and build the object
  with `config_runtime`.
- Ensure `Value(...)` and `Annotated[..., Discriminator("type")]` keep working.

## Migration

- Remove `@configuration` and `tree_config` arguments from `init(...)`.
- Provide a short migration guide and replace examples in docs.
- Optional: a small script to rewrite decorator usages.


## Examples

```python
from dataclasses import dataclass
from typing import Annotated
from pico_ioc import configured, configuration, EnvSource, DictSource, init

@configured(prefix="APP_", mapping="auto")
@dataclass
class HttpCfg:
    host: str
    port: int
    debug: bool = False

ctx = configuration(
    EnvSource(prefix=""),            # flat env
    DictSource({"app": {"http": {}}})  # tree dict, if needed elsewhere
)
c = init(modules=[__name__], config=ctx)
```

```python
from dataclasses import dataclass
from typing import Annotated, Union
from pico_ioc import configured, configuration, EnvSource, DictSource, Discriminator, init

@configured(prefix="DB_", mapping="tree")
@dataclass
class Postgres:
    kind: str
    host: str
    port: int

@configured(prefix="DB_", mapping="tree")
@dataclass
class Sqlite:
    kind: str
    path: str

@configured(prefix="DB_", mapping="tree")
@dataclass
class DbCfg:
    model: Annotated[Union[Postgres, Sqlite], Discriminator("kind")]

ctx = configuration(
    EnvSource(prefix=""),                   # e.g. DB_MODEL=Postgres, DB_MODEL__HOST=...
)
c = init(modules=[__name__], config=ctx)
```


