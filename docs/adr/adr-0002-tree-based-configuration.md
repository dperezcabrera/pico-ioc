## ADR-002: Tree-Based Configuration Binding

**Status:** Accepted

### Context

Basic configuration (`@configuration` with `ConfigSource`) is suitable for flat key-value pairs but becomes cumbersome for complex, nested application settings common in modern microservices (e.g., configuring databases, caches, feature flags, external clients with nested properties). Manually parsing nested structures or using complex prefixes is error-prone and lacks type safety beyond simple primitives. We needed a way to map structured configuration files (like YAML or JSON) directly to Python object graphs (like `dataclasses`).

### Decision

We introduced a **dedicated tree-binding system**:

1.  **`TreeSource` Protocol:** Defined sources that provide configuration as a nested `Mapping` (e.g., `YamlTreeSource`, `JsonTreeSource`). These are passed to `init(tree_config=...)`.
2.  **`ConfigResolver`:** An internal component that loads, merges (sources are layered), and interpolates (`${ENV:VAR}`, `${ref:path}`) all `TreeSource`s into a single, final configuration tree.
3.  **`ObjectGraphBuilder`:** An internal component that recursively maps a sub-tree (selected by a `prefix`) from the `ConfigResolver` onto a target Python type (usually a `dataclass`). It handles type coercion, nested objects, lists, dictionaries, `Union`s (with `$type` or custom `Discriminator`), and `Enum`s.
4.  **`@configured(target=Type, prefix="key")` Decorator:** A registration mechanism that tells `pico-ioc` to create a provider for the `target` type by using the `ObjectGraphBuilder` to map the configuration sub-tree found at `prefix`.

### Consequences

**Positive:** 👍
* Enables highly structured, type-safe configuration.
* Configuration structure directly mirrors `dataclass` definitions, improving clarity.
* Supports common formats like YAML and JSON naturally.
* Interpolation allows for dynamic values and avoids repetition.
* Decouples components from the *source* of configuration (env, file, etc.).
* Polymorphic configuration (`Union` + `Discriminator`) allows for flexible setup (e.g., selecting different cache backends via config).

**Negative:** 👎
* Introduces a second configuration system alongside the basic `@configuration`.
* Requires understanding the mapping rules (prefix, type coercion, discriminators).
* Adds optional dependencies for formats like YAML (`pip install pico-ioc[yaml]`).
