# GUIDE.md — pico-ioc

> **Mission:** Make dependency wiring trivial so you can ship faster and shorten feedback cycles.  
> ⚠️ **Requires Python 3.10+** (uses `typing.Annotated` and `include_extras=True`).

This guide shows how to structure a Python app with **pico-ioc**: define components, provide dependencies, bootstrap a container, and run web/CLI code predictably.

---

## 1) Core concepts

- **Component** → a class managed by the container. Use `@component`.  
- **Factory component** → a class that *provides* concrete instances (e.g. `Flask()`, DB clients). Use `@factory_component`.  
- **Provider** → a method on a factory that returns a dependency and declares its **key** (usually a type). Use `@provides(key=Type)` so consumers can request by type.  
- **Container** → built via `pico_ioc.init(package_or_module, ..., overrides=...)`.  
  Resolve with `container.get(TypeOrClass)`.

👉 Rule of thumb: **inject by type** (e.g., `def __init__(..., app: Flask)`).  

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

c = init(app)
svc = c.get(app.service.Service)
print(svc.run())  # -> "fetching from sqlite:///demo.db"
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

---

## 4) Configuration patterns

**Env-backed config:**

```python
import os
from pico_ioc import component

@component
class Config:
    WORKERS: int = int(os.getenv("WORKERS", "4"))
    DEBUG: bool = os.getenv("DEBUG", "0") == "1"
```

**Inject into consumers:**

```python
@component
class Runner:
    def __init__(self, cfg: Config):
        self._debug = cfg.DEBUG
```

---

## 5) Testing & overrides

You often want to replace real deps with fakes/mocks.

### 5.1 Test modules

```python
from pico_ioc import factory_component, provides
from app.repo import Repo

class FakeRepo(Repo):
    def fetch(self) -> str: return "fake-data"

@factory_component
class TestOverrides:
    @provides(key=Repo)
    def provide_repo(self) -> Repo: return FakeRepo()
```

```python
import app, tests.test_overrides_module as test_mod
from pico_ioc import init

def test_service_fetch():
    c = init([app, test_mod])
    svc = c.get(app.service.Service)
    assert svc.run() == "fake-data"
```

### 5.2 Direct `overrides`

```python
c = init(app, overrides={
    app.repo.Repo: object(),                # constant
    "fast_model": lambda: {"id": 123},      # provider
    "clock": (lambda: object(), True),      # lazy provider
})
```

### 5.3 Scoped subgraphs

```python
import pico_ioc, src
from tests.fakes import FakeDocker
from src.runner_service import RunnerService

def test_runner():
    with pico_ioc.scope(
        modules=[src],
        roots=[RunnerService],
        overrides={"docker.DockerClient": FakeDocker()},
        strict=True, lazy=True,
    ) as c:
        svc = c.get(RunnerService)
        assert isinstance(svc, RunnerService)
```

---

## 6) Qualifiers & collections

```python
from typing import Protocol, Annotated
from pico_ioc import component, qualifier

class Payment(Protocol):
    def pay(self, cents: int): ...

@qualifier("primary")
class Primary: pass

@qualifier("fallback")
class Fallback: pass

@component
class Stripe(Payment): ...

@component
class Paypal(Payment): ...

@component
class Billing:
    def __init__(
        self,
        all_methods: list[Payment],
        primary: Annotated[Payment, Primary],
        fallbacks: list[Annotated[Payment, Fallback]] = [],
    ):
        self.all = all_methods
        self.primary = primary
        self.fallbacks = fallbacks
```

* Inject `list[T]` → all implementations.
* Inject `list[Annotated[T, Q]]` → only tagged ones.

---

## 7) Interceptors API

Interceptors let you **observe/modify lifecycle**.

```python
from pico_ioc import Interceptor

class LoggingInterceptor(Interceptor):
    def on_resolve(self, key, ann, quals): print("resolving", key)
    def on_before_create(self, key): print("creating", key)
    def on_after_create(self, key, inst): print("created", key); return inst
    def on_exception(self, key, exc): print("error", key, exc); raise
```

```python
import pico_ioc, myapp
c = pico_ioc.init(myapp, interceptors=[LoggingInterceptor()])
```

Hooks: `on_resolve`, `on_before_create`, `on_after_create`, `on_invoke`, `on_exception`.
Use cases: logging, metrics, tracing, policies, audit.

---

## 8) Profiles & conditionals

Switch impls by env/predicate.

```python
from pico_ioc import component, conditional

class Cache: ...

@component
@conditional(require_env=("REDIS_URL",))
class RedisCache(Cache): ...

@component
@conditional(predicate=lambda: os.getenv("PROFILE") == "test")
class InMemoryCache(Cache): ...
```

* `require_env=(...)` → all must exist.
* `predicate=callable` → custom rule.
* Missing providers → bootstrap error (fail-fast).

Use cases: **profiles** (`test`, `prod`, `ci`), optional deps, feature flags.

---

## 9) Plugins & Public API helper

```python
from pico_ioc import plugin
from pico_ioc.plugins import PicoPlugin

@plugin
class TracingPlugin(PicoPlugin):
    def before_scan(self, pkg, binder): print("scanning", pkg)
    def after_ready(self, c, binder): print("ready")
```

```python
c = init(app, plugins=(TracingPlugin(),))
```

Expose public API:

```python
# app/__init__.py
from pico_ioc.public_api import export_public_symbols_decorated
__getattr__, __dir__ = export_public_symbols_decorated("app", include_plugins=True)
```

---

## 10) Tips & guardrails

* Inject by type, not by string.
* Keep constructors cheap (no I/O).
* One responsibility per component.
* Use factories for externals (DBs, clients, frameworks).
* Fail fast: bootstrap at startup.
* No globals; only resolve at edges.

---

## 11) Troubleshooting

* **No provider for X** → missing `@provides(key=X)`.
* **Wrong instance** → duplicates; last registered wins.
* **Circular imports** → split modules or move imports inside providers.
* **Framework not found** → check correct `@provides(key=FrameworkType)`.

---

## 12) Examples

* **Bootstrap auto-exports**

```python
# src/__init__.py
from pico_ioc.public_api import export_public_symbols_decorated
__getattr__, __dir__ = export_public_symbols_decorated("src")
```

* **Flask with waitress**

```python
import pico_ioc, src
from waitress import serve
c = pico_ioc.init(src)
app = c.get("flask.Flask")
serve(app, host="0.0.0.0", port=5001)
```

* **FastAPI with uvicorn**

```python
import pico_ioc, src, uvicorn
c = pico_ioc.init(src)
app = c.get("fastapi.FastAPI")
uvicorn.run(app, host="0.0.0.0", port=8000)
```

---

**TL;DR**
Decorate components, provide externals by type, `init()` once, and let the container wire everything — so you can run tests, serve web apps, or batch jobs with minimal glue.


