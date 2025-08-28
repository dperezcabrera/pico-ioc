# 📦 pico-ioc — Overview

## Mission
**pico-ioc’s mission is to simplify dependency management and accelerate development by shortening feedback loops.**  
It gives Python projects a tiny, predictable IoC container that removes boilerplate wiring, making apps easier to test, extend, and run.

---

## What is pico-ioc?
pico-ioc is a **lightweight Inversion of Control (IoC) and Dependency Injection (DI) container for Python**.

- **Zero dependencies**: pure Python, framework-agnostic.
- **Automatic wiring**: discovers components via decorators.
- **Resolution order**: name → type → base type (MRO) → string.
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

---

📌 With a few decorators and `init()`, you get a **clean DI container** that works across scripts, APIs, and services — from small apps to complex projects.

👉 Next steps:

* [Guide](./GUIDE.md) — practical recipes & usage patterns
* [Architecture](./ARCHITECTURE.md) — internals, algorithms & design trade-offs


