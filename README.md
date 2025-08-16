# 📦 Pico-IoC: A Minimalist IoC Container for Python

[![PyPI](https://img.shields.io/pypi/v/pico-ioc.svg)](https://pypi.org/project/pico-ioc/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
![CI (tox matrix)](https://github.com/dperezcabrera/pico-ioc/actions/workflows/ci.yml/badge.svg)
[![codecov](https://codecov.io/gh/dperezcabrera/pico-ioc/branch/main/graph/badge.svg)](https://codecov.io/gh/dperezcabrera/pico-ioc)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=dperezcabrera_pico-ioc&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=dperezcabrera_pico-ioc)
[![Duplicated Lines (%)](https://sonarcloud.io/api/project_badges/measure?project=dperezcabrera_pico-ioc&metric=duplicated_lines_density)](https://sonarcloud.io/summary/new_code?id=dperezcabrera_pico-ioc)
[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=dperezcabrera_pico-ioc&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=dperezcabrera_pico-ioc)

**Pico-IoC** is a tiny, zero-dependency, decorator-based Inversion of Control container for Python.  
Build loosely-coupled, testable apps without manual wiring. Inspired by the Spring ecosystem.

---

## ✨ Key Features

* **Zero dependencies** — pure Python.
* **Decorator API** — `@component`, `@factory_component`, `@provides`.
* **Auto discovery** — scans a package and registers components.
* **Eager by default, fail-fast** — non-lazy bindings are instantiated immediately after `init()`. Missing deps fail startup.
* **Opt-in lazy** — set `lazy=True` to defer creation (wrapped in `ComponentProxy`).
* **Factories** — encapsulate complex creation logic.
* **Smart resolution order** — **parameter name** takes precedence over **type annotation**, then **MRO fallback**, then **string(name)**.
* **Re-entrancy guard** — prevents `get()` during scanning.
* **Auto-exclude caller** — `init()` skips the calling module to avoid double scanning.

---

## 📦 Installation

```bash
pip install pico-ioc
````

---

## 🚀 Quick Start

```python
from pico_ioc import component, init

@component
class AppConfig:
    def get_db_url(self):
        return "postgresql://user:pass@host/db"

@component
class DatabaseService:
    def __init__(self, config: AppConfig):
        self._cs = config.get_db_url()
    def get_data(self):
        return f"Data from {self._cs}"

container = init(__name__)  # blueprint runs here (eager + fail-fast)
db = container.get(DatabaseService)
print(db.get_data())
```

---

## 🧩 Custom Component Keys

```python
from pico_ioc import component, init

@component(name="config")  # custom key
class AppConfig:
    db_url = "postgresql://user:pass@localhost/db"

@component
class Repository:
    def __init__(self, config: "config"):  # resolve by NAME
        self.url = config.db_url

container = init(__name__)
print(container.get("config").db_url)
```

---

## 🏭 Factories and `@provides`

* Default is **eager** (`lazy=False`). Eager bindings are constructed at the end of `init()`.
* Use `lazy=True` for on-first-use creation via `ComponentProxy`.

```python
from pico_ioc import factory_component, provides, init

COUNTER = {"value": 0}

@factory_component
class ServicesFactory:
    @provides(key="heavy_service", lazy=True)
    def heavy(self):
        COUNTER["value"] += 1
        return {"payload": "hello"}

container = init(__name__)
svc = container.get("heavy_service")  # not created yet
print(COUNTER["value"])               # 0
print(svc["payload"])                 # triggers creation
print(COUNTER["value"])               # 1
```

---

## 🧠 Dependency Resolution Order (Updated in v0.5.0)

Starting with **v0.5.0**, Pico-IoC enforces **name-first resolution**:

1. **Parameter name** (highest priority)
2. **Exact type annotation**
3. **MRO fallback** (walk base classes)
4. **String(name)**

This means that if a dependency could match both by name and type, **the name match wins**.

Example:

```python
from pico_ioc import component, factory_component, provides, init

class BaseType: ...
class Impl(BaseType): ...

@component(name="inject_by_name")
class InjectByName:
    def __init__(self):
        self.value = "by-name"

@factory_component
class NameVsTypeFactory:
    @provides("choose", lazy=True)
    def make(self, inject_by_name, hint: BaseType = None):
        return inject_by_name.value

container = init(__name__)
assert container.get("choose") == "by-name"
```

---

## ⚡ Eager vs. Lazy (Blueprint Behavior)

At the end of `init()`, Pico-IoC performs a **blueprint**:

* **Eager** (`lazy=False`, default): instantiated immediately; failures stop startup.
* **Lazy** (`lazy=True`): returns a `ComponentProxy`; instantiated on first real use.

**Lifecycle:**

```
       ┌───────────────────────┐
       │        init()         │
       └───────────────────────┘
                  │
                  ▼
       ┌───────────────────────┐
       │   Scan & bind deps    │
       └───────────────────────┘
                  │
                  ▼
       ┌─────────────────────────────┐
       │  Blueprint instantiates all │
       │    non-lazy (eager) beans   │
       └─────────────────────────────┘
                  │
       ┌───────────────────────┐
       │   Container ready     │
       └───────────────────────┘
```

---

## 🛠 API Reference

### `init(root, *, exclude=None, auto_exclude_caller=True) -> PicoContainer`

Scan and bind components in `root` (str module name or module).
Skips the calling module if `auto_exclude_caller=True`.
Runs blueprint (instantiate all `lazy=False` bindings).

### `@component(cls=None, *, name=None, lazy=False)`

Register a class as a component.
Use `name` for a custom key.
Set `lazy=True` to defer creation.

### `@factory_component`

Mark a class as a component factory (its methods can `@provides` bindings).

### `@provides(key, *, lazy=False)`

Declare that a factory method provides a component under `key`.
Set `lazy=True` for deferred creation (`ComponentProxy`).

---

## 🧪 Testing

```bash
pip install tox
tox
```

**New in v0.5.0:**
Additional tests verify:

* Name vs. type precedence.
* Mixed binding key resolution in factories.
* Eager vs. lazy instantiation edge cases.

---

## 🔌 Extensibility: Plugins, Binder, and Lifecycle Hooks

From `v0.4.0` onward, Pico-IoC can be cleanly extended without patching the core.

*(plugin API docs unchanged from before)*

---

## 📜 License

MIT — see [LICENSE](https://opensource.org/licenses/MIT)

```


