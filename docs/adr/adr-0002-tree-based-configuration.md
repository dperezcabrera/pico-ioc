# ADR-002: Tree-Based Configuration Binding

**Status:** Accepted (Partially Superseded by [ADR-0010](./adr-0010-unified-configuration.md))

> **Note:** While the core concepts of **tree-binding logic** (`ConfigResolver`, `ObjectGraphBuilder`) and using `@configured` for nested structures remain valid, **ADR-0010 unified the configuration system**. The mechanism described here using a separate `init(tree_config=...)` argument is **no longer current**. Configuration sources (including tree sources like `YamlTreeSource`) are now passed to the `configuration(...)` builder, and the resulting `ContextConfig` object is passed to `init(config=...)`. The `@configured` decorator now handles both flat and tree mapping via its `mapping` parameter.

## Context

Basic configuration (`@configuration` with `ConfigSource` - *now removed*) was suitable for flat key-value pairs but became cumbersome for complex, nested application settings common in modern microservices (e.g., configuring databases, caches, feature flags, external clients with nested properties). Manually parsing nested structures or using complex prefixes was error-prone and lacked type safety beyond simple primitives. We needed a way to map structured configuration files (like YAML or JSON) directly to Python object graphs (like `dataclasses`).

## Decision

We introduced a **dedicated tree-binding system**:

1.  **`TreeSource` Protocol:** Defined sources that provide configuration as a nested `Mapping` (e.g., `YamlTreeSource`, `JsonTreeSource`). These are now passed to the **`configuration(...)` builder** *(updated per ADR-0010)*.
2.  **`ConfigResolver`:** An internal component that loads, merges (sources are layered according to `configuration(...)` order), and interpolates (`${ENV:VAR}`, `${ref:path}`) all `TreeSource`s into a single, final configuration tree.
3.  **`ObjectGraphBuilder`:** An internal component that recursively maps a sub-tree (selected by a `prefix`) from the `ConfigResolver` onto a target Python type (usually a `dataclass`). It handles type coercion, nested objects, lists, dictionaries, `Union`s (with `Discriminator`), and `Enum`s.
4.  **`@configured(prefix="key", mapping="tree"|"auto")` Decorator:** *(Updated per ADR-0010)* A registration mechanism that tells `pico-ioc` to create a provider for the target type by using the `ObjectGraphBuilder` to map the configuration sub-tree found at `prefix`, when the `mapping` is determined to be `"tree"` (either explicitly or via `"auto"` detection).

## Consequences

**Positive:** 👍
* Enables highly structured, type-safe configuration.
* Configuration structure directly mirrors `dataclass` definitions, improving clarity.
* Supports common formats like YAML and JSON naturally.
* Interpolation allows for dynamic values and avoids repetition.
* Decouples components from the *source* of configuration (env, file, etc.).
* Polymorphic configuration (`Union` + `Discriminator`) allows for flexible setup (e.g., selecting different cache backends via config).

**Negative:** 👎
* *(Original negative points about having two systems are mostly resolved by ADR-0010)*
* Requires understanding the mapping rules (prefix, type coercion, discriminators, `mapping` parameter).
* Adds optional dependencies for formats like YAML (`pip install pico-ioc[yaml]`).
