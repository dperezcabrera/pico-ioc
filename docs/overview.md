# Pico-IoC Overview

Pico-IoC is a lightweight, async-ready dependency injection container for Python. It focuses on developer ergonomics, predictable wiring, and strong validation.

## Getting started

Initialize the container by scanning one or more packages or modules:

```python
from pico_ioc.api import init

pico = init(["your_project.package"])
```

## Core concepts

- Providers (components, factories, and module-level functions)
- Qualifiers, primary selection, and scopes
- Conditional activation via profiles, environment, or predicates
- Validation and troubleshooting
- Async-ready configuration

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

Factory methods can also be instance methods:

```python
from pico_ioc.api import factory, provides

class Client:
    pass

@factory
class ClientFactory:
    @provides(Client)
    def make(self, repo: "Repository") -> Client:
        return Client()
```

### Module-level functions with `@provides`

You can declare providers at module scope using functions. This is convenient for small setups or when a full factory class would be overkill.

```python
from pico_ioc.api import provides

class Cache:
    pass

@provides(Cache)
def build_cache() -> Cache:
    return Cache()
```

### String keys

When you do not want to use a type key, you can provide using a string key.

```python
from pico_ioc.api import provides

@provides("feature_flags")
def build_flags() -> dict:
    return {"beta": True}
```

## Qualifiers, primary, and scopes

All provider styles support qualifiers and primary selection. Scopes (for example, singleton) and lazy construction are also supported.

```python
from pico_ioc.api import provides, Qualifier

class Store:
    pass

@provides(Store, qualifiers=("fast",), primary=True)
def fast_store() -> Store:
    return Store()
```

Consumers can request a list of implementations with a qualifier:

```python
from typing import Annotated, List
from pico_ioc.api import component, Qualifier

@component
class UsesStores:
    def __init__(self, stores: Annotated[List["Store"], Qualifier("fast")]) -> None:
        self.stores = stores
```

Scopes and qualifiers can also be combined:

```python
@provides("cache", qualifiers=("primary",), scope="singleton", primary=True)
def build_primary_cache() -> dict:
    return {}
```

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

Errors are reported with actionable messages about missing bindings, type mismatches, and ambiguous providers.

## Retrieving instances

Use the container to retrieve instances by type or string key:

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

## Async-ready configuration

If a constructed object declares asynchronous configuration methods marked with `@configure`, Pico-IoC will await them during construction.
