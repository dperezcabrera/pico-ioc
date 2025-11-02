# Pico-IoC Overview

Pico-IoC is a lightweight, async-ready dependency injection container for Python. It focuses on developer ergonomics, predictable wiring, and strong validation.

## Core concepts

1. Components
2. Factories
3. Configuration objects
4. Configured graphs

## Ways to register providers

Pico-IoC supports three primary ways to declare providers:

1. Class components
2. Factory classes with `@provides` methods
3. Module-level functions with `@provides`

### Class components

Use `@component` to mark a class as a component. Constructor parameters are resolved from the container.

```python
from pico_ioc.api import component

@component
class Repository:
    def __init__(self, url: str) -> None:
        self.url = url
```

### Factory classes

Use `@factory` on a class and `@provides` on its methods. Methods can be instance methods, `@staticmethod`, or `@classmethod`.

```python
from pico_ioc.api import factory, provides

class Service:
    pass

@factory
class ServiceFactory:
    @staticmethod
    @provides(Service)
    def build(repo: "Repository") -> Service:
        return Service()
```

### Module-level functions with `@provides`

You can also declare providers at module scope using functions. This is convenient for small setups or when a full factory class would be overkill.

```python
from pico_ioc.api import provides

class Service:
    pass

@provides(Service)
def build_service(repo: "Repository") -> Service:
    return Service()
```

### String keys

When you do not want to use a type key, you can provide using a string key.

```python
from pico_ioc.api import provides

@provides("cache")
def build_cache() -> dict:
    return {}
```

## Scopes and qualifiers

All three styles support `scope`, `qualifiers`, `primary`, `lazy`, and conditional activation via profiles and environment variables.

```python
@provides("cache", qualifiers=("primary",), scope="singleton", primary=True)
def build_primary_cache() -> dict:
    return {}
```

## Validation

`init(..., validate_only=True)` performs fast fail validation of bindings and constructor/factory parameters. Errors are reported with actionable messages.

## Async-ready configuration

If a constructed object declares asynchronous configuration methods marked with `@configure`, Pico-IoC will await them during construction.

```

```markdown
# docs/guide.md
# Pico-IoC Guide

## Getting started

```python
from pico_ioc.api import init

pico = init(["your_project.package"])
```

## Declaring providers

### Class components

```python
from pico_ioc.api import component

@component
class Database:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
```

### Factory classes with `@provides`

```python
from pico_ioc.api import factory, provides

class Service:
    pass

@factory
class ServiceFactory:
    @provides(Service)
    def build(self, db: "Database") -> Service:
        return Service()
```

### Module-level `@provides` functions

Use module-level functions to provide objects directly without a factory class.

```python
from pico_ioc.api import provides

class Cache:
    pass

@provides(Cache)
def build_cache() -> Cache:
    return Cache()
```

You can also use string keys:

```python
from pico_ioc.api import provides

@provides("feature_flags")
def build_flags() -> dict:
    return {"beta": True}
```

### Static and class methods with `@provides`

Factory methods can be `@staticmethod` or `@classmethod`:

```python
from pico_ioc.api import factory, provides

class Client:
    pass

@factory
class ClientFactory:
    @staticmethod
    @provides(Client)
    def make() -> Client:
        return Client()
```

## Qualifiers and primary

```python
from pico_ioc.api import provides, Qualifier

class Store:
    pass

@provides(Store, qualifiers=("fast",), primary=True)
def fast_store() -> Store:
    return Store()
```

Consumers can request a list of implementations with a qualifier using `Annotated[List[T], Qualifier("name")]`.

## Conditional activation

Providers can be enabled conditionally by profiles, environment variables, or a predicate.

```python
from pico_ioc.api import provides

@provides("metrics", conditional_profiles=("prod",))
def prod_metrics() -> dict:
    return {"enabled": True}
```

## Validation and troubleshooting

Run validation without building instances:

```python
from pico_ioc.api import init
from pico_ioc.exceptions import InvalidBindingError

try:
    init(["your_project.package"], validate_only=True)
except InvalidBindingError as e:
    print(e)
```

## Example end-to-end

```python
from pico_ioc.api import component, provides, init

class Service:
    pass

@component
class Repo:
    pass

@provides(Service)
def service(repo: Repo) -> Service:
    return Service()

pico = init([__name__])
svc = pico.get(Service)
```
