# Pico-IoC: A Minimalist IoC Container for Python

[](https://www.google.com/search?q=https://pypi.org/project/pico-ioc/)
[](https://www.google.com/search?q=https://travis-ci.com/dperezcabrera/pico-ioc)
[](https://opensource.org/licenses/MIT)

**Pico-IoC** is a tiny, zero-dependency, and decorator-based Inversion of Control (IoC) container for Python. It helps you manage dependencies in your application in a clean, intuitive, and "Pythonic" way.

The core idea is to let you build loosely coupled, easily testable applications without the boilerplate of manually wiring components together.

-----

## Key Features

  * ✨ **Zero Dependencies:** Pure Python, no external libraries required.
  * 🚀 **Decorator-Based API:** A simple and declarative API using decorators like `@component` and `@provides`.
  * 🔍 **Automatic Discovery:** Scans your project packages to find and register components automatically.
  * 🧩 **Lazy Instantiation:** Components are created only when they are first requested, improving startup time and resource efficiency.
  * 🏭 **Flexible Factories:** Use factory components to handle complex object creation logic.
  * 🤝 **Framework-Agnostic:** Works with any application or framework (Flask, FastAPI, scripts, etc.).

-----

## Installation

You can install Pico-IoC directly from PyPI:

```bash
pip install pico-ioc
```

-----

##  Quickstart

Getting started is simple. Structure your application, decorate your classes, and let Pico-IoC wire everything up.

#### 1\. Define Your Components

Create your services and components in different files. Use the `@component` decorator for classes that the container can instantiate directly.

`# project/services.py`

```python
# A simple service with a dependency on another component.
# Pico-IoC will automatically inject 'config' when creating 'DatabaseService'.
@component
class DatabaseService:
    def __init__(self, config: AppConfig):
        self._connection_string = config.get_db_url()
        print(f"DatabaseService initialized with: {self._connection_string}")

    def get_data(self):
        return f"Data from {self._connection_string}"

# A component that will be a dependency for another service.
@component
class AppConfig:
    def get_db_url(self):
        return "postgresql://user:pass@host/db"
```

#### 2\. Initialize the Container

In your main application file, call `pico_ioc.init()` with your root package. This will scan for all decorated components and configure the container.

`# project/main.py`

```python
import pico_ioc
from project.services import DatabaseService

# Initialize the container, scanning the 'project' package
container = pico_ioc.init("project")

# 3. Get Your Top-Level Component
# The container will create the 'DatabaseService' and its 'AppConfig' dependency.
db_service = container.get(DatabaseService)

# Use the service
print(db_service.get_data())
```

#### 4\. Run It

When you run `main.py`, Pico-IoC handles the creation and injection of all objects:

```
$ python -m project.main
INFO:root:🔌 Initializing 'pico-ioc'...
INFO:root:🚀 Scanning in 'project'...
INFO:root:✅ Container configured and ready.
DatabaseService initialized with: postgresql://user:pass@host/db
Data from postgresql://user:pass@host/db
```

-----

## \#\# API Reference

### `init(root_package_name: str) -> PicoContainer`

Initializes the IoC container. It must be called once with the name of the root package to scan. It returns the configured container instance.

### `@component(cls=None, *, name: str = None)`

A class decorator that marks a class as a component for auto-discovery. The container will manage its lifecycle.

  * **`name`**: (Optional) A string to register the component with a specific name instead of its class type.

### `@factory_component`

A class decorator that marks a class as a source of components. Use this when object creation is complex. Methods inside a factory class can be decorated with `@provides`.

### `@provides(name: str)`

A method decorator used inside a `@factory_component`. It indicates that the method produces a component.

  * **`name`**: The name (string) used to register the component in the container. This is mandatory.

-----

## Contributing

Contributions are welcome\! If you find a bug or have a feature request, please open an issue. If you'd like to contribute code, please open a pull request.

-----

## License

This project is licensed under the MIT License. See the [LICENSE](https://www.google.com/search?q=LICENSE) file for details.

-----

## Authors

  * **David Perez Cabrera**
  * **Gemini 2.5-Pro**
