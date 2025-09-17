# FEATURE-2025-0001: Scoped Subgraphs with scope()

  - **Date:** 2025-09-13
  - **Status:** Delivered
  - **Priority:** high
  - **Related:** [ADR-0008: Lightweight Test Containers]

-----

## 1\) Summary

This feature introduces `pico_ioc.scope()`, a powerful factory function for creating lightweight, temporary containers limited to a specific dependency subgraph. By defining one or more `roots`, the container will only include components and services required by those roots. This is extremely useful for fast, isolated unit and integration tests, as well as for CLI tools or serverless functions that only need a subset of the application's full dependency graph.

-----

## 2\) Goals

  - To provide a mechanism for creating minimal IoC containers for testing or specialized tasks.
  - To drastically reduce the overhead and complexity of bootstrapping the full application graph for a limited use case.
  - To improve test performance by only scanning and instantiating necessary components.
  - To allow fine-grained graph pruning through tag-based filtering.

-----

## 3\) Non-Goals

  - `scope()` does not introduce new lifecycle scopes (like "request" or "session"). Components are still singletons within the created container.
  - It is not intended to replace the main `pico_ioc.init()` for bootstrapping the full application.

-----

## 4\) User Impact / Stories (Given/When/Then)

  - **Story 1: Isolated Service Test**

      - **Given** a developer wants to test `RunnerService`, which depends on `Repo` but not on `WebService`.
      - **When** they create a container with `scope(modules=["my_app"], roots=[RunnerService])`.
      - **Then** the container contains `RunnerService` and `Repo`, but not `WebService`, making the test setup faster and more focused.

  - **Story 2: Mocking Dependencies in a Test**

      - **Given** a developer is testing a service that depends on an external `DockerClient`.
      - **When** they use `scope(..., roots=[MyService], overrides={"docker.DockerClient": FakeDocker()})`.
      - **Then** the `MyService` instance they retrieve from the container is injected with the `FakeDocker` mock instead of the real one.

  - **Story 3: Pruning a Subgraph with Tags**

      - **Given** an application has multiple `Notifier` implementations tagged with `"email"` or `"sms"`.
      - **When** a developer builds a scope for a specific task using `scope(..., include_tags={"sms"})`.
      - **Then** only the `SmsNotifier` and its dependencies are included in the graph, while the `EmailNotifier` is excluded.

-----

## 5\) Scope & Acceptance Criteria

  - **In scope:**
      - `pico_ioc.scope()` function with `modules`, `roots`, `overrides`, `strict`, `lazy`, `include_tags`, and `exclude_tags` parameters.
      - Graph traversal logic to compute the dependency subgraph from the given roots.
      - Tag filtering logic to prune providers before graph traversal.
      - Support for use as a context manager.
  - **Out of scope:**
      - Runtime modification of a created scope.
  - **Acceptance:**
      - [x] A container created with `scope()` only contains providers transitively reachable from the specified `roots`.
      - [x] The `overrides` parameter correctly replaces providers within the subgraph.
      - [x] `strict=True` raises a `NameError` if a dependency cannot be found within the subgraph.
      - [x] `include_tags` and `exclude_tags` correctly filter the set of available providers before the subgraph is calculated.
      - [x] The `scope()` function works correctly when used as a `with` statement context manager.

-----

## 6\) API / UX Contract

The feature is exposed through the `pico_ioc.scope()` function:

```python
def scope(
    *,
    modules: Iterable[Any] = (),
    roots: Iterable[type] = (),
    overrides: Optional[Dict[Any, Any]] = None,
    strict: bool = True,
    lazy: bool = True,
    include_tags: Optional[set[str]] = None,
    exclude_tags: Optional[set[str]] = None,
) -> PicoContainer:
    # ...
```

**Example:**

```python
# In a test file
from pico_ioc import scope
from src.runner_service import RunnerService
from tests.fakes import FakeDocker
import src

def test_runner_in_isolation():
    # Create a container with only what RunnerService needs
    with scope(
        modules=[src],
        roots=[RunnerService],
        overrides={"docker.DockerClient": FakeDocker()},
        strict=True,
    ) as container:
        service = container.get(RunnerService)
        # ... assertions
```

-----

## 7\) Rollout & Guardrails

  - The feature was shipped as a new, non-breaking minor feature in version **1.2.0**.
  - It is fully backward-compatible and does not affect the existing `init()` function.

-----

## 8\) Telemetry

  - The `pico-ioc` builder logs at the `INFO` level when a scope container is ready, which can be useful for debugging test setups.

-----

## 9\) Risks & Open Questions

  - **Risk:** Developers might misunderstand `scope()` as a lifecycle feature (e.g., request scope) rather than a container construction tool.
      - **Mitigation:** The documentation explicitly states that components are still singletons within the scope and that `scope()` is primarily for testing and specialized tasks.

-----

## 10\) Test Strategy

  - **Unit Tests:** The graph traversal algorithm (`_compute_allowed_subgraph`) and tag filtering logic are unit-tested.
  - **Integration Tests:** End-to-end tests verify that `scope()` correctly builds containers for various scenarios, including complex dependency chains, overrides, and strict mode enforcement.

-----

## 11\) Milestones

  - **M1 Ready:** 2025-09-12 - Scope defined and accepted.
  - **M2 Planned:** 2025-09-12 - Implementation started.
  - **M3 Shipped:** 2025-09-13 - Feature merged, tested, and released in v1.2.0.

-----

## 12\) Documentation Impact

  - The feature is documented in `GUIDE.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `CHANGELOG.md`, `README.md`, and `OVERVIEW.md`.
  - Practical examples for testing are included in the main user guide.
