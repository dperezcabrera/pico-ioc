
# 📦 Pico-IoC: A Minimalist IoC Container for Python

[![PyPI](https://img.shields.io/pypi/v/pico-ioc.svg)](https://pypi.org/project/pico-ioc/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
![CI (tox matrix)](https://github.com/dperezcabrera/pico-ioc/actions/workflows/ci.yml/badge.svg)

**Pico-IoC** is a tiny, zero-dependency, decorator-based Inversion of Control (IoC) container for Python.
It helps you manage dependencies in a clean, intuitive, and *Pythonic* way.

The core idea is to let you build loosely coupled, easily testable applications without manually wiring components.
*Inspired by the IoC philosophy popularized by the Spring Framework.*

---

## ✨ Key Features

* **Zero Dependencies:** Pure Python, no external libraries.
* **Decorator-Based API:** Simple decorators like `@component` and `@provides`.
* **Automatic Discovery:** Scans your package to auto-register components.
* **Lazy Instantiation:** Objects are created on first use.
* **Flexible Factories:** Encapsulate complex creation logic.
* **Framework-Agnostic:** Works with Flask, FastAPI, CLIs, scripts, etc.
* **Smart Dependency Resolution:** Resolves by **parameter name**, then **type annotation**, then **MRO fallback**.
* **Auto-Exclude Caller:** `init()` automatically skips the calling module to avoid double-initialization during scans.

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

# Initialize the container scanning the current module
container = init(__name__)

db = container.get(DatabaseService)
print(db.get_data())  # Data from postgresql://user:pass@host/db
```

---

## 🧩 Custom Component Keys

You can register a component with a **custom key** (string, class, enum…).
`key=` is the preferred syntax. For backwards compatibility, `name=` still works.

```python
from pico_ioc import component, init

@component(name="config")  # still supported for legacy code
class AppConfig:
    def __init__(self):
        self.db_url = "postgresql://user:pass@localhost/db"

@component
class Repository:
    def __init__(self, config: "config"):  # resolve by name
        self._url = config.db_url

container = init(__name__)
repo = container.get(Repository)
print(repo._url)           # postgresql://user:pass@localhost/db
print(container.get("config").db_url)
```

---

## 🏭 Factory Components and `@provides`

Factories can provide components under a specific **key**.
Default is lazy creation (via `LazyProxy`).

```python
from pico_ioc import factory_component, provides, init

CREATION_COUNTER = {"value": 0}

@factory_component
class ServicesFactory:
    @provides(key="heavy_service")  # preferred
    def make_heavy(self):
        CREATION_COUNTER["value"] += 1
        return {"payload": "Hello from heavy service"}

container = init(__name__)
svc = container.get("heavy_service")
print(CREATION_COUNTER["value"])  # 0 (not created yet)

print(svc["payload"])             # triggers creation
print(CREATION_COUNTER["value"])  # 1
```

---

## 📦 Project-Style Scanning

```
project_root/
└── myapp/
    ├── __init__.py
    ├── services.py
    └── main.py
```

**myapp/services.py**

```python
from pico_ioc import component

@component
class Config:
    def __init__(self):
        self.base_url = "https://api.example.com"

@component
class ApiClient:
    def __init__(self, config: Config):
        self.base_url = config.base_url

    def get(self, path: str):
        return f"GET {self.base_url}/{path}"
```

**myapp/main.py**

```python
import pico_ioc
from myapp.services import ApiClient

container = pico_ioc.init("myapp")
client = container.get(ApiClient)
print(client.get("status"))  # GET https://api.example.com/status
```

---

## 🧠 Dependency Resolution Order

When Pico-IoC instantiates a component, it tries to resolve each parameter in this order:

1. **Exact parameter name** (string key in container)
2. **Exact type annotation** (class key in container)
3. **MRO fallback** (walk base classes until match)
4. **String version** of the parameter name

---

## 🛠 API Reference

### `init(root_package_or_module, *, exclude=None, auto_exclude_caller=True) -> PicoContainer`

Scan the given root **package** (str) or **module**.
By default, excludes the calling module.

### `@component(cls=None, *, name=None)`

Register a class as a component.
If `name` is given, registers under that string; otherwise under the class type.

### `@factory_component`

Register a class as a factory of components.

### `@provides(key=None, *, name=None, lazy=True)`

Declare that a factory method provides a component under `key`.
`name` is accepted for backwards compatibility.
If `lazy=True`, returns a `LazyProxy` that instantiates on first real use.

---

## 🧪 Testing

```bash
pip install tox
tox -e py311
```

---

## 📜 License

MIT — see [LICENSE](https://opensource.org/licenses/MIT)
