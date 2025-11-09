# Core Concepts: @component, @factory, @provides

To inject an object (a “component”), pico-ioc first needs to know how to create it. This is called registration.

There are two primary ways to register a component. Your choice depends on one simple question: “Do I own the code for this class?”

1. @component: The default choice. You use this decorator on your own classes.
2. @provides: The flexible provider pattern. You use this to register third‑party classes (which you can't decorate) or for any object that requires complex creation logic.

---

## 1. `@component`: The Default Choice

This is the decorator you learned in the Getting Started guide. You should use it for most of your application’s code.

Placing `@component` on a class tells pico-ioc: “This class is part of the system. Scan its `__init__` method to find its dependencies, and make it available for injection into other components.”

### Example

`@component` is the only thing you need. pico-ioc handles the rest.

```python
# app/database.py
from pico_ioc import component

@component
class Database:
    """A simple component with no dependencies."""
    def query(self, sql: str) -> dict:
        # ... logic to run query
        return {"data": "..."}
```

```python
# app/user_service.py
from pico_ioc import component
from app.database import Database

@component
class UserService:
    """This component depends on the Database."""

    # pico-ioc will automatically inject the Database instance
    def __init__(self, db: Database):
        self.db = db

    def get_user(self, user_id: int) -> dict:
        return self.db.query(f"SELECT * FROM users WHERE id = {user_id}")
```

```python
# main.py
from pico_ioc import init
from app.user_service import UserService

# Scan specific modules (strings are importable module paths)
container = init(modules=['app.database', 'app.user_service'])

user_svc = container.get(UserService)
user_data = user_svc.get_user(1)
print(user_data)
```

When to use `@component`:
- It’s a class you wrote and can modify.
- The `__init__` method is all that’s needed to create a valid instance.

-----

## 2. When `@component` Isn’t Enough

You cannot use `@component` when:
- You don’t own the class: You can’t add `@component` to `redis.Redis` from redis-py or `BaseClient` from botocore/boto3.
- Creation logic is complex: You can’t just call the constructor. You need to call a factory (like `redis.Redis.from_url(...)`) or run conditional logic.
- You are implementing a Protocol or abstract type: You want to register a concrete class as the provider for an abstract protocol or interface.

For all these cases, use the Provider Pattern with `@provides`.

-----

## 3. `@provides`: The Provider Pattern

`@provides(SomeType)` decorates a function or method that acts as a recipe for building `SomeType`. pico-ioc offers three flexible ways to use it, ordered from simplest to most complex.

The following examples assume a `config.py` module defining configuration dataclasses (see the configuration guides).

### Pattern 1: Module-Level `@provides` (Simplest)

This is a simple, lightweight method for registering a single third‑party object or a component with complex logic. You write a function in any scanned module and decorate it.

```python
# app/clients.py
import redis
from pico_ioc import provides, configured
from dataclasses import dataclass

@configured(prefix="REDIS_")
@dataclass
class RedisConfig:
    URL: str = "redis://localhost:6379/0"

# This function is the "recipe" for building a redis.Redis client.
@provides(redis.Redis)
def build_redis_client(config: RedisConfig) -> redis.Redis:
    # Dependencies (RedisConfig) are injected into the function's arguments
    return redis.Redis.from_url(config.URL)
```

Scan the module containing the provider:
```python
from pico_ioc import init
import redis
from app.clients import build_redis_client

container = init(modules=['app.clients'])
redis_client = container.get(redis.Redis)
```

### Pattern 2: Group providers with `@factory` (Static or Class methods)

If you have many stateless providers, group them inside a class decorated with `@factory`. Use `@staticmethod` or `@classmethod` when the provider does not need factory instance state.

Important: apply `@provides(...)` before `@staticmethod`/`@classmethod` so pico-ioc sees the underlying function.

```python
# app/factories.py
import redis
import botocore.client
import boto3
from pico_ioc import factory, provides, configured
from dataclasses import dataclass

@configured(prefix="REDIS_")
@dataclass
class RedisConfig:
    URL: str = "redis://localhost:6379/0"

@configured(prefix="AWS_")
@dataclass
class S3Config:
    ACCESS_KEY_ID: str
    SECRET_ACCESS_KEY: str
    REGION: str = "us-east-1"

@factory
class ExternalClientsFactory:
    # Stateless providers

    @provides(redis.Redis)
    @staticmethod
    def build_redis(config: RedisConfig) -> redis.Redis:
        return redis.Redis.from_url(config.URL)

    @provides(botocore.client.BaseClient)
    @classmethod
    def build_s3(cls, config: S3Config) -> botocore.client.BaseClient:
        return boto3.client(
            "s3",
            aws_access_key_id=config.ACCESS_KEY_ID,
            aws_secret_access_key=config.SECRET_ACCESS_KEY,
            region_name=config.REGION,
        )
```

Scan the factory module:
```python
from pico_ioc import init
import redis
import botocore.client

container = init(modules=['app.factories'])

cache = container.get(redis.Redis)
s3 = container.get(botocore.client.BaseClient)
```

### Pattern 3: `@factory` Instance Methods (Stateful)

Use this pattern when providers need to share common state or resources, such as a connection pool managed by the factory instance. The `@factory` class is instantiated, its `__init__` dependencies are injected, and `@provides` methods can use `self`.

```python
# app/db_factory.py
from pico_ioc import factory, provides, configured
from dataclasses import dataclass

class ConnectionPool:
    @staticmethod
    def create(config) -> "ConnectionPool":
        return ConnectionPool()

    def get_connection(self):
        return object()  # placeholder

class UserClient:
    def __init__(self, pool: ConnectionPool):
        self.pool = pool

class AdminClient:
    def __init__(self, pool: ConnectionPool):
        self.pool = pool

@configured(prefix="DB_POOL_")
@dataclass
class PoolConfig:
    MAX_SIZE: int = 10

@factory
class DatabaseClientFactory:
    # This factory is stateful. It creates one pool and
    # shares it with all clients it builds.

    def __init__(self, config: PoolConfig):
        self.pool = ConnectionPool.create(config)

    @provides(UserClient)
    def build_user_client(self) -> UserClient:
        return UserClient(self.pool)

    @provides(AdminClient)
    def build_admin_client(self) -> AdminClient:
        return AdminClient(self.pool)
```

Scan the module containing the factory:
```python
from pico_ioc import init
from app.db_factory import UserClient, AdminClient

container = init(modules=['app.db_factory'])
user_client = container.get(UserClient)
admin_client = container.get(AdminClient)
```

-----

## 4. Using the Injected Component

Your consumer classes do not care how a component was registered (`@component` or `@provides`). They just ask for the type they need via constructor injection. This decouples your business logic (the “what”) from the creation logic (the “how”).

```python
# app/cache_service.py
import redis
from pico_ioc import component

@component
class CacheService:
    # pico-ioc knows it needs a `redis.Redis` instance.
    # It will find your provider (module-level or factory),
    # run it (injecting its dependencies like RedisConfig),
    # and inject the resulting redis.Redis instance here.
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    def set_value(self, key: str, value: str):
        self.redis.set(key, value)
```

```python
# main.py
from pico_ioc import init
from app.cache_service import CacheService

container = init(modules=['app.clients', 'app.cache_service'])
cache = container.get(CacheService)
cache.set_value("greeting", "hello")
```

-----

## 5. Protocols and Abstract Types

Often you want to depend on an abstract type (interface) and provide a concrete implementation. Use Python’s `Protocol` or abstract base classes for the consumer, and register a provider for the concrete type or for the abstract type directly.

```python
# app/ports.py
from typing import Protocol

class Clock(Protocol):
    def now(self) -> float: ...
```

```python
# app/impl.py
import time
from pico_ioc import component, provides
from app.ports import Clock

@component
class SystemClock:
    def now(self) -> float:
        return time.time()

# Option A: Consumers depend on the concrete type (SystemClock), no extra work needed.
# Option B: Register SystemClock as the provider for the abstract Clock type:
@provides(Clock)
def provide_clock() -> Clock:
    return SystemClock()
```

```python
# app/service.py
from pico_ioc import component
from app.ports import Clock

@component
class JobService:
    def __init__(self, clock: Clock):
        self.clock = clock

    def run(self):
        started_at = self.clock.now()
        # ...
        return started_at
```

Scan modules that include either the concrete `@component` or the `@provides(Clock)` provider.

-----

## Summary: When to Use What

- @component
  - Decorator for a class you own.
  - Use when the `__init__` is sufficient to construct the instance.
  - Best for most of your application code.

- @provides
  - Decorator for a recipe function or method that constructs a target type.
  - Use for third‑party classes, complex creation logic, or mapping concrete implementations to abstract protocols.
  - Styles:
    - Module function (simplest).
    - Grouped in a `@factory` via `@staticmethod`/`@classmethod` (stateless).
    - Instance methods on a `@factory` (stateful, shared resources).

Rule of thumb: Default to `@component`. When you can’t, use the simplest `@provides` pattern that fits your needs (start with a module‑level function).

-----

## Next Steps

Now that you understand how to register components, the next logical step is to learn how to configure them using the unified configuration system.

- Configuration: Basic Concepts: Learn about the configuration builder and how pico-ioc handles different sources.
  See: ./configuration-basic.md
