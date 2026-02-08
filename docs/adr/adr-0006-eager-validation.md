# ADR-006: Eager Startup Validation

**Status:** Accepted

## Context

Dependency Injection containers often defer resolving dependencies until a component is actually requested at runtime. This can lead to unexpected `ProviderNotFoundError` or `CircularDependencyError` exceptions during operation (e.g., in the middle of a user request), which is disruptive and difficult to debug, especially in production environments. We prioritize application stability, predictability, and detecting configuration errors as early as possible.

---

## Decision

We decided to implement eager validation during the `init()` process:

1. Discovery and selection: After discovering all components (`@component`, `@factory`, `@provides`, `@configured`) and selecting the effective providers based on profiles, conditions, and rules (`Registrar.select_and_bind`), the `Registrar._validate_bindings` method performs a static analysis of the resulting dependency graph.
2. Dependency inspection: For each registered component (excluding those explicitly marked with `lazy=True`), the validator inspects the type annotations of the constructor (`__init__`) or the factory/provider method (`@provides`) from which it originates.
3. Provider verification: For each required dependency (identified by its type annotation or a string key), it verifies whether a corresponding provider exists in the finalized `ComponentFactory`. List injections (e.g., `Annotated[List[Type], Qualifier]`) are also handled by checking that at least one matching provider exists (unless the list is optional or has a default value).
4. Early failure: If any required dependency cannot be satisfied for a non-lazy component, `init()` immediately raises an `InvalidBindingError`, listing all unsatisfied dependencies detected during the validation scan. Circular dependencies are often detected during this analysis phase or on the first actual resolution attempt, raising a `CircularDependencyError`.

---

## Scope and Limitations

- What is validated:
  - `__init__` signatures and signatures of methods/functions annotated with `@provides`.
  - Type annotations per PEP 484/PEP 593 (including `Annotated[...]`, `Optional[T]`/`T | None`, parameters with default values).
  - Collection/multi-injections (e.g., `List[T]` with qualifier) requiring at least one provider when the parameter is required.
- What is not validated:
  - Constructor execution or runtime logic within factory/provider methods.
  - Providers registered dynamically after `init()` or components loaded by plugins after startup.
  - Dependencies only reachable through components marked with `lazy=True` (their trees are not traversed).
  - Conditions depending on runtime state that have not been resolved before `Registrar.select_and_bind`.

---

## Implementation Details

- Execution order:
  - Component and rule discovery.
  - Profile/condition resolution and provider selection via `Registrar.select_and_bind`.
  - Construction of the final provider map in `ComponentFactory`.
  - `Registrar._validate_bindings` traverses non-lazy components and validates their dependencies.
- Required dependency resolution:
  - Parameters without default values and not annotated as optional are considered required.
  - Dependencies identified by type, string key, or qualifier (e.g., via `Annotated[..., Qualifier]`) must have at least one selected provider.
  - For collections (`List[T]`, `Iterable[T]`), at least one matching provider is required unless the parameter is optional or has a default value.
- Handling of optionals and default values:
  - `Optional[T]` or `T | None` parameters and/or those with default values do not cause an error if no provider exists.
  - For collections, a default value (e.g., empty list) disables the provider existence requirement.
- Lazy components:
  - Components with `lazy=True` are not deeply validated; their resolution and potential associated errors are deferred until first access.
- Cycle detection:
  - Graph edges are generated between non-lazy components based on their required dependencies. If an obvious cycle is detected, a `CircularDependencyError` is raised. Some cycles may manifest on the first actual resolution if they are not statically deducible.
- Error reporting:
  - `InvalidBindingError` aggregates and deduplicates all detected missing dependencies, indicating the source component, parameter, and unsatisfied criterion (type/key/qualifier) to facilitate debugging.

---

## Alternatives Considered

- On-demand resolution (lazy-only):
  - Pros: faster startup.
  - Cons: failures in production at non-deterministic times, worse debugging experience, lower deployment confidence.
- Partial validation:
  - Pros: compromise between startup cost and safety.
  - Cons: leaves undetected error windows for critical components.
- External compile-time/linter validation:
  - Pros: early feedback in CI.
  - Cons: does not always have visibility into active profiles/conditions or the actual set of providers at runtime.

---

## Consequences

Positive:
- Significantly reduces wiring errors at runtime: Most common issues such as missing components, key typos, or unsatisfied dependencies are detected at startup, before serving requests.
- Improves developer confidence: A successful `init()` largely guarantees that the core dependency graph is resolvable (except for runtime errors within constructors/methods).
- Clear error reporting: `InvalidBindingError` lists all issues detected during validation, accelerating debugging.

Negative:
- Slight increase in startup time: Validation adds overhead to `init()` by inspecting signatures and querying the provider map. This is usually negligible but may be noticeable in extremely large applications.
- `lazy=True` components skip full validation: Dependencies required only by components marked as lazy may not be validated until first access (a deliberate trade-off of `lazy=True`).

---

## Adoption and Migration Guide

- Annotate constructor parameters and `@provides` methods with precise types. Unannotated or ambiguous parameters may not resolve properly.
- Ensure that for every type/key/qualifier required by non-lazy components in the active profile, at least one provider is selected after `Registrar.select_and_bind`.
- Mark optional dependencies using `Optional[T]`/`T | None` or define default values on parameters to avoid errors when their absence is acceptable.
- For collection injections, provide at least one binding or set a default value (e.g., empty list) if absence is semantically valid.
- Use `lazy=True` on components whose validation/resolution cost should be consciously deferred, accepting the risk of errors on first access.
- If using profiles/conditions, ensure they are configured before `init()` so that provider selection is consistent with the target environment.

---

## Validation Result Examples

- Missing required dependency:
  - Component A requires `ServiceX` without a default value or `Optional` and no provider for `ServiceX` exists in the active profile -> `InvalidBindingError`.
- List injection without providers:
  - Component B requires `List[Plugin]` and no `Plugin` providers are registered -> `InvalidBindingError` (unless the parameter has a default value or is optional).
- Cycle between non-lazy components:
  - A requires B and B requires A -> `CircularDependencyError` during validation or on the first resolution attempt.
- Unsatisfied optional dependency:
  - Component C has `repo: Optional[Repo] = None` and no `Repo` provider exists -> not considered an error.
