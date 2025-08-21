# Usage Patterns for pico-ioc (LLM Guidance)

This document provides examples of typical questions and answers an LLM should handle when assisting developers with **pico-ioc**.
The goal is to give consistent, concise, and technically accurate responses.

---

## 1. General Questions

**Q:** What is pico-ioc?
**A:** pico-ioc is a lightweight Inversion of Control (IoC) and Dependency Injection (DI) container for Python.
It uses decorators (`@component`, `@factory_component`, `@provides`) to register dependencies and automatically resolve them at runtime.
It is inspired by frameworks like Spring (Java) but designed to be minimal, fast, and Pythonic.

---

## 2. How to Start

**Q:** How do I initialize pico-ioc in my project?
**A:**

```python
import pico_ioc
import myapp

container = pico_ioc.init(myapp)
service = container.get(MyService)
```

This scans the `myapp` package for components and wires them automatically.

---

## 3. Registering Components

**Q:** How do I register a class as a component?
**A:**

```python
from pico_ioc import component

@component
class MyService:
    def greet(self):
        return "Hello from MyService!"
```

---

## 4. Using Factories

**Q:** How do I create instances using a factory?
**A:**

```python
from pico_ioc import factory_component, provides

class MyService:
    def greet(self):
        return "Hello!"

@factory_component
class MyFactory:
    @provides("my_service")
    def build_service(self) -> MyService:
        return MyService()
```

Factories let you encapsulate creation logic. Each `@provides` method binds a key to the produced object.

---

## 5. Providing Interfaces

**Q:** How do I bind an interface to an implementation?
**A:**

```python
from pico_ioc import provides

class Storage:
    ...

class FileStorage(Storage):
    ...

@provides(Storage)
def provide_storage() -> Storage:
    return FileStorage()
```

Now any class that requires `Storage` will receive a `FileStorage`.

---

## 6. Resolving Dependencies

**Q:** How are constructor parameters injected?
**A:** pico-ioc inspects type hints in constructors and provides the required dependencies.

```python
@component
class UserService:
    def __init__(self, storage: Storage):
        self.storage = storage
```

When `UserService` is requested, pico-ioc automatically injects a `Storage`.

---

## 7. Thread Safety

**Q:** Is pico-ioc thread-safe?
**A:** Yes. Dependency resolution and scanning states are tracked using `ContextVar`, which isolates these flags per thread and per async task. This ensures safe operation in multithreaded and asynchronous environments without shared-state conflicts.

---

## 8. Lazy vs. Eager Components

By default, bindings are **eager** (instantiated immediately).
If `lazy=True` is passed, pico-ioc returns a `ComponentProxy` instead. The proxy defers creation until the first real use.

```python
from pico_ioc import component

@component(lazy=True)
class HeavyService:
    def __init__(self):
        print("Expensive init...")
        self.value = 42

container = pico_ioc.init(__name__)
svc = container.get(HeavyService)  # not yet created
print(svc.value)                   # triggers creation
```

**Note (since v0.6.0):** `ComponentProxy` fully forwards operators, attribute access, context manager protocols, etc., making lazy components behave transparently like the real object.

---

## 9. Best Practices

* Always use type hints so dependencies can be resolved correctly.
* Prefer `@component` for classes and `@provides` for interfaces.
* Use factories (`@factory_component` + `@provides`) for advanced creation logic.
* Avoid global state; let the container manage lifecycle.
* Use `init(package)` at the root of your application to wire everything automatically.
* Consider `lazy=True` for heavy or rarely used services.

---

## 10. Example Flow

```python
import pico_ioc
from pico_ioc import component

@component
class Repo:
    def fetch(self):
        return "data"

@component
class Service:
    def __init__(self, repo: Repo):
        self.repo = repo

    def run(self):
        return f"Service using {self.repo.fetch()}"

# Bootstrap
import myapp
container = pico_ioc.init(myapp)
svc = container.get(Service)
print(svc.run())
```

**Expected output:**

```
Service using data
```

---

## 11. Troubleshooting

* **Error:** "Cannot resolve parameter" → Add proper type hints.
* **Error:** "No provider found" → Ensure the class/function is decorated with `@component` or `@provides`.
* **Unexpected singleton reuse** → Check if you intended a new instance vs. a shared one.
* **Lazy service not instantiated** → Remember: `lazy=True` returns a proxy, actual creation happens only on first real usage.

---

✅ With these usage patterns, an LLM should be able to explain **how pico-ioc works**, provide **practical examples**, and help users debug typical problems.
**New in v0.6.0:** transparent `ComponentProxy` support for all Python protocols, making lazy components nearly indistinguishable from eager ones.

