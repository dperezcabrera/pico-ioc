# 📦 pico-ioc — Overview

## Mission
**pico-ioc’s mission is to simplify dependency management and accelerate development by shortening feedback loops.**  
It gives Python projects a tiny, predictable IoC container that removes boilerplate wiring, making apps easier to test, extend, and run.

> ⚠️ **Requires Python 3.10+** (uses `typing.Annotated` and `include_extras=True`).

---

## What is pico-ioc?
pico-ioc is a **lightweight Inversion of Control (IoC) and Dependency Injection (DI) container for Python**.

- **Zero dependencies**: pure Python, framework-agnostic.
- **Automatic wiring**: discovers components via decorators.
- **Resolution order**: parameter name → exact type → base type (MRO) → string key.
- **Eager by default**: fail-fast at startup; opt into `lazy=True` for proxies.
- **Thread/async safe**: isolation via `ContextVar`.
- **Qualifiers & collection injection**: group implementations and inject lists (`list[Annotated[T, Q]]`).
- **Plugins**: lifecycle hooks (`before_scan`, `after_ready`) for cross-cutting concerns.
- **Public API helper**: auto-export decorated symbols, cleaner `__init__.py`.

In short: **a minimal Spring-like container for Python, without the overhead**.

---

## Example: Hello World Service

```python
from pico_ioc import component, init

@component
class Config:
    url = "sqlite:///demo.db"

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
container = init(myapp)
svc = container.get(Service)
print(svc.run())
````

**Output:**

```
fetching from sqlite:///demo.db
```

---

## Why pico-ioc?

* **Less glue code** → no manual wiring.
* **Predictable lifecycle** → fail early, easy to debug.
* **Test-friendly** → swap out components via `@provides`.
* **Universal** → works with Flask, FastAPI, CLIs, or plain scripts.
* **Extensible** → add tracing, logging, or metrics via plugins.
* **Overrides for testing** → inject mocks/fakes directly via `init(overrides={...})`.

---

📌 With a few decorators and `init()`, you get a **clean DI container** that works across scripts, APIs, and services — from small apps to complex projects.


---

## Public API Helper

Instead of manually re-exporting components in your `__init__.py`,  
you can use the helper `export_public_symbols_decorated`:

```python
# app/__init__.py
from pico_ioc.public_api import export_public_symbols_decorated
__getattr__, __dir__ = export_public_symbols_decorated("app", include_plugins=True)
````

This automatically exposes:

* All `@component` and `@factory_component` classes
* All `@plugin` classes (if `include_plugins=True`)
* Any symbols listed in `__all__`

So you can import directly:

```python
from app import Service, Config, TracingPlugin
```

This keeps `__init__.py` **clean, declarative, and convention-driven**.

---

## Testing with overrides

You can replace providers on the fly during tests:

```python
from pico_ioc import init
import myapp

fake = {"repo": "fake-data"}
c = init(myapp, overrides={
    "fast_model": fake,                     # constant instance
    "user_service": lambda: {"id": 1},      # provider
})

svc = c.get("fast_model")
assert svc == {"repo": "fake-data"}

```
---

## Scoped subgraphs for testing & tools

Besides global `init(...)`, you can build a **bounded container** with only the
dependencies of certain roots. This is ideal for unit tests, CLI tools, or
integration-lite scenarios.

```python
from pico_ioc import scope
from src.runner_service import RunnerService
from tests.fakes import FakeDocker, TestRegistry
import src

c = scope(
    modules=[src],
    roots=[RunnerService],
    overrides={
        "docker.DockerClient": FakeDocker(),
        TestRegistry: TestRegistry(),
    },
    strict=True,
    lazy=True,
)
svc = c.get(RunnerService)
```

This avoids bootstrapping the entire app (controllers, HTTP, etc.) just to test
a single service.

---

👉 Next steps:

* [Guide](./GUIDE.md) — practical recipes & usage patterns
* [Architecture](./ARCHITECTURE.md) — internals, algorithms & design trade-offs

