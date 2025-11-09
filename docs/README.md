# Welcome to pico-ioc

`pico-ioc` is a powerful, async-native, and observability-first Inversion of Control (IoC) container for Python. It's designed to bring the power of enterprise-grade dependency injection, configuration binding, and AOP (Aspect-Oriented Programming) from frameworks like Spring into the modern Python ecosystem.

This documentation site guides you from your first component to building complex, observable, and testable applications.

## Key Features

* 🚀 Async-Native: Full support for `async`/`await` in component resolution (`aget`), lifecycle methods (`__ainit__`, `@cleanup`), AOP interceptors, and the Event Bus.
* 🌳 Advanced Unified Configuration: Use `@configured` to map complex YAML/JSON configuration trees or flat key-value sources (like ENV) directly to `dataclass` graphs via the `configuration(...)` builder, with clear precedence rules and normalization.
* 🔬 Observability-First: Built-in container contexts (`as_current`), stats (`.stats()`), and observer protocols (`ContainerObserver`) to monitor, trace, and debug your application's components.
* ✨ Powerful AOP: Intercept method calls for cross-cutting concerns (like logging, tracing, or caching) using `@intercepted_by` without modifying your business logic.
* ✅ Fail-Fast Validation: The container validates all component dependencies at startup (`init()`), preventing `ProviderNotFoundError` exceptions at runtime.
* 🧩 Rich Lifecycle: Full control over component lifecycles with `scope`, lazy instantiation, `@configure` setup methods, and `@cleanup` teardown hooks.

## Documentation Structure

| Section | Focus | Start Here |
| :--- | :--- | :--- |
| 1. Getting Started | Installation and 5-minute quick start. | [Quick Start](./getting-started.md) |
| 2. User Guide | Core concepts, configuration, scopes, and testing. | [User Guide Overview](./user-guide/README.md) |
| 3. Advanced Features | Async, AOP, Event Bus, and conditional logic. | [Advanced Features Overview](./advanced-features/README.md) |
| 4. Observability | Context, metrics, tracing, and graph export. | [Observability Overview](./observability/README.md) |
| 5. Integrations | FastAPI, Flask, Django, and AI/LangChain recipes. | [Integrations Overview](./integrations/README.md) |
| 6. Cookbook (Patterns) | Full architectural solutions (Multi-tenant, Hot-reload, CQRS). | [Cookbook Overview](./cookbook/README.md) |
| 7. Architecture | Design principles and internal deep-dive. | [Architecture Overview](./architecture/README.md) |
| 8. API Reference | Glossary and decorator/method cheatsheets. | [API Reference Overview](./api-reference/README.md) |

## Overview

pico-ioc is a Dependency Injection (DI) container for Python that implements advanced enterprise architecture patterns. Its design is inspired by frameworks like Spring (Java) and Guice, adapted for the Python ecosystem.

It provides a robust, type-safe, and testable foundation for complex applications by managing component lifecycles, configuration, and runtime dependencies.

---

## Core Strengths

The framework is built on specific principles:

* Fail-Fast at Startup: All wiring errors are detected during `init()`, preventing runtime surprises.
* Async-Native: Full integration of `async`/`await` across the resolution and lifecycle systems.
* AOP and Observability: Built-in tools for cross-cutting concerns and monitoring runtime behavior.

---

## Getting Started

### Installation

```bash
pip install pico-ioc
```

### A Simple Example

```python
from dataclasses import dataclass
from pico_ioc import component, init

# 1. Define your components
class Greeter:
    def say_hello(self) -> str: ...

@component
class EnglishGreeter(Greeter):
    def say_hello(self) -> str:
        return "Hello!"

@component
class App:
    # 2. Declare dependencies in the constructor
    def __init__(self, greeter: Greeter):
        self.greeter = greeter
    
    def run(self):
        print(self.greeter.say_hello())

# 3. Initialize the container (scans this module for @component)
container = init(modules=[__name__])

# 4. Get the root component and run
app = container.get(App)
app.run()

# Output: Hello!
```

### Async Quick Peek

```python
from pico_ioc import component, init

@component
class AsyncService:
    async def __ainit__(self):
        # async initialization logic (e.g., open connections)
        ...

    async def compute(self) -> int:
        return 42

container = init(modules=[__name__])

# Resolve asynchronously
service = await container.aget(AsyncService)
print(await service.compute())
```

### Configuration at a Glance

```python
import os
from dataclasses import dataclass
from pico_ioc import component, configured, configuration, init

# Example config dataclass bound from ENV and a YAML file
@configured(prefix="app")
@dataclass
class AppConfig:
    name: str
    debug: bool = False

@component
class ConfiguredApp:
    def __init__(self, config: AppConfig):
        self.config = config

# Compose configuration sources with precedence: ENV > file defaults
config = configuration(
    files=["./config/app.yaml"],  # YAML/JSON files
    env=os.environ,               # flat ENV vars (e.g., APP_NAME, APP_DEBUG)
)

container = init(modules=["my_project.components"], config=config)
app = container.get(ConfiguredApp)
print(app.config)
```

---

## Observability Essentials

* Use `with container.as_current():` to establish a container context for tracing.
* Access container metrics via `container.stats()`.
* Implement `ContainerObserver` to react to lifecycle events (component created/cleaned up, resolution timings).

---

## Next Steps

* Read the Quick Start to build your first app: [Getting Started](./getting-started.md)
* Explore AOP, async lifecycles, and the Event Bus: [Advanced Features](./advanced-features/README.md)
* Learn how to bind complex configurations: [User Guide](./user-guide/README.md)
* See observability in action: [Observability](./observability/README.md)
