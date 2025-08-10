# 📦 Pico-IoC: A Minimalist IoC Container for Python

[![PyPI](https://img.shields.io/pypi/v/pico-ioc.svg)](https://pypi.org/project/pico-ioc/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
![CI (tox matrix)](https://github.com/dperezcabrera/pico-ioc/actions/workflows/ci.yml/badge.svg)

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
* **Smart resolution** — by **parameter name**, then **type annotation**, then **MRO fallback**, then **string(name)**.
* **Re-entrancy guard** — prevents `get()` during scanning.
* **Auto-exclude caller** — `init()` skips the calling module to avoid double scanning.

---

## 📦 Installation

```bash
pip install pico-ioc
```

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

## 🧠 Dependency Resolution Order

1. parameter **name**
2. exact **type annotation**
3. **MRO fallback** (walk base classes)
4. `str(name)`

---

## ⚡ Eager vs. Lazy (Blueprint Behavior)

At the end of `init()`, Pico-IoC performs a **blueprint**:

- **Eager** (`lazy=False`, default): instantiated immediately; failures stop startup.
- **Lazy** (`lazy=True`): returns a `ComponentProxy`; instantiated on first real use.

**Lifecycle:**

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


**Best practice:** keep eager+fail-fast for production parity with Spring; use lazy only for heavy/optional deps or to support negative tests.

---

## 🔄 Migration Guide (v0.2.1 → v0.3.0)

* **Defaults changed:** `@component` and `@provides` now default to `lazy=False` (eager).
* **Proxy renamed:** `LazyProxy` → `ComponentProxy` (only relevant if referenced directly).
* **Tests/fixtures:** components intentionally missing deps should be marked `@component(lazy=True)` (to avoid failing `init()`), or excluded from the scan.

Example fix for an intentional failure case:

```python
@component(lazy=True)
class MissingDep:
    def __init__(self, missing):
        self.missing = missing
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
tox -e py311
```

Tip: for “missing dependency” tests, mark those components as `lazy=True` so `init()` remains fail-fast for real components while your test still asserts failure on resolution.

---

## 🔌 Extensibility: Plugins, Binder, and Lifecycle Hooks

From `v0.4.0` onward, Pico-IoC can be cleanly extended without patching the core.
This enables optional integration layers like `pico-ioc-rest` for Flask, FastAPI, etc., while keeping the core dependency-free.

### Plugin Protocol

A plugin is any object that implements some or all of the following methods:

```python
from pico_ioc import PicoPlugin, Binder

class MyPlugin:
    def before_scan(self, package, binder: Binder): ...
    def visit_class(self, module, cls, binder: Binder): ...
    def after_scan(self, package, binder: Binder): ...
    def after_bind(self, container, binder: Binder): ...
    def before_eager(self, container, binder: Binder): ...
    def after_ready(self, container, binder: Binder): ...
```

All hooks are optional. If present, they are called in this order during `init()`:

1. **before\_scan** — called before package scanning starts.
2. **visit\_class** — called for every class discovered during scanning.
3. **after\_scan** — called after scanning all modules.
4. **after\_bind** — called after the core has bound all components/factories.
5. **before\_eager** — called right before eager (non-lazy) instantiation.
6. **after\_ready** — called after all eager instantiation is complete.

### Binder API

Plugins receive a [`Binder`](#binder-api) instance in each hook, allowing them to:

* **bind**: register new providers in the container.
* **has**: check if a binding exists.
* **get**: resolve a binding immediately.

Example plugin that binds a “marker” component when a certain class is discovered:

```python
class MarkerPlugin:
    def visit_class(self, module, cls, binder):
        if cls.__name__ == "SpecialService" and not binder.has("marker"):
            binder.bind("marker", lambda: {"ok": True}, lazy=False)

container = init("my_app", plugins=(MarkerPlugin(),))
assert container.get("marker") == {"ok": True}
```

### Creating Extensions

With the plugin API, you can build separate packages like `pico-ioc-rest`:

```python
from pico_ioc import PicoPlugin, Binder, create_instance, resolve_param
from flask import Flask

class FlaskRestPlugin:
    def __init__(self):
        self.controllers = []

    def visit_class(self, module, cls, binder: Binder):
        if getattr(cls, "_is_controller", False):
            self.controllers.append(cls)

    def after_bind(self, container, binder: Binder):
        app: Flask = container.get(Flask)
        for ctl_cls in self.controllers:
            ctl = create_instance(ctl_cls, container)
            # register routes here using `resolve_param` for handler DI
```

### Public Helpers for Extensions

Plugins can reuse Pico-IoC’s DI logic without duplicating it:

* **`create_instance(cls, container)`** — instantiate a class with DI, respecting Pico-IoC’s resolution order.
* **`resolve_param(container, parameter)`** — resolve a single function/class parameter via Pico-IoC rules.

---

## ❓ FAQ

**Q: Can I make the container lenient at startup?**
A: By design it’s strict. Prefer `lazy=True` on specific bindings or exclude problem modules from the scan.

**Q: Thread safety?**
A: Container uses `ContextVar` to guard re-entrancy during scanning. Singletons are created once per container; typical usage is in single-threaded app startup, then read-mostly.

**Q: Frameworks?**
A: Framework-agnostic. Works with Flask, FastAPI, CLIs, scripts, etc.

---

## 📜 License

MIT — see [LICENSE](https://opensource.org/licenses/MIT)


