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

## ✨ Features

- **Zero dependencies** — pure Python, framework-agnostic.
- **Decorator API** — `@component`, `@factory_component`, `@provides`, `@plugin`.
- **Fail-fast bootstrap** — eager by default; missing deps surface at startup.
- **Opt-in lazy** — `lazy=True` wraps with `ComponentProxy`.
- **Smart resolution order** — parameter name → type annotation → MRO → string.
- **Qualifiers & collections** — `list[Annotated[T, Q]]` filters by qualifier.
- **Plugins** — lifecycle hooks (`before_scan`, `after_ready`).
- **Public API helper** — auto-export decorated symbols in `__init__.py`.
- **Thread/async safe** — isolation via `ContextVar`.
- **Overrides for testing** — inject mocks/fakes directly via `init(overrides={...})`.
- **Scoped subgraph for tests** — `scope(modules=…, roots=…, overrides=…, strict=…, lazy=…, include_tags=…, exclude_tags=…)` to load only what you need.

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

* [Overview](.llm/OVERVIEW.md) — mission & concepts
* [Guide](.llm/GUIDE.md) — practical usage & recipes
* [Architecture](.llm/ARCHITECTURE.md) — internals & design rationale

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



