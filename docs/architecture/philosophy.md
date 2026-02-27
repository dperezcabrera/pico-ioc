# Philosophy & Architectural Opinions

This document makes explicit the design philosophy behind pico-ioc: the beliefs, trade-offs, and strong opinions that shape the framework. While [Design Principles](./design-principles.md) explains the *technical* rationale behind each feature, this document answers the deeper question: **what kind of applications is pico-ioc trying to help you build, and how?**

---

## Why pico-ioc Exists

Python's ecosystem has excellent libraries for individual tasks, but lacks a cohesive answer to a fundamental architectural question: **how do you wire a large application together reliably?**

Most Python projects wire dependencies by hand. This works for small scripts but degrades as applications grow. Dependencies become implicit, configuration scatters across modules, and testing requires monkey-patching. Errors surface at runtime, often in production.

pico-ioc exists to solve this. It is an opinionated IoC container that brings discipline from enterprise ecosystems (Spring, Guice) to Python, adapted to Python's strengths: type hints, decorators, and `asyncio`. It targets developers building **medium-to-large applications** where reliability, testability, and maintainability matter more than minimalism.

---

## Core Beliefs

### 1. Errors should surface at startup, never at runtime

The most important property of a well-wired application is that it either starts correctly or fails immediately with a clear error. pico-ioc validates the entire dependency graph during `init()`. If a dependency is missing, a cycle exists, or a configuration value cannot be bound, the application refuses to start.

This is a deliberate trade-off: startup takes slightly longer, but every request served by the running application is guaranteed to have all dependencies available.

### 2. Wiring should be explicit, discoverable, and close to the code

pico-ioc uses decorators (`@component`, `@factory`, `@provides`, `@configured`) applied directly to the classes they affect. This keeps the wiring visible and co-located with the business logic, rather than hidden in external configuration files or a separate container module.

When you read a class decorated with `@component`, you know immediately that it participates in the IoC graph. When you read its `__init__` signature, you know its dependencies. No magic, no implicit scanning.

### 3. The container is infrastructure, not architecture

pico-ioc should be invisible in your business logic. Components receive their dependencies through constructor parameters with no reference to the container. Only the **composition root** (the entry point where `init()` is called) should know about the container.

This means your domain classes can be tested without any framework, using plain constructor calls:

```python
def test_service():
    svc = OrderService(repo=FakeRepo(), notifier=FakeNotifier())
    svc.create_order(...)
```

### 4. One container, one application

pico-ioc is designed around the assumption that an application has **a single container instance** that owns all components. This is not a technical limitation but an intentional design choice: a single container provides a single source of truth for the dependency graph, configuration, and lifecycle.

Multiple containers are supported for advanced use cases (multi-tenant, testing), but the default mental model is one container per process.

### 5. Async is not an afterthought

Modern Python applications are increasingly async. pico-ioc was designed from the start to support `asyncio` as a first-class citizen: `aget()`, `__ainit__`, async `@configure`, async `@cleanup`, async interceptors, and an async event bus. Async is not a bolt-on; it's part of the core resolution engine.

---

## Strong Opinions

These are deliberate design decisions where pico-ioc takes a stance. Each comes with trade-offs.

### Constructor injection only

pico-ioc supports **only constructor injection** (`__init__` parameters). There is no field injection, setter injection, or method injection for wiring dependencies.

**Why:** Constructor injection guarantees that an object is fully initialized when it's created. There is no window where a partially-constructed object exists with `None` dependencies. It also makes dependencies explicit in the constructor signature, which aids readability and enables static analysis.

**Trade-off:** Constructor parameter lists can grow long. This is intentional -- a long constructor is a signal that the class has too many responsibilities and should be split.

### Dataclasses for configuration

Configuration objects must be Python `dataclasses` decorated with `@configured`. This is required, not optional.

**Why:** Dataclasses provide a clean, declarative way to define typed configuration with defaults. They integrate naturally with type hints, enable IDE autocompletion, and are easily serializable. Using a single standard mechanism avoids the ambiguity of multiple configuration patterns.

**Trade-off:** You cannot use arbitrary classes, Pydantic models, or raw dictionaries as configuration targets. If you need Pydantic validation, apply it in a `@configure` method after binding.

### Singleton is the default scope

Components are singletons unless explicitly declared otherwise (`scope="prototype"`, `scope="request"`, etc.).

**Why:** Most application components (services, repositories, configuration) are stateless or thread-safe and should be shared. Creating a new instance on every request wastes resources and loses caching benefits. Making singleton the default matches this reality.

**Trade-off:** Developers must be aware that components are shared. Stateful components that need isolation must explicitly use `scope="prototype"` or a context-aware scope.

### Concrete class as default contract

When you register `@component class UserService`, the container binds it to the class `UserService` itself. There is no requirement to define a separate interface or protocol.

**Why:** Python is not Java. Requiring interfaces for every service adds ceremony without value in most cases. When you need polymorphism, use protocols or abstract base classes and bind with `@provides` or `primary=True`.

**Trade-off:** Without explicit interfaces, swapping implementations requires `overrides` or profiles rather than a simple rebinding.

### No implicit circular dependency resolution

pico-ioc detects circular dependencies and **refuses to resolve them automatically**. It will not inject proxies or lazy wrappers into constructors to break cycles.

**Why:** Circular dependencies are almost always a design smell. Automatically resolving them hides the problem and can lead to objects being used in partially-initialized states. pico-ioc forces you to break the cycle explicitly using `@configure` methods, provider injection (`Callable[[], T]`), or the event bus.

**Trade-off:** You must restructure your code or use explicit patterns to break cycles. This is extra work, but it results in a cleaner architecture.

---

## The Composition Root Pattern

pico-ioc follows the **composition root** pattern: there should be exactly one place in your application where the container is created and components are resolved. This is typically `main()` or the framework entry point.

```python
# main.py -- the composition root
from pico_ioc import init

def main():
    container = init(modules=["myapp"])
    app = container.get(App)
    app.run()
```

**Rules of thumb:**

- Call `init()` once, at the top of your application.
- Call `container.get()` only in the composition root or framework integration code (e.g., FastAPI middleware).
- Never pass the container to business logic components. If a component needs to create other components dynamically, inject a `Callable[[], T]` provider instead.
- Never import `container` as a module-level global in business logic.

Framework integrations like [pico-fastapi](https://github.com/dperezcabrera/pico-fastapi) and [pico-boot](https://github.com/dperezcabrera/pico-boot) handle the composition root for you, so you rarely need to call `init()` directly.

---

## When NOT to Use pico-ioc

pico-ioc is not the right tool for every Python project. Consider alternatives when:

| Scenario | Why pico-ioc is overkill | Alternative |
|----------|--------------------------|-------------|
| **Small scripts** (< 500 LOC) | The overhead of decorators and `init()` adds complexity without benefit | Manual wiring or no DI |
| **Jupyter notebooks** | Interactive exploration doesn't need lifecycle management | Direct instantiation |
| **Libraries / packages** | Libraries should not impose a DI framework on consumers | Dependency injection via constructor parameters (manual DI) |
| **Projects requiring Python < 3.11** | pico-ioc uses modern typing features unavailable before 3.11 | `dependency-injector` or `punq` |
| **Projects with zero dependencies policy** | pico-ioc itself is zero-dependency, but the pattern adds conceptual weight | Manual wiring |

**Use pico-ioc when:** you are building a long-lived application (web service, CLI tool, background worker) with multiple modules, configuration from environment/files, and a need for testability and clean architecture.

---

## The pico-framework Ecosystem

pico-ioc is the foundation of a family of packages that integrate IoC with popular Python frameworks:

| Package | Purpose | Integration |
|---------|---------|-------------|
| **[pico-ioc](https://github.com/dperezcabrera/pico-ioc)** | IoC container core | Standalone |
| **[pico-boot](https://github.com/dperezcabrera/pico-boot)** | Application orchestration & plugin discovery | Auto-configures `init()` |
| **[pico-fastapi](https://github.com/dperezcabrera/pico-fastapi)** | FastAPI integration | Request scope, controller injection |
| **[pico-sqlalchemy](https://github.com/dperezcabrera/pico-sqlalchemy)** | SQLAlchemy + transactions | Repository pattern, `@transactional` |
| **[pico-celery](https://github.com/dperezcabrera/pico-celery)** | Celery task integration | Task registration, DI in workers |
| **[pico-pydantic](https://github.com/dperezcabrera/pico-pydantic)** | Pydantic validation AOP | `@validate` interceptor |
| **[pico-agent](https://github.com/dperezcabrera/pico-agent)** | LLM agent framework | Agent/tool DI, conversation scope |

All ecosystem packages follow the same principles: decorator-driven registration, type-hint injection, and fail-fast validation.

---

## Summary

pico-ioc is opinionated by design. It prioritizes:

- **Safety** over flexibility (fail-fast validation)
- **Explicitness** over magic (decorators + type hints)
- **Simplicity** over power (constructor injection only)
- **Correctness** over convenience (no implicit cycle resolution)

These opinions exist to help you build applications that are easy to understand, test, and maintain over time. If you find yourself fighting the framework, step back and consider whether the framework is signaling a design improvement.

---

## Next Steps

- [Design Principles](./design-principles.md): Technical rationale for each feature
- [Comparison to Other Libraries](./comparison.md): How pico-ioc compares to alternatives
