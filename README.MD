# Pico-IoC: A Minimalist IoC Container for Python

[![PyPI](https://img.shields.io/pypi/v/pico-ioc.svg)](https://pypi.org/project/pico-ioc/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
![CI (tox matrix)](https://github.com/dperezcabrera/pico-ioc/actions/workflows/ci.yml/badge.svg)

**Pico-IoC** is a tiny, zero-dependency, decorator-based Inversion of Control (IoC) container for Python.  
It helps you manage dependencies in a clean, intuitive, and *Pythonic* way.

The core idea is to let you build loosely coupled, easily testable applications without manually wiring components.  
*Inspired by the IoC philosophy popularized by the Spring Framework.*

---

## Key Features

* ✨ **Zero Dependencies:** Pure Python, no external libraries.
* 🚀 **Decorator-Based API:** Simple decorators like `@component` and `@provides`.
* 🔍 **Automatic Discovery:** Scans your package to auto-register components.
* 🧩 **Lazy Instantiation:** Objects are created on first use.
* 🏭 **Flexible Factories:** Encapsulate complex creation logic.
* 🤝 **Framework-Agnostic:** Works with Flask, FastAPI, CLIs, scripts, etc.

---

## Installation

```bash
pip install pico-ioc
```

---

## Quick Start

Getting started is simple. Decorate your classes and let Pico-IoC wire them up.

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

## More Examples

### 🧩 Custom Component Name

```python
from pico_ioc import component, init

@component(name="config")
class AppConfig:
    def __init__(self):
        self.db_url = "postgresql://user:pass@localhost/db"

@component
class Repository:
    def __init__(self, config: "config"):  # refer by custom name if you prefer
        self._url = config.db_url

container = init(__name__)
repo = container.get(Repository)
print(repo._url)           # postgresql://user:pass@localhost/db
print(container.get("config").db_url)
```

> Pico-IoC prefers **type annotations** to resolve deps; if missing, it falls back to the **parameter name**.

### 💤 Lazy Factories (only build when used)

```python
from pico_ioc import factory_component, provides, init

CREATION_COUNTER = {"value": 0}

@factory_component
class ServicesFactory:
    @provides(name="heavy_service")  # returns a LazyProxy by default
    def make_heavy(self):
        CREATION_COUNTER["value"] += 1
        return {"payload": "Hello from heavy service"}

container = init(__name__)
svc = container.get("heavy_service")
print(CREATION_COUNTER["value"])  # 0 (not created yet)

print(svc["payload"])             # triggers creation
print(CREATION_COUNTER["value"])  # 1
```

### 📦 Project-Style Package Scanning

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

# Scan the whole 'myapp' package
container = pico_ioc.init("myapp")

client = container.get(ApiClient)
print(client.get("status"))  # GET https://api.example.com/status
```

---

## API Reference (mini)

### `init(root_package_or_module) -> PicoContainer`

Initialize the container by scanning a root **package** (str) or **module**. Returns the configured container.

### `@component(cls=None, *, name: str | None = None)`

Mark a class as a component. Registered by **class type** by default, or by **name** if provided.

### `@factory_component`

Mark a class as a factory holder. Methods inside can be `@provides(...)`.

### `@provides(name: str, lazy: bool = True)`

Declare that a factory method **produces** a component registered under `name`. By default it’s **lazy** (a proxy that creates on first real use).

---

## Testing

`pico-ioc` ships with `pytest` tests and a `tox` matrix.

```bash
pip install tox
tox -e py311           # run on a specific version
tox                    # run all configured envs
```

---

## Contributing

Issues and PRs are welcome. If you spot a bug or have an idea, open an issue!

---

## License

MIT — see the [LICENSE](https://opensource.org/licenses/MIT).

---

## Authors

* **David Perez Cabrera**
* **Gemini 2.5-Pro**
* **GPT-5**
