# FEATURE-2025-0002: Interceptor Auto-Registration and Conditional Providers

  - **Date:** 2025-09-14
  - **Status:** Removed
  - **Priority:** high
  - **Related:** [ADR-0006: Declarative Cross-Cutting Concerns],[FEATURE-2025-0006]

-----

## 1\) Summary

This feature introduces the `@interceptor` decorator to automatically discover, instantiate, and activate interceptors, simplifying how cross-cutting concerns like logging or transactions are applied. Additionally, it introduces the `@conditional` decorator, allowing any component (including interceptors) to be activated based on profiles, environment variables, or custom logic predicates. This enhances both the extensibility and environment-specific configuration of the container.

-----

## 2\) Goals

  - To automate the discovery and registration of both `MethodInterceptor` and `ContainerInterceptor` implementations.
  - To allow developers to define interceptors alongside their business logic, improving modularity.
  - To provide a mechanism (`@conditional`) for activating or deactivating any component based on external factors without code changes.
  - To support metadata for interceptor ordering (`order`) and conditional activation (`profiles`, etc.).

-----

## 3\) Non-Goals

  - This feature does not change the underlying `MethodInterceptor` or `ContainerInterceptor` protocols.
  - It does not introduce a complex Aspect-Oriented Programming (AOP) model beyond method interception.

-----

## 4\) User Impact / Stories (Given/When/Then)

  - **Story 1: Automatic Logging Interceptor**

      - **Given** a developer writes a `LoggingInterceptor` class that implements `MethodInterceptor`.
      - **When** they decorate the class with `@interceptor`.
      - **Then** all component method calls are automatically intercepted and logged without any manual registration code.

  - **Story 2: Environment-Specific Component**

      - **Given** an `InMemoryCache` component should only be used for local development and testing.
      - **When** the developer decorates it with `@conditional(profiles=["dev", "test"])`.
      - **Then** the `InMemoryCache` is only active when the container is initialized with the "dev" or "test" profile, and a `RedisCache` marked with `@conditional(profiles=["prod"])` can be used in production.

  - **Story 3: Controlling Interceptor Order**

      - **Given** a developer has a `TimingInterceptor` and a `SecurityInterceptor`.
      - **When** they decorate them with `@interceptor(order=10)` and `@interceptor(order=20)` respectively.
      - **Then** the `TimingInterceptor` will wrap the `SecurityInterceptor`, ensuring the total execution time is measured correctly.

-----

## 5\) Scope & Acceptance Criteria

  - **In scope:**
      - `@interceptor` decorator with `kind`, `order`, and conditional parameters.
      - `@conditional` decorator with `profiles`, `require_env`, and `predicate` parameters.
      - Integration with the scanner to discover these decorators on classes, methods, and functions.
      - Integration with the builder to instantiate and register active interceptors.
      - Integration with the policy engine to filter out inactive conditional components.
  - **Out of scope:**
      - Pointcut expressions or more advanced AOP features.
  - **Acceptance:**
      - [x] The scanner correctly identifies classes and functions decorated with `@interceptor`.
      - [x] The builder correctly instantiates interceptors, injecting their dependencies.
      - [x] The `order` parameter correctly influences the interceptor chain.
      - [x] Components decorated with `@conditional` are only registered if their conditions (profiles, env vars, predicate) are met.
      - [x] An inactive component causes a `NameError` at bootstrap if it's a required dependency for an eager component.

-----

## 6\) API / UX Contract

The feature introduces the following public APIs:

  - **Decorators:** `pico_ioc.interceptor(...)`, `pico_ioc.conditional(...)`

**Example (Interceptor):**

```python
from pico_ioc import interceptor, component
from pico_ioc.interceptors import MethodInterceptor, Invocation
import time

# Before: No standard mechanism for registration.

# After: Simple, declarative, and auto-discovered.
@interceptor(order=-100)
class TimingInterceptor(MethodInterceptor):
    def __call__(self, inv: Invocation, proceed):
        start = time.time()
        result = proceed()
        duration = time.time() - start
        print(f"{inv.method_name} took {duration:.2f}s")
        return result

@component
class MyService:
    def do_work(self):
        time.sleep(1)

# In main.py, `init("my_app")` is enough. The interceptor is found and applied.
```

-----

## 7\) Rollout & Guardrails

  - The feature was shipped as a new, non-breaking minor feature in version **1.3.0**.
  - It is fully backward-compatible. Existing components without these decorators are unaffected.

-----

## 8\) Telemetry

  - The `pico-ioc` builder logs at the `DEBUG` level which interceptors are activated and which are skipped due to conditional rules, aiding in diagnostics.

-----

## 9\) Risks & Open Questions

  - **Risk:** The interaction between multiple conditionals or complex predicates could be confusing for users.
      - **Mitigation:** The documentation provides clear examples for each conditional type and emphasizes the fail-fast nature of the container if a required dependency becomes inactive.

-----

## 10\) Test Strategy

  - **Unit Tests:** The `@interceptor` and `@conditional` decorators are tested to ensure they attach the correct metadata.
  - **Integration Tests:** Scenarios verify that the scanner, builder, and policy engine work together to activate/deactivate components and interceptors based on profiles and environment variables. Tests for interceptor ordering are included.

-----

## 11\) Milestones

  - **M1 Ready:** 2025-09-13 - Scope defined and accepted.
  - **M2 Planned:** 2025-09-13 - Implementation started.
  - **M3 Shipped:** 2025-09-14 - Feature merged, tested, and released in v1.3.0.

-----

## 12\) Documentation Impact

The following documents were created or updated:

  - **Created:** `GUIDE_CREATING_PLUGINS_AND_INTERCEPTORS.md`
  - **Updated:** `ARCHITECTURE.md`, `DECISIONS.md`, `GUIDE.md`, `CHANGELOG.md`, `README.md`, `OVERVIEW.md`
