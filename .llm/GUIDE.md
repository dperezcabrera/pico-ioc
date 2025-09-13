# GUIDE.md — pico-ioc

> **Mission:** make dependency wiring trivial so you can ship faster and shorten feedback cycles.  
> ⚠️ **Requires Python 3.10+** (uses `typing.Annotated` and `include_extras=True`).

This guide shows how to structure a Python app with **pico-ioc**: define components, provide dependencies, bootstrap a container, and run web/CLI code predictably.

---

## 1) Core concepts

* **Component**: a class managed by the container. Use `@component`.
* **Factory component**: a class that *provides* concrete instances (e.g., `Flask()`, clients). Use `@factory_component`.
* **Provider**: a method on a factory that returns a dependency and declares its **key** (usually a type). Use `@provides(key=Type)` so consumers can request by type.
* **Container**: built via `pico_ioc.init(package_or_module, ..., overrides=...)`. Resolve with `container.get(TypeOrClass)`.

Resolution rule of thumb: **ask by type** (e.g., `container.get(Flask)` or inject `def __init__(..., app: Flask)`).

---

## 2) Quick start (Hello DI)

```python
# app/config.py
from pico_ioc import component

@component
class Config:
    DB_URL = "sqlite:///demo.db"
````

```python
# app/repo.py
from pico_ioc import component
from .config import Config

@component
class Repo:
    def __init__(self, cfg: Config):
        self._url = cfg.DB_URL
    def fetch(self) -> str:
        return f"fetching from {self._url}"
```

```python
# app/service.py
from pico_ioc import component
from .repo import Repo

@component
class Service:
    def __init__(self, repo: Repo):
        self.repo = repo
    def run(self) -> str:
        return self.repo.fetch()
```

```python
# main.py
from pico_ioc import init
import app

container = init(app)          # build the container from the package
svc = container.get(app.service.Service)
print(svc.run())               # -> "fetching from sqlite:///demo.db"
```

Run:

```bash
python main.py
```

---

## 3) Web example (Flask)

```python
# app/app_factory.py
from pico_ioc import factory_component, provides
from flask import Flask

@factory_component
class AppFactory:
    @provides(key=Flask)
    def provide_flask(self) -> Flask:
        app = Flask(__name__)
        app.config["JSON_AS_ASCII"] = False
        return app
```

```python
# app/api.py
from pico_ioc import component
from flask import Flask, jsonify

@component
class ApiApp:
    def __init__(self, app: Flask):
        self.app = app
        self._routes()

    def _routes(self):
        @self.app.get("/health")
        def health():
            return jsonify(status="ok")
```

```python
# web.py
from pico_ioc import init
from flask import Flask
import app

c = init(app)
flask_app = c.get(Flask)

if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=5000)
```

Run:

```bash
python web.py
# GET http://localhost:5000/health -> {"status":"ok"}
```

---

## 4) Configuration patterns

**Environment-backed config:**

```python
# app/config.py
import os
from pico_ioc import component

@component
class Config:
    WORKERS: int = int(os.getenv("WORKERS", "4"))
    DEBUG: bool = os.getenv("DEBUG", "0") == "1"
```

**Inject where needed** (constructor injection keeps code testable):

```python
@component
class Runner:
    def __init__(self, cfg: Config):
        self._debug = cfg.DEBUG
```

---

## 5) Testing & overrides

You often want to replace real dependencies with fakes or mocks in tests.  
There are two main patterns:

### 5.1 Composition modules

Define a **test factory** that provides fakes using the same keys:

```python
# tests/test_overrides_module.py
from pico_ioc import factory_component, provides
from app.repo import Repo

class FakeRepo(Repo):
    def fetch(self) -> str:
        return "fake-data"

@factory_component
class TestOverrides:
    @provides(key=Repo)
    def provide_repo(self) -> Repo:
        return FakeRepo()
````

Build the container for tests with both packages (app + overrides):

```python
from pico_ioc import init
import app
from tests import test_overrides_module

def test_service_fetch():
    c = init([app, test_overrides_module])
    svc = c.get(app.service.Service)
    assert svc.run() == "fake-data"
```

### 5.2 Direct `overrides` argument

`init()` also accepts an `overrides` dict for ad-hoc mocks. Each entry can be:

* **Instance** → bound as constant.
* **Callable** (0 args) → bound as provider, non-lazy.
* **(provider, lazy\_bool)** → provider with explicit laziness.

```python
from pico_ioc import init
import app

fake_repo = object()

c = init(app, overrides={
    app.repo.Repo: fake_repo,            # constant
    "fast_model": lambda: {"id": 123},   # provider
    "expensive": (lambda: object(), True) # lazy provider
})
```

This is handy for **quick mocking in unit tests**:

```python
def test_with_direct_overrides():
    c = init(app, overrides={"fast_model": {"fake": True}}, reuse=False)
    svc = c.get(app.service.Service)
    assert svc.repo.fetch() == "fake-data"
```

> Note: if you call `init(..., reuse=True, overrides=...)` on an already built container, the overrides are applied on the cached container.

### 5.3 Scoped subgraphs with `scope(...)`

For unit tests or lightweight integration you can build a **reduced container** that only
includes the dependencies reachable from certain root components.

```python
from pico_ioc
from src.runner_service import RunnerService
from tests.fakes import FakeDocker, TestRegistry
import src

def test_runner_service_subset():
    c = pico_ioc.scope(
        modules=[src],
        roots=[RunnerService],   # only RunnerService and its deps
        overrides={
            "docker.DockerClient": FakeDocker(),
            TestRegistry: TestRegistry(),
        },
        strict=True,   # fail if dep is outside the subgraph
        lazy=True,     # instantiate on demand
    )
    svc = c.get(RunnerService)
    assert isinstance(svc, RunnerService)
```
Benefits:

* **Fast**: you don’t need to bootstrap the entire app (HTTP, controllers, etc.).
* **Deterministic**: fails early if a dependency is missing.
* **Flexible**: works outside tests as well (e.g. CLI tools, benchmarks).

> Note: `scope` does *not* add new lifecycles. It creates a **bounded container**
> with the same singleton-per-container semantics.

**Tag filtering**

You can limit the subgraph by **tags**:

- Tag components/factories:
```python
  from pico_ioc import component, factory_component, provides

  @component(tags={"runtime", "docker"})
  class DockerClient: ...

  @factory_component
  class ObservabilityFactory:
      @provides("metrics", tags={"observability"})
      def make_metrics(self): ...
```

* Filter during `scope()`:

### API Reference: `scope(...)`

```python
pico_ioc.scope(
    *,
    modules: Iterable[Any] = (),
    roots: Iterable[type] = (),
    overrides: Optional[Dict[Any, Any]] = None,
    base: Optional[PicoContainer] = None,
    include_tags: Optional[set[str]] = None,
    exclude_tags: Optional[set[str]] = None,
    strict: bool = True,
    lazy: bool = True,
) -> PicoContainer
```

**Parameters**

* `modules` — list of packages/modules to scan.
* `roots` — root components to keep; container is pruned to their subgraph.
* `overrides` — same format as in `init()`, replace bindings.
* `base` — optional base container to reuse existing providers.
* `include_tags` — only include providers with one of these tags (if set).
* `exclude_tags` — drop any provider with these tags.
* `strict` — if `True`, missing deps cause `NameError`; otherwise skipped.
* `lazy` — if `True`, instantiate only on demand; if `False`, instantiate eagerly.

**Notes**

* `scope` does not add new lifecycles — it’s still singleton-per-container.
* Tag filters are applied before traversal; excluded providers behave as missing.


**Rules**

* If a provider has **no tags**, it’s considered neutral (passes unless excluded via other criteria).
* `exclude_tags` wins over `include_tags` for any provider that matches both.
* Filtering is applied **before** traversal; pruned providers are treated as missing (and will error in `strict=True`).

---

## 6) Qualifiers & collection injection

```python
from typing import Protocol, Annotated
from pico_ioc import component, Qualifier, qualifier

class Handler(Protocol):
    def handle(self, s: str) -> str: ...

PAYMENTS = Qualifier("payments")

@component
@qualifier(PAYMENTS)
class StripeHandler(Handler): ...

@component
@qualifier(PAYMENTS)
class PaypalHandler(Handler): ...

@component
class Orchestrator:
    def __init__(self, handlers: list[Annotated[Handler, PAYMENTS]]):
        self.handlers = handlers

    def run(self, s: str) -> list[str]:
        return [h.handle("ok") for h in self.handlers]

```
If you request list[Handler] you get all implementations.
If you request list[Annotated[Handler, PAYMENTS]], you only get the tagged ones.

---

## 7) Plugins & Public API helper

```python
from pico_ioc import plugin
from pico_ioc.plugins import PicoPlugin

@plugin
class TracingPlugin(PicoPlugin):
    def before_scan(self, package, binder):
        print(f"Scanning {package}")
    def after_ready(self, container, binder):
        print("Container ready")
```

Register explicitly:

```python
from pico_ioc import init
import app

c = init(app, plugins=(TracingPlugin(),))
```

And to expose your app’s API cleanly:

```python
# app/__init__.py
from pico_ioc.public_api import export_public_symbols_decorated
__getattr__, __dir__ = export_public_symbols_decorated("app", include_plugins=True)
```

Now you can import directly:

```python
from app import Service, Config, TracingPlugin
```

---

## 8) Tips & guardrails

* **Ask by type**: inject `Flask`, `Config`, `Repo` instead of strings.
* **Keep constructors cheap**: do not perform I/O in `__init__`.
* **Small components**: one responsibility per component; wire them in service classes.
* **Factories provide externals**: frameworks, clients, DB engines belong in `@factory_component` providers.
* **Fail fast**: build the container at startup and crash early if a dependency is missing.
* **No globals**: let the container own lifecycle; fetch via `container.get(...)` only at the edges (bootstrap).

---

## 9) Troubleshooting

* **“No provider for X”**
  Ensure a `@provides(key=X)` exists in a module passed to `init(...)`, and your constructor type annotation is exactly `X`.

* **Wrong instance injected**
  Check for duplicate providers for the same key. The last registered wins; control order via the list passed to `init([module_a, module_b])`.

* **Circular imports**
  Split components or move heavy imports into providers. Keep modules acyclic where possible.

* **Flask not found**
  Verify `from flask import Flask` and that your factory uses `@provides(key=Flask)`. Resolve it with `container.get(Flask)`.

---

## 10) Examples

### 10.1 Bootstrap & auto-imports

```python
# src/__init__.py
from pico_ioc.public_api import export_public_symbols_decorated
__getattr__, __dir__ = export_public_symbols_decorated("src", include_plugins=True)
```

Now you can import cleanly:

```python
from src import Service, Config, TracingPlugin
```

### 10.2 Flask with waitress

```python
# main_flask.py
import logging
from waitress import serve
import pico_ioc, src
from flask import Flask

def main():
    logging.basicConfig(level=logging.INFO)
    c = pico_ioc.init(src)
    app = c.get(Flask)
    serve(app, host="0.0.0.0", port=5001, threads=8)
```

### 10.3 FastAPI with uvicorn

```python
# main_fastapi.py
import logging
import pico_ioc, src, uvicorn
from fastapi import FastAPI

def main():
    logging.basicConfig(level=logging.INFO)
    c = pico_ioc.init(src)
    app = c.get(FastAPI)
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### 10.4 App Factory for externals

```python
# src/app_factory.py
from pico_ioc import factory_component, provides
from flask import Flask
from fastapi import FastAPI
import docker
from .config import Config

@factory_component
class AppFactory:
    def __init__(self):
        self._config = Config()

    @provides(key=Config)
    def provide_config(self) -> Config:
        return self._config

    @provides(key=Flask)
    def provide_flask(self) -> Flask:
        return Flask(__name__)

    @provides(key=FastAPI)
    def provide_fastapi(self) -> FastAPI:
        return FastAPI()

    @provides(key=docker.DockerClient)
    def provide_docker(self) -> docker.DockerClient:
        return docker.from_env()
```

---

**TL;DR**
Decorate components, provide externals by type, `init()` once, and let the container do the wiring—so you can **run tests, serve web apps, or batch jobs with minimal glue**.


