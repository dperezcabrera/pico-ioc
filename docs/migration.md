# Migration Guide

This guide covers breaking changes across major and minor versions of
pico-ioc and provides before/after code examples.

---

## Migrating from v1.x to v2.0.0

v2.0.0 is a complete redesign. If you were using an internal v1.x version,
treat this as a greenfield migration.

### Key changes

| Feature | v1.x | v2.0.0 |
|---------|------|--------|
| Python version | 3.8+ | 3.10+ (3.11+ since v2.2.2) |
| Decorator API | `@inject`, stacked decorators | `@component`, `@factory`, `@provides` |
| Container creation | Manual wiring | `init(modules=[...])` with auto-scanning |
| Scopes | Manual | `singleton`, `prototype`, `request`, `session`, `transaction` |
| Async | Not supported | First-class `aget()`, `__ainit__`, async `@configure` |
| AOP | Not available | `@intercepted_by`, `MethodInterceptor` protocol |
| Config | Manual | `@configured`, `configuration(...)`, tree/flat sources |
| Events | Not available | `EventBus`, `@subscribe`, `AutoSubscriberMixin` |

### Before (v1.x)

```python
# v1.x -- manual wiring
class Database:
    pass

class UserService:
    def __init__(self, db: Database):
        self.db = db

db = Database()
svc = UserService(db=db)
```

### After (v2.0.0)

```python
from pico_ioc import component, init

@component
class Database:
    pass

@component
class UserService:
    def __init__(self, db: Database):
        self.db = db

container = init(modules=[__name__])
svc = container.get(UserService)  # Database injected automatically
```

---

## Migrating from v2.0.x to v2.1.0

### Breaking: `@configuration` decorator removed

The `@configuration` decorator for flat key-value binding was removed.
Use `@configured` with the unified `configuration(...)` builder instead.

#### Before (v2.0.x)

```python
from pico_ioc import configuration

@configuration
class DbConfig:
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432

container = init(
    modules=[__name__],
    config={"DB_HOST": "myhost"},
)
```

#### After (v2.1.0+)

```python
from dataclasses import dataclass
from pico_ioc import configured, configuration, FlatDictSource, init

@configured(prefix="DB_", mapping="flat")
@dataclass
class DbConfig:
    host: str = "localhost"
    port: int = 5432

container = init(
    modules=[__name__],
    config=configuration(FlatDictSource({"DB_HOST": "myhost"})),
)
```

### Breaking: `init()` signature changed

The old `config` (flat dict) and `tree_config` parameters were removed.
All configuration is now passed through `config: ContextConfig`.

#### Before (v2.0.x)

```python
container = init(
    modules=[__name__],
    config={"KEY": "value"},
    tree_config={"db": {"host": "localhost"}},
)
```

#### After (v2.1.0+)

```python
from pico_ioc import configuration, FlatDictSource, DictSource

container = init(
    modules=[__name__],
    config=configuration(
        FlatDictSource({"KEY": "value"}),
        DictSource({"db": {"host": "localhost"}}),
    ),
)
```

### Breaking: `custom_scopes` API simplified

`custom_scopes` now accepts `Iterable[str]` instead of a dict of
scope implementations.

#### Before (v2.0.x)

```python
container = init(
    modules=[__name__],
    custom_scopes={"tenant": ContextVarScope(...)},
)
```

#### After (v2.1.0+)

```python
container = init(
    modules=[__name__],
    custom_scopes=["tenant"],  # ContextVarScope auto-created
)
```

---

## Migrating from v2.1.x to v2.2.0

### New: `CustomScanner` protocol

v2.2.0 introduced `CustomScanner` for extending component discovery. No
breaking changes -- this is additive.

### New: `container.ashutdown()`

Added `ashutdown()` for async cleanup. Replaces the pattern of manually
calling `await container.cleanup_all_async()`.

---

## Migrating from v2.2.1 to v2.2.2

### Breaking: Python 3.10 dropped

Minimum Python version raised from 3.10 to 3.11. Update your CI matrix
and `requires-python` if needed.

---

## Migrating from v2.2.2 to v2.2.3

No breaking changes. Fixes PEP 563 (`from __future__ import annotations`)
compatibility across the framework.

---

## Summary of Breaking Changes by Version

| Version | Breaking Change |
|---------|----------------|
| 2.0.0 | Complete redesign; new decorator API, new `init()` |
| 2.1.0 | `@configuration` removed; `init()` `config`/`tree_config` params removed; `custom_scopes` simplified |
| 2.1.3 | LRU eviction removed; manual `cleanup_scope()` required |
| 2.2.2 | Python 3.10 support dropped |
