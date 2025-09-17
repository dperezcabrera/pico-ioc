# 📦 pico-ioc — Overview

## 🎯 Mission

**pico-ioc’s mission is to simplify dependency management and accelerate development by shortening feedback loops.** It gives Python projects a tiny, predictable IoC container that removes boilerplate wiring, making apps easier to test, extend, and run.

> ⚠️ **Requires Python 3.10+** (relies on `typing.Annotated` and `include_extras=True`).

---

## 🔍 What is pico-ioc?

pico-ioc is a **minimal Inversion of Control (IoC) and Dependency Injection (DI) container for Python**.

  - **Zero dependencies** → pure Python, framework-agnostic.
  - **Decorator API** → `@component`, `@factory_component`, `@provides`, `@plugin`.
  - **Type-safe Configuration** → `@config_component` classes are auto-populated from environment variables and files (YAML, JSON, .env).
  - **Automatic wiring** → resolves by: param name → exact type → MRO base → string key.
  - **Fail-fast bootstrap** → eager by default; opt into `lazy=True` proxies.
  - **Scoped subgraphs** → load only what you need with `scope(...)`.
  - **Overrides** → replace providers directly in `init(overrides={...})`.
  - **Qualifiers & collections** → tag/group implementations; inject `list[Annotated[T, Q]]`.
  - **Infrastructure & Interceptors** → Extend the container with custom logic for logging, metrics, or AOP via `@infrastructure` components.
  - **Conditional providers** → enable components by env vars or predicates (profiles).
  - **Plugins** → lifecycle hooks (`before_scan`, `after_ready`).
  - **Thread/async safe** → isolation via `ContextVar`.
  - **Public API helper** → auto-export decorated symbols, cleaner `__init__.py`.

In short: **a Spring-like container for Python — tiny, predictable, and test-oriented.**

---

## ⚡ Example: Hello Service

```python
from pico_ioc import component, config_component, init

# This class is now populated from env vars or files (e.g., config.yml)
@config_component
class Config:
    url: str = "sqlite:///demo.db" # Default value

@component
class Repo:
    def __init__(self, config: Config):
        self.url = config.url
    def fetch(self): return f"fetching from {self.url}"

@component
class Service:
    def __init__(self, repo: Repo):
        self.repo = repo
    def run(self): return self.repo.fetch()

# bootstrap
import myapp
from pico_ioc.config import EnvSource

# The container will build the Config object from environment variables
c = init(myapp, config=(EnvSource(),))
svc = c.get(Service)
print(svc.run())
```

**Output:**

```
fetching from sqlite:///demo.db
```

-----

## 🚀 Why pico-ioc?

  * **Less glue code** — no manual wiring.
  * **Predictable lifecycle** — fail early, debug easily.
  * **Test-friendly** — overrides & scoped subgraphs make mocking trivial.
  * **Externalized Configuration** — Manage settings for different environments without code changes.
  * **Universal** — works with Flask, FastAPI, CLIs, or scripts.
  * **Extensible** — logging, metrics, tracing via infrastructure and interceptors.
  * **Profiles** — conditionals let you switch implementations by env/config.

-----

## 🧪 Testing patterns

Replace providers quickly in tests:

```python
from pico_ioc import init
import myapp

fake = {"repo": "fake-data"}
c = init(myapp, overrides={
    "fast_model": fake,             # constant
    "user_service": lambda: {"id": 1},  # provider
})
assert c.get("fast_model") == {"repo": "fake-data"}
```

Or use `scope()` to build only a subgraph:

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

-----

## 📦 Public API Helper

Instead of manual exports in `__init__.py`:

```python
# app/__init__.py
from pico_ioc.public_api import export_public_symbols_decorated
__getattr__, __dir__ = export_public_symbols_decorated("app", include_plugins=True)
```

This auto-exposes:

  * All `@component` and `@factory_component` classes
  * All `@plugin` classes (if `include_plugins=True`)
  * Any symbols in `__all__`

So you can import cleanly:

```python
from app import Service, Config, TracingPlugin
```

-----

## 📖 Documentation

  * **🚀 New to pico-ioc? Start with the User Guide.**

      * [**GUIDE.md**](GUIDE.md) — Learn with practical examples: testing, configuration, collection injection, and web framework integration.

  * **⚙️ Feature & Pattern Guides**

      * [**Guide: Configuration Injection**](GUIDE-CONFIGURATION-INJECTION.md) — A deep dive into the type-safe configuration system.
      * [**Guide: Creating Plugins and Interceptors**](GUIDE-CREATING-PLUGINS-AND-INTERCEPTORS.md) — Learn how to extend pico-ioc with custom logic.
      * [**Pattern: Implementing a CQRS Command Bus**](GUIDE-CQRS.md) — An example of building clean architectures with pico-ioc.

  * **🏗️ Want to understand the internals? See the Architecture.**

      * [**ARCHITECTURE.md**](ARCHITECTURE.md) — A deep dive into the algorithms, lifecycle, and internal diagrams. Perfect for contributors.

  * **🤔 Want to know *why* it's designed this way? Read the Decisions.**

  * [**DECISIONS.md**](DECISIONS.md) — The history and rationale behind key technical decisions.

  * [Readme](../README.md) — readme.md file.

  * [Changelog](../CHANGELOG.md) — release history.

