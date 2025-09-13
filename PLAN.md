# Implementation Plan: Aligning Code with Documentation

**Objective:** This plan outlines the necessary steps to implement features that are described in the project's documentation but are currently missing or incomplete in the source code. The goal is to achieve full coherence between the documentation and the implementation, ensuring a predictable and reliable experience for users.

There are two major features to address:

1.  **Full Lifecycle Interceptor API**
2.  **`predicate` Support for `@conditional` Decorator**

-----

## Epic 1: Implement Full Lifecycle Interceptor API

**User Story:** As a developer, I want to hook into the container's lifecycle events (like dependency resolution and component creation) so that I can implement cross-cutting concerns such as logging, metrics, transaction management, or security policies.

### Acceptance Criteria

1.  The main `pico_ioc.init()` function accepts an `interceptors` argument.
2.  A clear `Interceptor` protocol is defined with hooks for the container lifecycle: `on_resolve`, `on_before_create`, `on_after_create`, and `on_exception`.
3.  The container correctly triggers these hooks at the appropriate points during dependency resolution and instantiation.
4.  The `on_after_create` hook can wrap or replace the component instance before it's cached and returned.
5.  The existing `MethodInterceptor` functionality for intercepting method calls remains unaffected.
6.  The new functionality is covered by comprehensive unit tests.

### Tasks

1.  **Refine `Interceptor` Protocol:**

      * Define the final `Interceptor` protocol in `interceptors.py`.
      * Specify the exact method signatures, for example:
        ```python
        class LifecycleInterceptor(Protocol):
            def on_resolve(self, key: Any, ...) -> None: ...
            def on_before_create(self, key: Any) -> None: ...
            def on_after_create(self, key: Any, instance: Any) -> Any: ... # Returns instance
            def on_exception(self, key: Any, exception: Exception) -> None: ...
        ```

2.  **Update Public API (`api.py`):**

      * Add an `interceptors: Optional[list[LifecycleInterceptor]] = None` parameter to the `init()` function.
      * Pass this list to the `PicoContainer` instance upon its creation.

3.  **Integrate into `PicoContainer` (`container.py`):**

      * Modify the `PicoContainer.__init__` to accept and store the lifecycle interceptors.
      * Implement a dispatcher method within the container to run all registered interceptors for a given hook.

4.  **Implement `on_resolve` Hook:**

      * Modify `Resolver._resolve_param` to trigger the `on_resolve` hook just before it attempts to `container.get()` a dependency. This will provide visibility into what the container is looking for.

5.  **Implement Creation Hooks (`on_before_create`, `on_after_create`):**

      * In `PicoContainer.get`, before creating a new instance, trigger the `on_before_create` hook.
      * After the instance is created but *before* it is stored in the `_singletons` cache, trigger the `on_after_create` hook.
      * The value returned from `on_after_create` should be the one that is cached and returned to the caller, allowing the interceptor to replace or wrap the original instance.

6.  **Implement `on_exception` Hook:**

      * Wrap the core instantiation logic inside `PicoContainer.get` with a `try...except` block.
      * In the `except` block, trigger the `on_exception` hook, passing the key and the caught exception. The hook should be required to re-raise the exception to avoid masking errors.

7.  **Write Unit Tests:**

      * Create a test suite specifically for `LifecycleInterceptor`.
      * Verify that each hook is called with the correct arguments at the right time.
      * Write a test to confirm that returning a different object from `on_after_create` successfully replaces the component instance.
      * Test that exceptions are correctly reported via `on_exception`.

-----

## Epic 2: Add `predicate` Support to `@conditional` Decorator

**User Story:** As a developer, I want to enable or disable components based on custom, dynamic logic—not just environment variables or profiles—so that I can implement complex feature flags or configurations that depend on the application's state.

### Acceptance Criteria

1.  The `@conditional` decorator in `decorators.py` accepts a `predicate: Callable[[], bool]` argument.
2.  The core policy logic in `core_policy.py` correctly executes the provided predicate to determine if a component should be active.
3.  If a `predicate` is provided, it takes precedence or is logically combined with `profiles` and `require_env` checks. The documented behavior suggests an `OR` combination.
4.  The new functionality is covered by unit tests.

### Tasks

1.  **Update `@conditional` Decorator (`decorators.py`):**

      * Modify the function signature to accept a new optional argument: `predicate: Optional[Callable[[], bool]] = None`.
      * Store the predicate function in the `CONDITIONAL_META` dictionary attached to the decorated object.

2.  **Update Core Policy Logic (`core_policy.py`):**

      * Modify the `_conditional_active` function.
      * It should first check for `profiles` and `require_env` as it does now.
      * Then, it should check if a `predicate` exists in the metadata.
      * If the predicate exists, call it. The component is active if the predicate returns `True` OR if the other conditions (`profiles`, `require_env`) are met.

3.  **Write Unit Tests:**

      * Add a test case where a component is decorated with `@conditional(predicate=lambda: True)` and assert that it is included in the container.
      * Add a test case where a component is decorated with `@conditional(predicate=lambda: False)` and assert that it is excluded.
      * Test the interaction with other conditions, such as having a `profile` match but a `predicate` that returns `False`. Ensure the logic is correct (e.g., `True or False -> True`).
