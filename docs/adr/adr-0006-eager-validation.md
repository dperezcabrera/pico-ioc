# ADR-006: Eager Startup Validation ✅

**Status:** Accepted

## Context

Dependency Injection containers often defer resolving dependencies until a component is actually requested at runtime. This can lead to unexpected `ProviderNotFoundError` or `CircularDependencyError` exceptions during operation (e.g., in the middle of a user request), which are disruptive and hard to debug, especially in production environments. We prioritized application stability, predictability, and catching configuration errors as early as possible. 💣➡️😌

---

## Decision

We decided to implement **eager validation** during the `init()` process:

1.  **Dependency Graph Analysis:** After discovering all components (`@component`, `@factory`, `@provides`, `@configured`) and selecting the primary providers based on profiles, conditions, and rules (`Registrar.select_and_bind`), the `Registrar._validate_bindings` method performs a static analysis of the potential dependency graph.
2.  **Check Dependencies:** For every registered component (excluding those explicitly marked with `lazy=True`), the validator inspects the type hints of its constructor (`__init__`) or the factory method (`@provides`) it originates from.
3.  **Verify Providers:** For each required dependency (identified by its type hint or string key), it checks if a corresponding provider exists in the finalized `ComponentFactory`. It also handles list injections (e.g., `Annotated[List[Type], Qualifier]`) by ensuring *at least one* provider matches the criteria (unless the list itself is optional or has a default).
4.  **Fail Fast:** If any required dependency cannot be satisfied for a non-lazy component, `init()` raises an `InvalidBindingError` **immediately**, listing all unsatisfied dependencies found during the validation scan. Circular dependencies are also often caught during this analysis phase or upon the first *actual* resolution attempt, raising a `CircularDependencyError`. 💥

---

## Consequences

**Positive:** 👍
* **Significantly reduces runtime wiring errors:** Most common issues like missing components, typos in keys, or unsatisfied dependencies are caught at application startup, *before* handling any requests.
* **Improves Developer Confidence:** A successful `init()` provides a strong guarantee that the core dependency graph is resolvable (barring runtime errors *within* component constructors/methods themselves). ✅
* **Clear Error Reporting:** The `InvalidBindingError` clearly lists all problems detected during validation, making debugging much faster. 🕵️‍♀️

**Negative:** 👎
* **Slightly Increased Startup Time:** The validation step adds a small overhead to the `init()` call, as it needs to inspect function signatures and query the provider map. This is typically negligible for most applications but could be noticeable in extremely large applications with thousands of components. ⏱️
* **`lazy=True` Components Bypass Full Validation:** Dependencies required *only* by components marked `lazy=True` might not have their own dependencies fully validated at startup. This could potentially defer a `ProviderNotFoundError` until the lazy component is first accessed (this is a deliberate trade-off for using `lazy=True`). 🤔

