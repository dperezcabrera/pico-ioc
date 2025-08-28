# 📦 Pico-IoC: A Minimalist IoC Container for Python

[![PyPI](https://img.shields.io/pypi/v/pico-ioc.svg)](https://pypi.org/project/pico-ioc/)
[![DeepWiki](https://img.shields.io/badge/docs-DeepWiki-blue)](https://deepwiki.com/dperezcabrera/pico-ioc)
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
* **Decorator API** — `@component`, `@factory_component`, `@provides`, `@plugin`.
* **Qualifiers** — tag components with `@qualifier(Q)` and inject lists like `list[Annotated[T, Q]]`.
* **Auto discovery** — scans a package and registers components.
* **Public API helper** — `export_public_symbols_decorated(...)` removes boilerplate from `__init__.py`.
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

---

## 🧩 Qualifiers and Collection Injection

You can tag components with a `Qualifier` and inject all implementations of a type or a filtered subset.

```python
from typing import Protocol, Annotated
from pico_ioc import component, Qualifier, qualifier

class Handler(Protocol):
    def handle(self, s: str) -> str: ...

PAYMENTS = Qualifier("payments")

@component
@qualifier(PAYMENTS)
class StripeHandler(Handler): ...

@component
@qualifier(PAYMENTS)
class PaypalHandler(Handler): ...

@component
class Orchestrator:
    def __init__(self, handlers: list[Annotated[Handler, PAYMENTS]]):
        self.handlers = handlers

    def run(self, s: str) -> list[str]:
        return [h.handle(s) for h in self.handlers]

container = init(__name__)
orch = container.get(Orchestrator)
print([h.handle("ok") for h in orch.handlers])  # ['stripe:ok', 'paypal:ok']
```

If you omit the qualifier (`list[Handler]`), *all* implementations are injected.
If you specify a qualifier (`list[Annotated[Handler, PAYMENTS]]`), only matching ones are injected.

---

## 🔌 Plugins

Plugins allow you to hook into the container lifecycle.
Use the `@plugin` decorator and implement the `PicoPlugin` protocol.

```python
from pico_ioc import plugin
from pico_ioc.plugins import PicoPlugin

@plugin
class TracingPlugin(PicoPlugin):
    def before_scan(self, package, binder):
        print(f"Scanning {package}")

    def after_ready(self, container, binder):
        print("Container is ready")
```

Plugins are passed explicitly to `init()`:

```python
from pico_ioc import init
container = init(__name__, plugins=(TracingPlugin(),))
```

---

## 📤 Public API Helper

Instead of polluting your `__init__.py` with manual re-exports,
you can use the helper `export_public_symbols_decorated` to automatically expose
all decorated classes (`@component`, `@factory_component`, `@plugin`) and any `__all__` symbols.

**Example for an extension library:**

```python
# myext/__init__.py
from pico_ioc.public_api import export_public_symbols_decorated
__getattr__, __dir__ = export_public_symbols_decorated("myext", include_plugins=True)
```

Now you can import directly:

```python
from myext import SomeComponent, SomeFactory, SomePlugin
```

**Example for an app project:**

```python
# app/__init__.py
from pico_ioc.public_api import export_public_symbols_decorated
__getattr__, __dir__ = export_public_symbols_decorated("app", "app.subpkg", include_plugins=True)
```

This automatically picks up all components and plugins under `app/` and `app/subpkg/`.

---

## 🛠 API Reference

### `init(root, *, exclude=None, auto_exclude_caller=True, plugins=()) -> PicoContainer`

Scan and bind components in `root`.
Optional `plugins` are invoked on lifecycle hooks.

### `@component(cls=None, *, name=None, lazy=False)`

Register a class as a component.

### `@factory_component`

Mark a class as a component factory.

### `@provides(key, *, lazy=False)`

Mark a factory method as a provider.

### `@plugin`

Mark a class as a PicoPlugin.

### `Qualifier` and `@qualifier(...)`

Tag components with named qualifiers to enable filtered collection injection.

### `export_public_symbols_decorated(*packages, include_also=None, include_plugins=True)`

Helper to build `__getattr__`/`__dir__` for your `__init__.py`.
Exports all decorated classes automatically.

---

## 🧪 Testing

```bash
pip install tox
tox
```

---

## 📜 License

MIT — see [LICENSE](https://opensource.org/licenses/MIT)

```



