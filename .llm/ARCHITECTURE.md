# pico-ioc — Architecture

> **Scope:** internal model, wiring algorithm, lifecycle, and design trade-offs.
> **Non-goals:** tutorials/recipes (see `GUIDE_CREATING_PLUGINS_AND_INTERCEPTORS.md`), product pitch.
>
> ⚠️ **Requires Python 3.10+** (uses `typing.Annotated` with `include_extras=True`).

---

## 1) Design goals & non-goals

### Goals

  - **Tiny, predictable DI** for Python apps (CLIs, Flask/FastAPI, services).
  - **Fail fast** at bootstrap; deterministic resolution.
  - **Ergonomic**: typed constructors; minimal reflection; explicit decorators.
  - **Framework-agnostic**: no hard deps on web frameworks.
  - **Safe by default**: thread/async-friendly; no global mutable singletons.

### Non-goals

  - Full Spring feature set (complex scopes, bean post-processors).
  - Hot reload or runtime graph mutation beyond explicit overrides.
  - Magical filesystem-wide auto-imports.

---

## 2) High-level model

  - **Component** → class marked with `@component`. Instantiated by the container.
  - **Config Component** → class marked with `@config_component`. Instantiated and populated from external sources like files or environment variables.
  - **Factory component** → class marked with `@factory_component`; owns provider methods via `@provides(key=TypeOrToken)`. Providers return *externals* (e.g., `Flask`, DB clients).
  - **Infrastructure** → class marked with `@infrastructure`. Discovered automatically to apply cross-cutting logic, such as registering interceptors.
  - **Container** → built by `pico_ioc.init(mod_or_list, ...)`; resolve with `container.get(KeyOrType)`.

### Bootstrap sequence

```mermaid
sequenceDiagram
    participant App as Your package(s)
    participant IOC as pico-ioc Container
    App->>IOC: init(packages, config, ...)
    IOC->>IOC: Create ConfigRegistry from sources
    IOC->>App: scan decorators (@component, @config_component, @infrastructure)
    IOC->>IOC: register providers and collect infrastructure declarations
    IOC->>IOC: build and activate infrastructure (which registers interceptors)
    IOC->>IOC: apply policy (e.g., @primary, @on_missing aliases)
    IOC->>IOC: apply overrides (replace providers/constants)
    IOC->>IOC: instantiate eager components
    App->>IOC: get(Service)
    IOC->>IOC: resolve dependencies (with interception)
    IOC-->>App: instance(Service)
```

---

## 3\) Discovery & registration

1.  **Scan inputs** passed to `init(...)`: module or list of modules/packages.
2.  **Collect**:
      * `@component` classes → registered by a **key** (defaults to the class type).
      * `@config_component` classes → registered as special components whose instances are built from external configuration sources.
      * `@factory_component` classes → introspected for `@provides(key=...)` methods.
      * `@infrastructure` classes → collected for activation.
      * `@plugin` classes → if explicitly passed via `init(..., plugins=(...))`.
3.  **Registry** (frozen after bootstrap):
      * Map **key → provider**. Keys are typically **types**; string tokens are also supported.

**Precedence:** If multiple providers are active for the same key (e.g., one with `@primary`, another regular), a deterministic policy is applied to choose the winner. Direct overrides are applied last, having the final say.

---

## 4\) Resolution algorithm (deterministic)

When constructing a component `C`:

1.  Inspect `__init__(self, ...)`; collect **type-annotated** parameters (excluding `self`).
2.  For each parameter `p: T`, resolve by this order:
    1.  **By name**: if a provider key matches the parameter name `p` (if `prefer_name_first=True`).
    2.  **Exact type** `T`.
    3.  **MRO walk**: first registered base class of `T`.
    4.  **By name (fallback)**: if a provider key matches the parameter name `p`.
3.  Instantiate dependencies depth-first; cache singletons.
4.  Construct `C` with resolved instances.

### Failure modes

  * **No provider** for a required key → **bootstrap error** (fail fast) with a full dependency chain.
  * **Ambiguous/incompatible** registrations → policy resolves to a single provider or raises an error.

### 4b) Collection resolution

If the constructor requests `list[T]` or `list[Annotated[T, Q]]`:

  * Return **all** compatible providers for `T`.
  * If `Q` (qualifier) is present, filter to matching ones.
  * Registration order is preserved; no implicit sorting.
  * Returns an empty list if no matches.

---

## 5\) Lifecycles & scopes

  * **Singleton per container**: a provider is instantiated at most once and cached.
  * **Lazy proxies (optional)**: `@component(lazy=True)` or `@provides(lazy=True)` defers instantiation until first use via a `ComponentProxy`. Prefer eager to catch errors early.

**Rationale:** Most Python app composition (config, clients, web apps) fits singleton-per-container; it’s simple and fast.

---

## 6\) Factories & providers

Use `@factory_component` for **externals** (framework apps, DB clients, engines).

```python
from pico_ioc import factory_component, provides
from flask import Flask

@factory_component
class AppFactory:
    @provides(key=Flask)
    def provide_flask(self) -> Flask:
        app = Flask(__name__)
        app.config["JSON_AS_ASCII"] = False
        return app
```

Guidelines:

  * Providers should be **pure constructors** (no long-running work).
  * Prefer **typed keys** (e.g., `Flask`) over strings.

---

## 7\) Concurrency model

  * Container state is **immutable after init**.
  * Caches & resolution are **thread/async safe** (internal isolation; no global singletons).
  * Instances you create **must** be safe for your usage patterns; the container cannot fix non-thread-safe libraries.

---

## 8\) Error handling & diagnostics

  * **Bootstrap**:
      * Missing providers → explicit `NameError` with full dependency chain details.
      * Duplicate keys → resolved by policy, preferring `@primary`.
  * **Runtime**:
      * Exceptions from providers/constructors bubble up. The resolver path is included in the error for easier debugging.

**Tip:** Keep constructors **cheap**; push I/O to explicit start/serve methods.

---

## 9\) Configuration

Configuration is treated as a first-class, type-safe component using a dedicated injection system.

1.  **Define a Config Class**: Create a class (preferably a `dataclass`) and mark it with `@config_component`. An optional `prefix` can be used for environment variables.

    ```python
    from pico_ioc import config_component
    from dataclasses import dataclass

    @config_component(prefix="APP_")
    @dataclass(frozen=True)
    class Settings:
        db_url: str
        timeout: int = 30
    ```

2.  **Provide Sources**: At bootstrap, pass an ordered tuple of `ConfigSource` objects to the `config` parameter of `init()`. The order defines precedence (first source wins).

    ```python
    from pico_ioc import init
    from pico_ioc.config import EnvSource, FileSource

    container = init(
        "my_app",
        config=(
            EnvSource(prefix="APP_"), # Highest priority
            FileSource("config.prod.yml", optional=True),
            FileSource("config.yml"), # Lowest priority
        ),
    )
    ```

3.  **Inject and Use**: Inject the config class into other components just like any other dependency.

    ```python
    from pico_ioc import component

    @component
    class Database:
        def __init__(self, settings: Settings):
            self.connection = connect(settings.db_url)
    ```

### Resolution Logic

  - **Automatic Binding**: By default, `pico-ioc` binds fields automatically. For a field like `db_url`, it checks for keys like `APP_DB_URL` (in `EnvSource`), `DB_URL`, or `db_url` (in `FileSource`).
  - **Manual Overrides**: For more complex cases where keys don't align, you can use field-level helpers like `Env["CUSTOM_VAR"]`, `File["key.in.file"]`, or `Path.file["nested.key"]` to specify the exact key to use.

This system ensures that configuration is **type-safe**, **externalized**, and **testable**, while remaining simple for the common cases.

---

## 10\) Overrides & composition

### 10.1 Module-ordered overrides

The policy engine respects definition order. While not a strict "last-wins", providers marked `@primary` will take precedence over others discovered during the scan.

### 10.2 Direct overrides argument

`init()` accepts an `overrides` dictionary for ad-hoc replacement.

```python
c = init(app, overrides={
    Repo: FakeRepo(),                  # constant instance
    "fast_model": lambda: {"mock": True}, # provider
    "expensive": (lambda: object(), True), # provider with lazy=True
})
```

**Semantics:**

  * Applied **after scanning and policy** but before eager instantiation → replaced providers never run.
  * Accepted forms:
      * `key: instance`
      * `key: callable`
      * `key: (callable, lazy_bool)`
  * With `reuse=True`, re-calling `init()` with different `overrides` will create a new container, not mutate a cached one, as the configuration fingerprint changes.

---

## 11\) Interceptors (AOP & Lifecycle Hooks)

Interceptors apply cross-cutting logic like logging, metrics, or policy enforcement. They are **not discovered automatically**. Instead, they must be registered by an `@infrastructure` component during the container's bootstrap phase.

This is a two-step process:

1.  **Define the Interceptor**: Create a class that implements the `MethodInterceptor` or `ContainerInterceptor` protocol.
2.  **Register it via an Infrastructure Component**: Create a class decorated with `@infrastructure` and use the `infra.intercept.add()` method inside its `configure` function to activate the interceptor and define which components it applies to.

### Method Interceptors

These implement the `MethodInterceptor` protocol and wrap method calls on any component, enabling Aspect-Oriented Programming (AOP). They are ideal for tracing, timing, caching, or feature toggles.

```python
from pico_ioc import infrastructure
from pico_ioc.infra import Infra, Select
from pico_ioc.interceptors import MethodInterceptor, MethodCtx

# 1. Define the Interceptor
class LoggingInterceptor(MethodInterceptor):
    def invoke(self, ctx: MethodCtx, call_next):
        print(f"Calling {ctx.name}...")
        result = call_next(ctx)
        print(f"Finished {ctx.name}.")
        return result

# 2. Register it
@infrastructure
class MyInfra:
    def configure(self, infra: Infra):
        infra.intercept.add(
            interceptor=LoggingInterceptor(),
            where=Select().class_name(".*") # Apply to all components
        )
```

### Container Interceptors

These implement the `ContainerInterceptor` protocol and hook into the container's internal lifecycle events.

**Hook points**:

  * `around_resolve(self, ctx: ResolveCtx, call_next)`: Wraps the dependency resolution process for a specific key.
  * `around_create(self, ctx: CreateCtx, call_next)`: Wraps the instantiation of a component. It can modify the provider or even return a completely different instance.

---

## 12\) Profiles & conditional providers

Use `@conditional` to **activate providers based on profiles, environment variables, or a predicate function**.

```python
from pico_ioc import component, conditional

class Cache: ...

@component
@conditional(profiles=("prod", "staging"))
class RedisCache(Cache): ...

@component
@conditional(require_env=("REDIS_URL",))
class AnotherRedisCache(Cache): ...

@component
@conditional(predicate=lambda: os.path.exists("/tmp/use_mem"))
class InMemoryCache(Cache): ...
```

**Rules**:

  * `profiles=("A","B")` → active if any profile passed to `init()` or `scope()` matches.
  * `require_env=("A","B")` → all environment variables must exist and be non-empty.
  * `predicate=callable` → must return a truthy value to activate.
  * If no active provider satisfies a required type and something depends on it → **bootstrap error** (fail fast).

---

## 13\) Qualifiers & collection injection

Attach qualifiers to group/select implementations using `@qualifier`.

  * Request `list[T]` → injects all registered implementations of `T`.
  * Request `list[Annotated[T, Q]]` → injects only those implementations of `T` tagged with qualifier `Q`.

This preserves registration order and returns a stable list.

---

## 14\) Plugins

`@plugin` classes implementing the `PicoPlugin` protocol can observe the **container lifecycle**.

  * `before_scan(package, binder)`
  * `after_scan(package, binder)`
  * `after_bind(container, binder)`
  * `before_eager(container, binder)`
  * `after_ready(container, binder)`

Plugins are passed **explicitly** via `init(..., plugins=(MyPlugin(),))`. Prefer **infrastructure** for fine-grained wiring events; use **plugins** for coarse lifecycle integration.

---

## 15\) Scoped subgraphs (`scope`)

Build a **bounded container** containing only dependencies reachable from selected **roots**.

```python
from pico_ioc import scope
from src.runner_service import RunnerService
from tests.fakes import FakeDocker
import src

c = scope(
    modules=[src],
    roots=[RunnerService],
    overrides={"docker.DockerClient": FakeDocker()},
    strict=True, lazy=True,
)
svc = c.get(RunnerService)
```

### Tag-based pruning

Providers may carry `tags` (via `@component(tags=...)` or `@provides(..., tags=...)`). `scope()` can filter the initial set of providers using `include_tags` and `exclude_tags` before traversing the dependency graph.

### Semantics

  * **Limited reach**: only providers transitively reachable from `roots` are included in the final graph.
  * **Deterministic precedence**: `overrides > scoped providers > base container providers` (if `strict=False`).
  * **Strict mode**: controls whether missing dependencies raise an error (`True`) or can be resolved from the `base` container (`False`).
  * **Lifecycle**: still **singleton-per-container**; `scope` does **not** add request/session scopes.
  * **Context manager**: `with scope(...):` is supported.

**Use cases:** fast unit tests, integration-lite, CLI tools, microbenchmarks.

---

## 16\) Diagnostics & diagrams

### Registry & resolution (class diagram)

```mermaid
classDiagram
    class PicoContainer {
      +get(key) instance
      +get_all(base_type) sequence
      +add_method_interceptor(it)
      +add_container_interceptor(it)
      - _providers: Map[key, ProviderMeta]
      - _singletons: Map[key, instance]
    }
    class ProviderMeta {
      + factory: Callable
      + lazy: bool
      + tags: tuple
      + qualifiers: tuple
    }
    class MethodInterceptor {
      +invoke(ctx, call_next)
    }
    class ContainerInterceptor {
      +around_resolve(ctx, call_next)
      +around_create(ctx, call_next)
    }
    PicoContainer "1" o-- "*" MethodInterceptor
    PicoContainer "1" o-- "*" ContainerInterceptor
```

### Resolution flow (activity)

```mermaid
flowchart TD
    A[get(Type T)] --> B{Cached?}
    B -- yes --> Z[Return cached instance]
    B -- no --> D[Resolve dependencies for T (recurse)]
    D --> I_BEFORE[ContainerInterceptors: around_create]
    I_BEFORE --> F[Instantiate T]
    F -- exception --> I_EXC[Error bubbles up]
    F -- success --> H[Wrap with MethodInterceptors if needed]
    H --> I_AFTER[around_create returns instance]
    I_AFTER --> G[Cache instance]
    G --> Z
```

---

## 17\) Rationale & trade-offs

  * **Typed keys first**: better IDE support; fewer foot-guns than strings.
  * **Singleton-per-container**: matches typical Python app composition; simpler mental model.
  * **Explicit decorators**: determinism and debuggability over magical auto-wiring.
  * **Fail fast**: configuration and graph issues surface at startup, not mid-request.
  * **Interceptors via Infrastructure**: precise, opt-in hooks without the complexity of auto-discovery.

---

**TL;DR**
`pico-ioc` builds a **deterministic, typed dependency graph** from decorated components, factories, and infrastructure. It resolves by **type** (with qualifiers and collections), memoizes **singletons**, supports **type-safe configuration injection**, **overrides**, **plugins**, **conditionals/profiles**, and **scoped subgraphs**—keeping wiring **predictable, testable, and framework-agnostic**.


