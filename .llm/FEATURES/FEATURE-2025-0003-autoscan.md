# FEATURE-2025-0002: Modular Scanning with auto\_scan

  - **Date:** 2025-09-14
  - **Status:** Shipped
  - **Priority:** high
  - **Related:** [ADR-0007: Decoupled Package Scanning]

-----

## 1\) Summary

This feature introduces the `auto_scan` parameter to the `pico_ioc.init` function, allowing the container to discover components from multiple, independent Python packages beyond the main root package. This facilitates modular application design, simplifies the integration of third-party libraries providing pico-ioc components, and keeps the application's composition root clean and declarative.

-----

## 2\) Goals

  - To enable the discovery of components from any number of specified Python packages.
  - To simplify the integration of external or internal libraries into the IoC container.
  - To provide a "strict" mode to enforce that all scanned packages must be available.
  - To keep the application bootstrap process centralized in a single `init` call.

-----

## 3\) Non-Goals

  - It will not automatically scan the entire `sys.path` or filesystem for packages; all packages must be explicitly listed.
  - It is not responsible for installing missing packages; it assumes they are already in the Python environment.

-----

## 4\) User Impact / Stories (Given/When/Then)

  - **Story 1: Modular Application**

      - **Given** an application is split into a `core` package and an `api` package, each with its own components.
      - **When** the developer initializes the container with `init("core", auto_scan=["api"])`.
      - **Then** components from both the `core` and `api` packages are correctly registered and can be injected into each other.

  - **Story 2: Integrating a Third-Party Library**

      - **Given** an application uses a library like `pico_ioc_feature_toggle` which provides an interceptor.
      - **When** the developer calls `init("my_app", auto_scan=["pico_ioc_feature_toggle"])`.
      - **Then** the `FeatureToggleInterceptor` from the external library is automatically discovered and activated.

  - **Story 3: Optional Package with Non-Strict Mode**

      - **Given** a deployment might be missing an optional integration package, e.g., `optional_monitoring_plugin`.
      - **When** the container is initialized with `init(..., auto_scan=["optional_monitoring_plugin"])` and `strict_autoscan` is `False` (the default).
      - **Then** the application starts successfully with a logged warning about the missing package, instead of crashing.

-----

## 5\) Scope & Acceptance Criteria

  - **In scope:**
      - `auto_scan: Sequence[str]` parameter in the `init` function.
      - `strict_autoscan: bool` parameter in the `init` function.
      - `auto_scan_exclude: Callable` parameter to filter modules within auto-scanned packages.
      - Integration with `importlib` to dynamically load modules.
  - **Out of scope:**
      - Support for scanning non-package sources (e.g., zip files, remote URLs).
  - **Acceptance:**
      - [x] Packages listed in `auto_scan` are successfully imported and scanned.
      - [x] Components, factories, and interceptors from `auto_scan` packages are registered in the container.
      - [x] If `strict_autoscan=False`, a missing package logs a warning and does not raise an exception.
      - [x] If `strict_autoscan=True`, a missing package raises an `ImportError`.
      - [x] The `auto_scan_exclude` filter is correctly applied to modules discovered during the scan.

-----

## 6\) API / UX Contract

The feature is exposed through parameters in the `pico_ioc.init` function signature:

```python
def init(
    root_package,
    *,
    # ... other parameters
    auto_scan: Sequence[str] = (),
    auto_scan_exclude: Optional[Callable[[str], bool]] = None,
    strict_autoscan: bool = False,
) -> PicoContainer:
    # ...
```

**Example:**

```python
# main.py
from pico_ioc import init
from demo_app.service import MyService

# init() now scans both the main app and our feature toggle library.
# The FeatureToggleInterceptor is found and activated automatically.
container = init("demo_app", auto_scan=["pico_ioc_feature_toggle"])

service = container.get(MyService)
# ...
```

-----

## 7\) Rollout & Guardrails

  - This is a fundamental feature of the `pico-ioc` core API and has been stable across major versions.
  - The default behavior (`strict_autoscan=False`) is safe for production environments where optional packages might be missing. It is recommended to use `strict_autoscan=True` in development and CI to catch typos and dependency issues early.

-----

## 8\) Telemetry

  - The `logging` module is used to report warnings for missing packages when `strict_autoscan` is `False`.
  - Errors during module import are logged at the `ERROR` level if strict mode is enabled.

-----

## 9\) Risks & Open Questions

  - **Risk:** Typos in package names in the `auto_scan` list can lead to silent failures (components not being registered).
      - **Mitigation:** The `strict_autoscan=True` flag provides an immediate failure, which should be used during development and testing to prevent such issues.
  - **Risk:** Scanning many large packages could potentially slow down application startup.
      - **Mitigation:** The feature is designed for targeted scanning of necessary packages. Users should be encouraged to specify only the packages containing components relevant to the application's composition root.

-----

## 10\) Test Strategy

  - **Unit Tests:** The `init` function is tested to verify its handling of the `auto_scan` and `strict_autoscan` parameters.
  - **Integration Tests:** End-to-end tests confirm that a component defined in an `auto_scan` package can be successfully resolved and injected into a component from the `root_package`.
  - **Error Case Tests:** Tests ensure that the correct behavior (warning vs. exception) occurs for missing packages in both strict and non-strict modes.

-----

## 11\) Milestones

  - **M1 Ready:** N/A (Core feature from early design).
  - **M2 Planned:** N/A.
  - **M3 Shipped:** This feature has been a stable part of the core API since pre-1.0 releases.

-----

## 12\) Documentation Impact

  - The feature is documented in `GUIDE.md` and `ARCHITECTURE.md`.
  - It is demonstrated in practical examples within `GUIDE_CREATING_PLUGINS_AND_INTERCEPTORS.md`.
  - The `init` function's docstring clearly explains the `auto_scan` and `strict_autoscan` parameters.
