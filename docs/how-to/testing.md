# How to Test Components

## Problem

You want to write fast, isolated tests for pico-ioc components without
starting real databases, network services, or other heavy infrastructure.

## Solution

pico-ioc provides three primary mechanisms for testing:

1. **`overrides`** -- replace any provider with a mock or stub.
2. **`profiles`** -- activate test-specific conditional components.
3. **`DictSource` / `FlatDictSource`** -- provide test configuration inline.

---

### 1. Override components with mocks

Pass `overrides={Key: replacement}` to `init()`.  The replacement can be
an instance, a callable, or a `(callable, lazy)` tuple:

```python
import pytest
from pico_ioc import init, component

# Production code
@component
class Database:
    def query(self, sql: str) -> list:
        return real_db_query(sql)

@component
class UserService:
    def __init__(self, db: Database):
        self.db = db

    def get_users(self) -> list:
        return self.db.query("SELECT * FROM users")


# Test code
class FakeDatabase:
    def query(self, sql: str) -> list:
        return [{"id": 1, "name": "Alice"}]


def test_get_users():
    container = init(
        modules=[__name__],
        overrides={Database: FakeDatabase()},
    )
    svc = container.get(UserService)
    users = svc.get_users()
    assert users == [{"id": 1, "name": "Alice"}]
    container.shutdown()
```

### 2. Use unittest.mock for fine-grained control

For tests that need to assert call counts, arguments, or side effects:

```python
from unittest.mock import MagicMock

def test_user_service_calls_db():
    mock_db = MagicMock(spec=Database)
    mock_db.query.return_value = [{"id": 1}]

    container = init(
        modules=[__name__],
        overrides={Database: mock_db},
    )
    svc = container.get(UserService)
    svc.get_users()

    mock_db.query.assert_called_once_with("SELECT * FROM users")
    container.shutdown()
```

### 3. Test with inline configuration

Use `DictSource` for tree-based config or `FlatDictSource` for flat
key-value config:

```python
from dataclasses import dataclass
from pico_ioc import init, configured, configuration, DictSource

@configured(prefix="db")
@dataclass
class DbConfig:
    host: str = "localhost"
    port: int = 5432

def test_config_injection():
    cfg = configuration(
        DictSource({"db": {"host": "testdb", "port": 9999}})
    )
    container = init(modules=[__name__], config=cfg)
    db_cfg = container.get(DbConfig)
    assert db_cfg.host == "testdb"
    assert db_cfg.port == 9999
    container.shutdown()
```

### 4. Use profiles for test-specific implementations

Register test doubles that only activate under a `"test"` profile:

```python
from pico_ioc import component

@component(conditional_profiles=("test",))
class InMemoryDatabase:
    """Only registered when the 'test' profile is active."""
    def query(self, sql: str) -> list:
        return []

def test_with_profile():
    container = init(
        modules=[__name__],
        profiles=("test",),
    )
    db = container.get(InMemoryDatabase)
    assert db.query("SELECT 1") == []
    container.shutdown()
```

### 5. Validate wiring without running the app

Use `validate_only=True` to verify all bindings and detect cycles without
actually creating singletons:

```python
def test_wiring_is_valid():
    container = init(
        modules=["myapp"],
        validate_only=True,
    )
    # If we get here, all bindings are valid
    container.shutdown()
```

### 6. Pytest fixture pattern

Wrap container creation in a fixture for automatic cleanup:

```python
import pytest

@pytest.fixture
def container():
    c = init(
        modules=["myapp"],
        overrides={Database: FakeDatabase()},
        config=configuration(DictSource({"db": {"host": "testdb"}})),
    )
    yield c
    c.shutdown()


def test_service(container):
    svc = container.get(UserService)
    assert svc.get_users() is not None
```

### 7. Async test pattern

For components with `__ainit__` or async `@configure`:

```python
import pytest

@pytest.fixture
async def container():
    c = init(
        modules=["myapp"],
        overrides={Database: FakeDatabase()},
    )
    yield c
    await c.ashutdown()


@pytest.mark.asyncio
async def test_async_service(container):
    svc = await container.aget(AsyncService)
    result = await svc.process()
    assert result == "ok"
```

## Explanation

The `overrides` parameter in `init()` directly replaces the provider for a
given key in the `ComponentFactory`.  This means:

- The override is used instead of the scanned `@component` or `@provides`.
- All downstream dependents receive the override.
- Overrides take highest precedence and bypass conditional logic.

When you pass a plain value (not a callable), pico-ioc wraps it in
`lambda: value`.  When you pass a callable, it's called at resolution time
with `lambda: callable()`.

## Common Pitfalls

| Pitfall | Fix |
|---------|-----|
| **Forgetting `container.shutdown()`** -- resources leak between tests. | Use a fixture with `yield` + `shutdown()`. |
| **Overriding with a class instead of an instance** -- the override *is* the class object, not an instance of it. | Pass `overrides={Key: MyFake()}` (with parentheses). |
| **Shared mutable state between tests** -- singletons persist. | Create a fresh container per test. |
| **Async component in sync test** -- `AsyncResolutionError`. | Use `pytest.mark.asyncio` and `await container.aget(...)`. |
| **Missing modules in `init()`** -- test cannot find overridden dependencies' dependents. | Include all modules needed by the component under test. |
