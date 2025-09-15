# GUIDE.md — pico-ioc

> **Mission:** Make dependency wiring trivial so you can ship faster and shorten feedback cycles.
> ⚠️ **Requires Python 3.10+** (uses `typing.Annotated` and `include_extras=True`).

This guide shows how to structure a Python app with **pico-ioc**: define components, provide dependencies, bootstrap a container, and run web/CLI code predictably.

-----

## 1\) Core concepts

  - **Component** → a class managed by the container. Use `@component`.
  - **Factory component** → a class that *provides* concrete instances (e.g. `Flask()`, DB clients). Use `@factory_component`.
  - **Provider** → a method on a factory that returns a dependency and declares its **key** (usually a type). Use `@provides(key=Type)` so consumers can request by type.
  - **Container** → built via `pico_ioc.init(package_or_module, ..., overrides=...)`.
    Resolve with `container.get(TypeOrClass)`.

👉 Rule of thumb: **inject by type** (e.g., `def __init__(..., app: Flask)`).

-----

## 2\) Quick start (Hello DI)

```python
# app/config.py
from pico_ioc import component

@component
class Config:
    DB_URL = "sqlite:///demo.db"
```

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

-----

## 3\) Web example (Flask)

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

-----

## 4\) Configuration patterns

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

-----

## 5\) Testing & overrides

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
    c = init([app, test_mod], reuse=False) # Important: use reuse=False in tests
    svc = c.get(app.service.Service)
    assert svc.run() == "fake-data"
```

### 5.2 Direct `overrides`

```python
from app.repo import Repo

c = init(app, reuse=False, overrides={
    Repo: FakeRepo(),                      # constant instance
    "fast_model": lambda: {"id": 123},     # provider
    "clock": (lambda: object(), True),     # lazy provider
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

-----

## 6\) Qualifiers & collections

```python
from typing import Protocol, Annotated
from pico_ioc import component, Qualifier, qualifier

class Payment(Protocol):
    def pay(self, cents: int): ...

PAYMENTS = Qualifier("payments")

@component
@qualifier(PAYMENTS)
class Stripe(Payment): ...

@component
@qualifier(PAYMENTS)
class Paypal(Payment): ...

@component
class Billing:
    def __init__(
        self,
        # Get all components that implement the Payment protocol
        all_methods: list[Payment],
        # Get all components that implement Payment AND are marked with the "payments" qualifier
        payment_methods: list[Annotated[Payment, PAYMENTS]],
    ):
        self.all = all_methods
        self.payments = payment_methods
```

  - Inject `list[T]` → all implementations of `T`.
  - Inject `list[Annotated[T, Q]]` → only implementations of `T` tagged with qualifier `Q`.

-----

## 7\) Interceptors

Interceptors let you **observe/modify behavior** across components. They are discovered automatically via `@interceptor`.

```python
from pico_ioc import interceptor
from pico_ioc.interceptors import MethodInterceptor, Invocation

# This interceptor will wrap method calls
@interceptor(order=-10)
class TimingInterceptor(MethodInterceptor):
    def __call__(self, inv: Invocation, proceed):
        print(f"Starting {inv.method_name}...")
        result = proceed()
        print(f"Finished {inv.method_name}.")
        return result
```

There's no need to register it manually. `pico_ioc.init(app)` will find and activate it automatically.

-----

## 8\) Profiles & conditionals

Switch implementations by environment or other conditions.

```python
import os
from pico_ioc import component, conditional

class Cache: ...

@component
@conditional(profiles=("prod", "staging")) # Active only in these profiles
class RedisCache(Cache): ...

@component
@conditional(profiles=("dev", "test"))   # Active in other profiles
class InMemoryCache(Cache): ...
```

Activate a profile by passing it to `init` or setting the `PICO_PROFILE` environment variable.

```python
# In production code
container = init(app, profiles=["prod"])

# In a test
container = init(app, profiles=["test"], reuse=False)
```

  - `profiles=(...)` → matches against profiles passed to `init()`.
  - `require_env=(...)` → all environment variables must exist.
  - `predicate=callable` → custom activation rule.

-----

## 9\) Plugins & Public API helper

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

Expose your library's public API easily:

```python
# app/__init__.py
from pico_ioc.public_api import export_public_symbols_decorated
__getattr__, __dir__ = export_public_symbols_decorated("app")
```

-----

## 10\) Tips & guardrails

  - Inject by type, not by string.
  - Keep constructors cheap (no I/O).
  - One responsibility per component.
  - Use factories for external objects (DBs, clients, frameworks).
  - Fail fast: bootstrap your container at application startup.

-----

## 11\) Troubleshooting

  - **No provider for X** → Check for a missing `@component` or `@provides(key=X)`.
  - **Wrong instance** → An override or a `@primary` component is taking precedence.
  - **Circular imports** → Split modules or move imports inside provider methods.

-----

## 12\) Complete Examples

### 12.1 CLI App with Profiles and Overrides

This example shows a CLI tool that uses a different notification service based on the active profile (`"prod"` vs `"dev"`).

```python
# cli_app/services.py
from pico_ioc import component, conditional
import abc

class Notifier(abc.ABC):
    @abc.abstractmethod
    def notify(self, msg: str): ...

@component
@conditional(profiles=["prod"])
class EmailNotifier(Notifier):
    def notify(self, msg: str): print(f"EMAIL: {msg}")

@component
@conditional(profiles=["dev"])
class ConsoleNotifier(Notifier):
    def notify(self, msg: str): print(f"CONSOLE: {msg}")

@component
class MainApp:
    def __init__(self, notifier: Notifier):
        self._notifier = notifier
    def run(self):
        self._notifier.notify("Processing complete.")
```

**Running the CLI:**

```python
# run.py
from pico_ioc import init
import cli_app

# Run in "dev" mode (default if PICO_PROFILE is not set)
dev_container = init(cli_app, profiles=["dev"], reuse=False)
dev_container.get(cli_app.services.MainApp).run()
# Output: CONSOLE: Processing complete.

# Run in "prod" mode
prod_container = init(cli_app, profiles=["prod"], reuse=False)
prod_container.get(cli_app.services.MainApp).run()
# Output: EMAIL: Processing complete.

# Run a test with a direct override
class FakeNotifier(cli_app.services.Notifier):
    def notify(self, msg: str): print(f"FAKE: {msg}")

test_container = init(cli_app, overrides={cli_app.services.Notifier: FakeNotifier()}, reuse=False)
test_container.get(cli_app.services.MainApp).run()
# Output: FAKE: Processing complete.
```

### 12.2 Web App with Interceptors and Eager Initialization

This example demonstrates a Flask app where a custom interceptor logs method calls. The container is initialized eagerly to catch errors at startup.

```python
# web_app/components.py
from pico_ioc import component, interceptor
from pico_ioc.interceptors import MethodInterceptor, Invocation
from flask import Flask, jsonify

@interceptor
class LoggingInterceptor(MethodInterceptor):
    def __call__(self, inv: Invocation, proceed):
        print(f"-> Entering {inv.method_name}")
        result = proceed()
        print(f"<- Exiting {inv.method_name}")
        return result

@component
class HealthService:
    def get_status(self) -> dict:
        return {"status": "healthy"}

@component
class WebRoutes:
    def __init__(self, app: Flask, health: HealthService):
        @app.route("/health")
        def health_check():
            # The interceptor will wrap this call
            status = health.get_status()
            return jsonify(status)
```

**Running the Web Server:**

```python
# server.py
from pico_ioc import init, factory_component, provides
from flask import Flask
import web_app

# Define the Flask provider in the bootstrap script
@factory_component
class WebFactory:
    @provides(Flask)
    def make_flask(self) -> Flask: return Flask("my_web_app")

# Initialize the container, scanning both modules
container = init(["web_app", "server"])

# Get the fully configured Flask app
app = container.get(Flask)

if __name__ == "__main__":
    # When a request hits /health, the logs will show:
    # -> Entering get_status
    # <- Exiting get_status
    app.run(port=5000)
```
---

**TL;DR**
Decorate components, provide externals by type, `init()` once, and let the container wire everything — so you can run tests, serve web apps, or batch jobs with minimal glue.


