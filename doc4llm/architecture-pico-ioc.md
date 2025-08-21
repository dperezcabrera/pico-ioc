# Pico-IoC Architecture & LLM Guide

## What is Pico-IoC?

Pico-IoC is a tiny, zero-dependency Inversion of Control (IoC) container for Python.  
It discovers components via decorators, wires dependencies automatically, and instantiates everything eagerly by default (fail-fast).  
You can opt into lazy creation via a lightweight proxy.

Target Python: 3.8+  
Core design goals: minimal API, predictable resolution, easy testing, framework-agnostic.

---

## Core Concepts (Glossary)

* **Container (`PicoContainer`)**
  Holds bindings (providers) and singletons. Keys may be classes or strings.

* **Binder (`Binder`)**
  A thin façade for plugins to `bind/has/get` during scan & lifecycle hooks.

* **Decorators**
  * `@component(cls=None, *, name=None, lazy=False)` → register a class.  
    - Key: class type by default, or `name` (string) if provided.  
    - `lazy=True` returns a `ComponentProxy` until first real use.
  * `@factory_component` → register a factory class whose methods can provide components.
  * `@provides(key, *, lazy=False)` → mark a factory method as a provider for `key` (string or type).

* **Factory DI**
  * Constructor of a `@factory_component` receives DI like regular components.
  * Each `@provides` method can also have DI in its parameters (by name/type).
  * Defaulted params are **optional**: if not bound, the method uses its default.

* **Resolution Order**
  1. **parameter name**, 2) type annotation, 3) MRO fallback, 4) `str(name)`.

* **ComponentProxy**
  A transparent proxy for lazy components that defers creation until first actual interaction.  
  Forwards common dunder methods (e.g., `__len__`, `__getitem__`, `__iter__`, `__bool__`, operators, context managers, etc.).

* **Re-entrancy Guard**
  Accessing `container.get(...)` during package scanning raises a clear error (prevents re-entrant use).

---

## Lifecycle

1. **init(root, …)**
   * Scans `root` package (string/module).
   * Auto-excludes the calling module by default (`auto_exclude_caller=True`).
   * Calls plugin hooks (`before_scan`, `visit_class`, `after_scan`, `after_bind`, `before_eager`, `after_ready`).
   * **Binding order**: components first, then factories.
   * **Blueprint**: eagerly instantiate all non-lazy bindings. Errors fail startup.

2. **get(key)**
   Returns the singleton instance for `key` (creates if needed).  
   For lazy bindings, returns a proxy first.

---

## How Pico-IoC Resolves Dependencies

Given a constructor or provider method parameter `p`:

* If a binding exists for the **parameter name**, use it.
* Else if the **type annotation** is bound, use it.
* Else try **MRO** (walk base classes) and use the first bound base type.
* Else if `str(name)` is bound, use that.
* Else: raise `NameError("No provider found for key: …")`.

**Optional defaulted params**: If resolution fails and the param has a default (e.g., `hint: T = None`), the resolver **omits the argument** so Python uses the default.

---

## Quick Recipes

### 1) Basic components
```python
from pico_ioc import component, init

@component
class Config:
    url = "postgresql://…"

@component
class Repo:
    def __init__(self, config: Config):  # type-based DI
        self.url = config.url

c = init(__name__)
repo = c.get(Repo)
````

### 2) Inject by name

```python
from pico_ioc import component

@component(name="fast_model")
class Model:
    pass

@component
class NeedsByName:
    def __init__(self, fast_model):  # name-based DI (highest priority)
        self.m = fast_model
```

### 3) Factory with lazy provider and provider-param DI

```python
from pico_ioc import factory_component, provides, component

@component
class Counter:
    def __init__(self): self.value = 0

@factory_component
class Factory:
    @provides("dataset", lazy=True)
    def make_dataset(self, counter: Counter):  # DI into provider method
        return list(range(counter.value, counter.value + 3))
```

### 4) Static/class methods as providers

```python
@factory_component
class F:
    @staticmethod
    @provides("static_result", lazy=True)
    def make_static():
        return "ok"

    @classmethod
    @provides("class_result")
    def make_class(cls):
        return "ok"
```

---

## Error Messages & What They Mean

* **`NameError: No provider found for key: ...`**
  A dependency couldn’t be resolved. Check the key being looked up:

  * For name-based DI: ensure a binding with that exact name exists (`@component(name=...)` or `@provides("name")`).
  * For type-based DI: ensure that class (or a base in its MRO) is provided.

* **`RuntimeError: pico-ioc: re-entrant container access during scan.`**
  Something called `get()` while scanning modules (e.g., at import time).
  Move that call out of module top-level or mark the dependent thing `lazy=True` and defer access.

---

## Plugins & Extensions

* Implement any subset of:

  * `before_scan(package, binder)`
  * `visit_class(module, cls, binder)`
  * `after_scan(package, binder)`
  * `after_bind(container, binder)`
  * `before_eager(container, binder)`
  * `after_ready(container, binder)`

* The `Binder` lets you register extra bindings, e.g.:

```python
class MarkerPlugin:
    def visit_class(self, module, cls, binder):
        if cls.__name__ == "SpecialService" and not binder.has("marker"):
            binder.bind("marker", lambda: {"ok": True}, lazy=False)
```

* Public helpers (also useful for plugins):

  * `create_instance(cls, container)` – construct with DI & precedence rules.
  * `resolve_param(container, inspect.Parameter)` – resolve a single param.

---

## Internals (Stable Behaviors)

* **Singletons**: All components/providers default to singletons (first creation cached).
* **Binding Order**: Components are bound **before** factories so factory constructors can be injected.
* **Eager by default**: `lazy=False` (default) is instantiated at the end of `init()`.
* **Lazy**: `lazy=True` yields a `ComponentProxy`; realization occurs on first real interaction.
* **Provider DI**: Provider methods can declare DI params; defaults make them optional.
* **Thread safety**: Scanning and resolution use `ContextVar`, isolating state per thread/async task.

---

## Troubleshooting Playbook (for an LLM)

When a user asks for help:

1. **Identify binding key**

   * If they mention a quoted name, assume **string key**.
   * If they mention a class, assume **type key**.

2. **Check resolution path**

   * Name → Type → MRO → `str(name)`.

3. **Suggest fixes**

   * For missing name: `@component(name="…")` or a `@provides("…")`.
   * For type: ensure class is scanned or provided by a factory.
   * For optional hint (`param: T = None`): remind that defaults are optional.

4. **Re-entrancy**

   * If errors mention “re-entrant during scan”, move `get()` out of import time.

5. **Factories**

   * Factory constructor and provider params both support DI.
   * Lazy provider builds only on first use; eager builds at `init()`.

6. **Testing advice**

   * For missing dep scenarios, mark component/provider `lazy=True` and force realization in the test.

---

## Anti-Patterns to Avoid

* Calling `container.get(...)` at module import time in scanned packages.
* Expecting type-based injection when a **name** binding exists (name wins).
* Providers that create new instances each call (Pico-IoC expects singletons; use callables if you need factories).

---

## Example: Minimal App Layout

```
myapp/
  __init__.py
  services/
    __init__.py
    components.py     # @component classes
    factories.py      # @factory_component classes + @provides methods
```

```python
# bootstrap.py
import myapp
from pico_ioc import init

container = init(myapp)
svc = container.get("heavy_service")
```

---

## FAQ (short)

* **Can I bind primitives or dicts?** Yes, via `@provides("name")` returning e.g. a dict.
* **Thread safety?** Yes. Singletons are created once per container. ContextVar ensures safe state isolation.
* **How do I exclude modules from scanning?** Use `init(root, exclude=callable)`.
* **Can I scan by module string?** Yes: `init("myapp.services")`.

---

## Version Notes Relevant to LLM Answers

* **v0.6.0**: `ComponentProxy` made fully transparent — supports operators, context managers, and more dunder methods.
* **v0.5.2**: Name-first resolution; defaulted params in constructors and provider methods are optional.
* Earlier versions: basic DI without name-first precedence.

---

## How to “Think” When Explaining Usage (LLM prompting tips)

* Be explicit about the **binding key** (type vs string).
* Map constructor/provider params to resolution rules.
* Show tiny, runnable snippets (no external deps).
* Prefer **lazy** for failure demos; prefer **eager** for production.
* If user hits `NameError`, propose concrete fixes (name, type, factory).
* Don’t promise async/background work — stick to code-level fixes.

---

End of document.

