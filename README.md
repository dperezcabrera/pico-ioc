# 📦 Pico-IoC: A Minimalist IoC Container for Python

[![PyPI](https://img.shields.io/pypi/v/pico-ioc.svg)](https://pypi.org/project/pico-ioc/)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/dperezcabrera/pico-ioc)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
![CI (tox matrix)](https://github.com/dperezcabrera/pico-ioc/actions/workflows/ci.yml/badge.svg)
[![codecov](https://codecov.io/gh/dperezcabrera/pico-ioc/branch/main/graph/badge.svg)](https://codecov.io/gh/dperezcabrera/pico-ioc)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=dperezcabrera_pico-ioc&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=dperezcabrera_pico-ioc)
[![Duplicated Lines (%)](https://sonarcloud.io/api/project_badges/measure?project=dperezcabrera_pico-ioc&metric=duplicated_lines_density)](https://sonarcloud.io/summary/new_code?id=dperezcabrera_pico-ioc)
[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=dperezcabrera_pico-ioc&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=dperezcabrera_pico-ioc)

**pico-ioc** is a **tiny, zero-dependency, decorator-based IoC container for Python**.  
It helps you build loosely-coupled, testable apps without manual wiring. Inspired by the Spring ecosystem, but minimal.

> ⚠️ **Requires Python 3.10+** (uses `typing.Annotated` and `include_extras=True`).

---

## ⚖️ Principles

* **Focus & Simplicity**: A minimal core for one job: managing dependencies. It avoids accidental complexity by doing one thing well.
* **Predictable & Explicit**: No magic. Behavior is deterministic, relying on explicit decorators and a clear resolution order.
* **Unified Composition Root**: The application is assembled from a single entry point (`init`) which defines a clear, predictable boundary. This ensures a stable and understandable bootstrap process.
* **Fail-Fast Bootstrap**: Catches dependency graph errors at startup, not in production. If the application runs, it's wired correctly.
* **Testability First**: Features like `scope()` and `overrides` are first-class citizens, enabling fast and isolated testing.
* **Extensible by Design**: Lifecycle hooks and AOP are available through a clean Plugin and Interceptor API without altering the core.
* **Framework Agnostic**: Zero hard dependencies. It works with any Python application, from simple scripts to complex web servers.

---

## ✨ Why Pico-IoC?

`pico-ioc` exists to solve a common problem that arises as Python applications grow: managing how objects are created and connected becomes complex and brittle. This manual wiring, where a change deep in the application can cause a cascade of updates, makes the code hard to test and maintain. `pico-ioc` introduces the principle of Inversion of Control (IoC) in a simple, Pythonic way. Instead of you creating and connecting every object, you declare your components with a simple `@component` decorator, and the container automatically wires them together based on their type hints. It brings the architectural robustness and testability of mature frameworks like Spring to the Python ecosystem, but without the heavy boilerplate, allowing you to build complex, loosely-coupled applications that remain simple to manage.


| Feature             | Manual Wiring                                     | With Pico-IoC                   |
| :------------------ | :------------------------------------------------ | :------------------------------ |
| **Object Creation** | `service = Service(Repo(Config()))`               | `svc = container.get(Service)`  |
| **Testing**         | Manual replacement or monkey-patching             | `overrides={Repo: FakeRepo()}`  |
| **Coupling**        | High (code knows about constructors)              | Low (code just asks for a type) |
| **Maintenance**     | Brittle (changing a constructor breaks consumers) | Robust (changes are isolated)   |
| **Learning Curve**  | Ad-hoc, implicit patterns                         | Uniform, explicit, documented   |


---

## 🧩 Features

### Core

* **Zero dependencies** — pure Python, framework-agnostic.
* **Single Entry Point (`init`)** — Robustly bootstrap your entire application from a single root package, enforcing a clean "Composition Root" pattern.
* **Decorator API** — `@component`, `@factory_component`, `@provides`, `@plugin`.
* **Fail-fast bootstrap** — eager by default; missing deps surface at startup.
* **Opt-in lazy** — `lazy=True` wraps with `ComponentProxy`.
* **Smart resolution order** — parameter name → type annotation → MRO → string.
* **Overrides for testing** — inject mocks/fakes directly via `init(overrides={...})`.
* **Public API helper** — auto-export decorated symbols in `__init__.py`.
* **Thread/async safe** — isolation via `ContextVar`.

### Advanced

* **Qualifiers & collections** — `list[Annotated[T, Q]]` filters by qualifier.
* **Flexible Scopes (`scope`)** — Create lightweight, temporary containers from multiple modules, ideal for testing, scripting, or modular tasks.
* **Interceptors API** — observe/modify resolution, instantiation, invocation, errors.
* **Conditional providers** — activate components by env vars or predicates.
* **Plugins** — lifecycle hooks (`before_scan`, `after_ready`).

---

## 📦 Installation

```bash
# Requires Python 3.10+
pip install pico-ioc
````

---

## 🚀 Quick start

```python
from pico_ioc import component, init

@component
class Config:
    url = "sqlite:///demo.db"

@component
class Repo:
    def __init__(self, cfg: Config):
        self.url = cfg.url
    def fetch(self): return f"fetching from {self.url}"

@component
class Service:
    def __init__(self, repo: Repo):
        self.repo = repo
    def run(self): return self.repo.fetch()

# bootstrap
import myapp
c = init(myapp)
svc = c.get(Service)
print(svc.run())
```

**Output:**

```
fetching from sqlite:///demo.db
```
---

### Quick overrides for testing

```python
from pico_ioc import init
import myapp

fake = {"repo": "fake-data"}
c = init(myapp, overrides={
    "fast_model": fake,                  # constant instance
    "user_service": lambda: {"id": 1},   # provider
})
assert c.get("fast_model") == {"repo": "fake-data"}
```
---

### Scoped subgraphs

For unit tests or lightweight integration, you can bootstrap **only a subset of the graph**.

```python
from pico_ioc
from src.runner_service import RunnerService
from tests.fakes import FakeDocker
import src

c = pico_ioc.scope(
    modules=[src],
    roots=[RunnerService],  # only RunnerService and its deps
    overrides={
        "docker.DockerClient": FakeDocker(),
    },
    strict=True,   # fail if something is missing
    lazy=True,     # instantiate on demand
)
svc = c.get(RunnerService)
```

This way you don’t need to bootstrap your entire app (`controllers`, `http`, …) just to test one service.

---
## 📖 Documentation

  * **🚀 New to pico-ioc? Start with the User Guide.**
      * [**GUIDE.md**](.llm/GUIDE.md) — Learn with practical examples: testing, configuration, collection injection, and web framework integration.

  * **🏗️ Want to understand the internals? See the Architecture.**
      * [**ARCHITECTURE.md**](.llm/ARCHITECTURE.md) — A deep dive into the algorithms, lifecycle, and internal diagrams. Perfect for contributors.

  * **🤔 Want to know *why* it's designed this way? Read the Decisions.**
      * [**DECISIONS.md**](.llm/DECISIONS.md) — The history and rationale behind key technical decisions.

  * **💡 Just need a quick summary?**
      * [**OVERVIEW.md**](.llm/OVERVIEW.md) — What pico-ioc is and why you should use it.
---

## 🧪 Development

```bash
pip install tox
tox
```

---

## 📜 Changelog

See [CHANGELOG.md](./CHANGELOG.md) for version history.

---

## 📜 License

MIT — see [LICENSE](https://opensource.org/licenses/MIT)



