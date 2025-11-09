# 📦 Pico-IoC: A Robust, Async-Native IoC Container for Python

[![PyPI](https://img.shields.io/pypi/v/pico-ioc.svg)](https://pypi.org/project/pico-ioc/)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/dperezcabrera/pico-ioc)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
![CI (tox matrix)](https://github.com/dperezcabrera/pico-ioc/actions/workflows/ci.yml/badge.svg)
[![codecov](https://codecov.io/gh/dperezcabrera/pico-ioc/branch/main/graph/badge.svg)](https://codecov.io/gh/dperezcabrera/pico-ioc)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=dperezcabrera_pico-ioc&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=dperezcabrera_pico-ioc)
[![Duplicated Lines (%)](https://sonarcloud.io/api/project_badges/measure?project=dperezcabrera_pico-ioc&metric=duplicated_lines_density)](https://sonarcloud.io/summary/new_code?id=dperezcabrera_pico-ioc)
[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=dperezcabrera_pico-ioc&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=dperezcabrera_pico-ioc)
[![PyPI Downloads](https://static.pepy.tech/personalized-badge/pico-ioc?period=monthly&units=INTERNATIONAL_SYSTEM&left_color=BLACK&right_color=GREEN&left_text=Monthly+downloads)](https://pepy.tech/projects/pico-ioc)
[![Docs](https://img.shields.io/badge/docs-pico--ioc-blue?style=for-the-badge&logo=readthedocs)](https://dperezcabrera.github.io/pico-ioc/)
[![Interactive Lab](https://img.shields.io/badge/learn-online-green?style=for-the-badge&logo=python)](https://dperezcabrera.github.io/learn-pico-ioc/)


**Pico-IoC** is a **lightweight, async-ready, decorator-driven IoC container** built for clarity, testability, and performance.
It brings Inversion of Control and dependency injection to Python in a deterministic, modern, and framework-agnostic way.

> 🐍 Requires Python 3.10+

---

## ⚖️ Core Principles

- Single Purpose – Do one thing: dependency management.
- Declarative – Use simple decorators (`@component`, `@factory`, `@provides`, `@configured`) instead of complex config files.
- Deterministic – No hidden scanning or side-effects; everything flows from an explicit `init()`.
- Async-Native – Fully supports async providers, async lifecycle hooks (`__ainit__`), and async interceptors.
- Fail-Fast – Detects missing bindings and circular dependencies at bootstrap (`init()`).
- Testable by Design – Use `overrides` and `profiles` to swap components instantly.
- Zero Core Dependencies – Built entirely on the Python standard library. Optional features may require external packages (see Installation).

---

## 🚀 Why Pico-IoC?

As Python systems evolve, wiring dependencies by hand becomes fragile and unmaintainable.
Pico-IoC eliminates that friction by letting you declare how components relate — not how they’re created.

| Feature         | Manual Wiring                  | With Pico-IoC                   |
| :-------------- | :----------------------------- | :------------------------------ |
| Object creation | `svc = Service(Repo(Config()))` | `svc = container.get(Service)`  |
| Replacing deps  | Monkey-patch                   | `overrides={Repo: FakeRepo()}`  |
| Coupling        | Tight                          | Loose                           |
| Testing         | Painful                        | Instant                         |
| Async support   | Manual                         | Built-in (`aget`, `__ainit__`)  |

---

## 🧩 Highlights (v2.0+)

- Unified Configuration: Use `@configured` to bind both flat (ENV-like) and tree (YAML/JSON) sources via the `configuration(...)` builder (ADR-0010).
- Async-aware AOP system: Method interceptors via `@intercepted_by`.
- Scoped resolution: singleton, prototype, request, session, transaction, and custom scopes.
- `UnifiedComponentProxy`: Transparent `lazy=True` and AOP proxy supporting serialization.
- Tree-based configuration runtime: Advanced mapping with reusable adapters and discriminators (`Annotated[Union[...], Discriminator(...)]`).
- Observable container context: Built-in stats, health checks (`@health`), observer hooks (`ContainerObserver`), dependency graph export (`export_graph`), and async cleanup.

---

## 📦 Installation

```bash
pip install pico-ioc
```

Optional extras:

- YAML configuration support (requires PyYAML)

  ```bash
  pip install pico-ioc[yaml]
  ```

-----

## ⚙️ Quick Example (Unified Configuration)

```python
import os
from dataclasses import dataclass
from pico_ioc import component, configured, configuration, init, EnvSource

# 1. Define configuration with @configured
@configured(prefix="APP_", mapping="auto")  # Auto-detects flat mapping
@dataclass
class Config:
    db_url: str = "sqlite:///demo.db"

# 2. Define components
@component
class Repo:
    def __init__(self, cfg: Config):  # Inject config
        self.cfg = cfg
    def fetch(self):
        return f"fetching from {self.cfg.db_url}"

@component
class Service:
    def __init__(self, repo: Repo):  # Inject Repo
        self.repo = repo
    def run(self):
        return self.repo.fetch()

# --- Example Setup ---
os.environ['APP_DB_URL'] = 'postgresql://user:pass@host/db'

# 3. Build configuration context
config_ctx = configuration(
    EnvSource(prefix="")  # Read APP_DB_URL from environment
)

# 4. Initialize container
container = init(modules=[__name__], config=config_ctx)  # Pass context via 'config'

# 5. Get and use the service
svc = container.get(Service)
print(svc.run())

# --- Cleanup ---
del os.environ['APP_DB_URL']
```

Output:

```
fetching from postgresql://user:pass@host/db
```

-----

## 🧪 Testing with Overrides

```python
class FakeRepo:
    def fetch(self): return "fake-data"

# Build configuration context (might be empty or specific for test)
test_config_ctx = configuration()

# Use overrides during init
container = init(
    modules=[__name__],
    config=test_config_ctx,
    overrides={Repo: FakeRepo()}  # Replace Repo with FakeRepo
)

svc = container.get(Service)
assert svc.run() == "fake-data"
```

-----

## 🧰 Profiles

Use profiles to enable/disable components or configuration branches conditionally.

```python
# Enable "test" profile when bootstrapping the container
container = init(
    modules=[__name__],
    profiles=["test"]
)
```

Profiles are typically referenced in decorators or configuration mappings to include/exclude components and bindings.

-----

## ⚡ Async Components

Pico-IoC supports async lifecycle and resolution.

```python
import asyncio
from pico_ioc import component, init

@component
class AsyncRepo:
    async def __ainit__(self):
        # e.g., open async connections
        self.ready = True

    async def fetch(self):
        return "async-data"

async def main():
    container = init(modules=[__name__])
    repo = await container.aget(AsyncRepo)   # Async resolution
    print(await repo.fetch())

asyncio.run(main())
```

- `__ainit__` runs after construction if defined.
- Use `container.aget(Type)` to resolve components that require async initialization or whose providers are async.

-----

## 🩺 Lifecycle & AOP

```python
import time
from pico_ioc import component, init, intercepted_by, MethodInterceptor, MethodCtx

# Define an interceptor component
@component
class LogInterceptor(MethodInterceptor):
    def invoke(self, ctx: MethodCtx, call_next):
        print(f"→ calling {ctx.cls.__name__}.{ctx.name}")
        start = time.perf_counter()
        try:
            res = call_next(ctx)
            duration = (time.perf_counter() - start) * 1000
            print(f"← {ctx.cls.__name__}.{ctx.name} done ({duration:.2f}ms)")
            return res
        except Exception as e:
            duration = (time.perf_counter() - start) * 1000
            print(f"← {ctx.cls.__name__}.{ctx.name} failed ({duration:.2f}ms): {e}")
            raise

@component
class Demo:
    @intercepted_by(LogInterceptor)  # Apply the interceptor
    def work(self):
        print("   Working...")
        time.sleep(0.01)
        return "ok"

# Initialize container (must scan module containing interceptor too)
c = init(modules=[__name__])
result = c.get(Demo).work()
print(f"Result: {result}")
```

Output:

```
→ calling Demo.work
   Working...
← Demo.work done (10.xxms)
Result: ok
```

-----

## 👁️ Observability & Cleanup

- Export a dependency graph in DOT format:

  ```python
  c = init(modules=[...])
  dot = c.export_graph()  # Returns DOT graph as a string
  with open("dependencies.dot", "w") as f:
      f.write(dot)
  ```

- Health checks:
  - Annotate health probes inside components with `@health` for container-level reporting.
  - The container exposes health information that can be queried in observability tooling.

- Container cleanup:
  - For sync components: `container.close()`
  - For async components/resources: `await container.aclose()`

Use cleanup in application shutdown hooks to release resources deterministically.

-----

## 📖 Documentation

The full documentation is available within the `docs/` directory of the project repository. Start with `docs/README.md` for navigation.

- Getting Started: `docs/getting-started.md`
- User Guide: `docs/user-guide/README.md`
- Advanced Features: `docs/advanced-features/README.md`
- Observability: `docs/observability/README.md`
- Integrations: `docs/integrations/README.md`
- Cookbook (Patterns): `docs/cookbook/README.md`
- Architecture: `docs/architecture/README.md`
- API Reference: `docs/api-reference/README.md`
- ADR Index: `docs/adr/README.md`

-----

## 🧩 Development

```bash
pip install tox
tox
```

-----

## 🧾 Changelog

See [CHANGELOG.md](./CHANGELOG.md) — Significant redesigns and features in v2.0+.

-----

## 📜 License

MIT — [LICENSE](https://opensource.org/licenses/MIT)
