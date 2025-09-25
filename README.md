# 📦 Pico-IoC: A Robust, Async-Native IoC Container for Python

[![PyPI](https://img.shields.io/pypi/v/pico-ioc.svg)](https://pypi.org/project/pico-ioc/)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/dperezcabrera/pico-ioc)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
![CI (tox matrix)](https://github.com/dperezcabrera/pico-ioc/actions/workflows/ci.yml/badge.svg)
[![codecov](https://codecov.io/gh/dperezcabrera/pico-ioc/branch/main/graph/badge.svg)](https://codecov.io/gh/dperezcabrera/pico-ioc)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=dperezcabrera_pico-ioc&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=dperezcabrera_pico-ioc)
[![Duplicated Lines (%)](https://sonarcloud.io/api/project_badges/measure?project=dperezcabrera_pico-ioc&metric=duplicated_lines_density)](https://sonarcloud.io/summary/new_code?id=dperezcabrera_pico-ioc)
[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=dperezcabrera_pico-ioc&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=dperezcabrera_pico-ioc)

**Pico-IoC** is a **lightweight, async-ready, decorator-driven IoC container** built for clarity, testability, and performance.
It brings *Inversion of Control* and *dependency injection* to Python in a deterministic, modern, and framework-agnostic way.

> 🐍 Requires **Python 3.10+**

---

## ⚖️ Core Principles

-   **Single Purpose** – Do one thing: dependency management.
-   **Declarative** – Use simple decorators (`@component`, `@factory`, `@configuration`) instead of config files or YAML magic.
-   **Deterministic** – No hidden scanning or side-effects; everything flows from an explicit `init()`.
-   **Async-Native** – Fully supports async providers, async lifecycle hooks, and async interceptors.
-   **Fail-Fast** – Detects missing bindings and circular dependencies at bootstrap.
-   **Testable by Design** – Use `overrides` and `profiles` to swap components instantly.
-   **Zero Core Dependencies** – Built entirely on the Python standard library. Optional features may require external packages (see Installation).

---

## 🚀 Why Pico-IoC?

As Python systems evolve, wiring dependencies by hand becomes fragile and unmaintainable.
**Pico-IoC** eliminates that friction by letting you declare how components relate — not how they’re created.

| Feature        | Manual Wiring              | With Pico-IoC                   |
| :------------- | :------------------------- | :------------------------------ |
| Object creation| `svc = Service(Repo(Config()))` | `svc = container.get(Service)`  |
| Replacing deps | Monkey-patch               | `overrides={Repo: FakeRepo()}`  |
| Coupling       | Tight                      | Loose                           |
| Testing        | Painful                    | Instant                         |
| Async support  | Manual                     | Built-in                        |

---

## 🧩 Highlights (v2.0.0)

-   **Full redesign:** unified architecture with simpler, more powerful APIs.
-   **Async-aware AOP system** — method interceptors via `@intercepted_by`.
-   **Typed configuration** — dataclasses with JSON/YAML/env sources.
-   **Scoped resolution** — singleton, prototype, request, session, transaction.
-   **UnifiedComponentProxy** — transparent lazy/AOP proxy supporting serialization.
-   **Tree-based configuration runtime** with reusable adapters and discriminators.
-   **Observable container context** with stats, health checks, and async cleanup.

---

## 📦 Installation

```bash
pip install pico-ioc
```

For optional features, you can install extras:

  * **YAML Configuration:**

    ```bash
    pip install pico-ioc[yaml]
    ```

    (Requires `PyYAML`)

  * **Dependency Graph Export:**

    ```bash
    pip install pico-ioc[graphviz]
    ```

    (Requires the `graphviz` Python package and the Graphviz command-line tools)

-----

## ⚙️ Quick Example

```python
from dataclasses import dataclass
from pico_ioc import component, configuration, init

@configuration
@dataclass
class Config:
    db_url: str = "sqlite:///demo.db"

@component
class Repo:
    def __init__(self, cfg: Config):
        self.cfg = cfg
    def fetch(self):
        return f"fetching from {self.cfg.db_url}"

@component
class Service:
    def __init__(self, repo: Repo):
        self.repo = repo
    def run(self):
        return self.repo.fetch()

container = init(modules=[__name__])
svc = container.get(Service)
print(svc.run())
```

**Output:**

```
fetching from sqlite:///demo.db
```

-----

## 🧪 Testing with Overrides

```python
class FakeRepo:
    def fetch(self): return "fake-data"

container = init(modules=[__name__], overrides={Repo: FakeRepo()})
svc = container.get(Service)
assert svc.run() == "fake-data"
```

-----

## 🩺 Lifecycle & AOP

```python
from pico_ioc import intercepted_by, MethodInterceptor, MethodCtx

class LogInterceptor(MethodInterceptor):
    def invoke(self, ctx: MethodCtx, call_next):
        print(f"→ calling {ctx.name}")
        res = call_next(ctx)
        print(f"← {ctx.name} done")
        return res

@component
class Demo:
    @intercepted_by(LogInterceptor)
    def work(self):
        return "ok"

c = init(modules=[__name__])
c.get(Demo).work()
```

-----

## 📖 Documentation

The full documentation is available within the `docs/` directory of the project repository. Start with `docs/README.md` for navigation.

  * **Getting Started:** `docs/getting-started.md`
  * **User Guide:** `docs/user-guide/README.md`
  * **Advanced Features:** `docs/advanced-features/README.md`
  * **Observability:** `docs/observability/README.md`
  * **Integrations:** `docs/integrations/README.md`
  * **Cookbook (Patterns):** `docs/cookbook/README.md`
  * **Architecture:** `docs/architecture/README.md`
  * **API Reference:** `docs/api-reference/README.md`
  * **ADR Index:** `docs/adr/README.md`

-----

## 🧩 Development

```bash
pip install tox
tox
```

-----

## 🧾 Changelog

See [CHANGELOG.md](./CHANGELOG.md) — *Full redesign for v2.0.0.*

-----

## 📜 License

MIT — [LICENSE](https://opensource.org/licenses/MIT)

