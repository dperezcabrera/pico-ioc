# ADR-002: Tree-Based Configuration Binding

> **DEPRECATED**: This decision has been superseded by ADR-010 (Unified Configuration).
> This document is kept for historical context only. Please refer to the User Guide.

Note: While the core concepts of tree-binding logic (`ConfigResolver`, `ObjectGraphBuilder`) and using `@configured` for nested structures remain valid, ADR-0010 unified the configuration system. The mechanism described here using a separate `init(tree_config=...)` argument is no longer current. Configuration sources (including tree sources like `YamlTreeSource`) are now passed to the `configuration(...)` builder, and the resulting `ContextConfig` object is passed to `init(config=...)`. The `@configured` decorator now handles both flat and tree mapping via its `mapping` parameter.

## Context

Basic configuration (via the old `@configuration` with `ConfigSource` — now removed) was suitable for flat key-value pairs but became cumbersome for complex, nested application settings common in modern microservices (e.g., configuring databases, caches, feature flags, external clients with nested properties). Manually parsing nested structures or using complex prefixes was error-prone and lacked type safety beyond simple primitives. We needed a way to map structured configuration files (like YAML or JSON) directly to Python object graphs (such as `dataclasses`).

## Decision

We introduced a dedicated tree-binding system that remains the foundation for structured configuration:

1. TreeSource Protocol: Sources that provide configuration as a nested `Mapping` (e.g., `YamlTreeSource`, `JsonTreeSource`). These are now passed to the unified `configuration(...)` builder (per ADR-0010).
2. ConfigResolver: An internal component that loads, merges (sources are layered according to `configuration(...)` order), and interpolates (`${ENV:VAR}`, `${ref:path}`) all `TreeSource`s into a single, final configuration tree.
3. ObjectGraphBuilder: An internal component that recursively maps a sub-tree (selected by a `prefix`) from the `ConfigResolver` onto a target Python type (usually a `dataclass`). It handles type coercion, nested objects, lists, dictionaries, `Union`s (with a `Discriminator`), and `Enum`s.
4. `@configured(prefix="key", mapping="tree"|"auto")` Decorator: A registration mechanism that tells the container to create a provider for the target type by using the `ObjectGraphBuilder` to map the configuration sub-tree found at `prefix`, when the `mapping` is determined to be `"tree"` (either explicitly or via `"auto"` detection).

## How It Works (Post-ADR-0010)

- Build configuration:
  - Call `configuration(...)` with the desired sources, including any tree sources such as `YamlTreeSource` and `JsonTreeSource`.
  - The builder produces a `ContextConfig`, which encapsulates the unified, merged configuration (flat and tree).
- Register structured components:
  - Annotate target types (typically `dataclasses`) with `@configured(prefix="...", mapping="tree"|"auto")`.
  - When `mapping="auto"`, the system determines whether to apply tree or flat mapping based on the target type and the configuration structure.
- Initialize the application:
  - Pass the constructed `ContextConfig` to `init(config=...)`.
  - Providers registered via `@configured` are resolved by mapping configuration subtrees into the corresponding Python object graphs.

## Mapping Rules (Summary)

- Prefix selection: `prefix` identifies the subtree to map for a given provider.
- Type coercion: Primitive types are coerced from strings/numbers as needed.
- Nested objects: Nested `dataclasses` and classes are built recursively.
- Collections: Lists and dictionaries are supported, including nested content.
- Polymorphism: `Union` types are supported via a `Discriminator` to select the concrete type.
- Enums: `Enum` values are mapped by name (and, where appropriate, by value).
- Interpolation:
  - Environment: `${ENV:VAR}` injects environment variable values.
  - References: `${ref:path}` references other nodes within the configuration tree to avoid duplication.

## Migration Notes (From Pre-ADR-0010)

- Replace `init(tree_config=...)` with `init(config=...)`.
- Use the unified `configuration(...)` builder to supply sources (both flat and tree). Pass `YamlTreeSource`/`JsonTreeSource` directly to `configuration(...)`.
- Switch existing `@configured(..., mapping="tree")` usages to rely on the new unified handling. In many cases, `mapping="auto"` may be sufficient.

## Consequences

Positive:
- Enables highly structured, type-safe configuration.
- Configuration structure directly mirrors `dataclass` definitions, improving clarity.
- Supports common formats like YAML and JSON naturally.
- Interpolation allows for dynamic values and avoids repetition.
- Decouples components from the source of configuration (env, file, etc.).
- Polymorphic configuration (`Union` + `Discriminator`) allows for flexible setup (e.g., selecting different cache backends via config).

Negative:
- The split between flat and tree systems is resolved by ADR-0010, but users must understand the mapping rules (prefix, type coercion, discriminators, `mapping` parameter).
- Adds optional dependencies for formats like YAML (`pip install pico-ioc[yaml]`).
