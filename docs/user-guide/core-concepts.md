# Core Concepts: @component, @factory, @provides

To inject an object (a "component"), `pico-ioc` first needs to know how to create it. This is called **registration**.

There are two primary ways to register a component. Your choice depends on one simple question: **"Do I own the code for this class?"**

1.  **`@component`**: The default choice. You use this decorator **on your own classes**.
2.  **`@provides`**: The flexible provider pattern. You use this to register **third-party classes** (which you can't decorate) or for any object that requires complex creation logic.

---

## 1. `@component`: The Default Choice

This is the decorator you learned in the "Getting Started" guide. You should use it for **90% of your application's code**.

Placing `@component` on a class tells `pico-ioc`: "This class is part of the system. Scan its `__init__` method to find its dependencies, and make it available for injection into other components."

### Example

`@component` is the *only* thing you need. `pico-ioc` handles the rest.

```python
# database.py
@component
class Database:
    """A simple component with no dependencies."""
    def query(self, sql: str) -> dict:
        # ... logic to run query
        return {"data": "..."}

# user_service.py
@component
class UserService:
    """This component *depends* on the Database."""
    
    # pico-ioc will automatically inject the Database instance
    def __init__(self, db: Database):
        self.db = db

    def get_user(self, user_id: int) -> dict:
        return self.db.query(f"SELECT * FROM users WHERE id = {user_id}")
```

**When to use `@component`:**

  \* It's a class you wrote and can modify.
  \* The `__init__` method is all that's needed to create a valid instance.

-----

## 2\. When `@component` Isn't Enough

You **cannot** use `@component` when:

1.  **You don't own the class:** You can't add `@component` to `redis.Redis` from `redis-py` or `S3Client` from `boto3`.
2.  **Creation logic is complex:** You can't just call the constructor. You need to call a static method (like `redis.Redis.from_url(...)`) or run `if/else` logic first.
3.  **You are implementing a Protocol:** You want to register a *concrete class* as the provider for an *abstract protocol*.

For all these cases, you use the **Provider Pattern** with `@provides`.

-----

## 3\. `@provides`: The Provider Pattern

`@provides(SomeType)` decorates a *function* that acts as a "recipe" for building `SomeType`. `pico-ioc` offers three flexible ways to use it, ordered from simplest to most complex.

(The following examples assume you have a `config.py` module, as seen in the next guide).

### Pattern 1: Module-Level `@provides` (Simplest)

This is the simplest, lightest, and often-preferred method for registering a single third-party object or a component with complex logic.

You just write a function in any scanned module and decorate it.

```python
# factories.py
import redis
from pico_ioc import provides
from .config import RedisConfig # Assume this is a @configuration dataclass

# No factory class needed!
# This function is the "recipe" for building a redis.Redis client.
@provides(redis.Redis)
def build_redis_client(config: RedisConfig) -> redis.Redis:
    # Dependencies (RedisConfig) are injected into the function's arguments
    print(f"Connecting to Redis at {config.URL} from module function...")
    return redis.Redis.from_url(config.URL)
```

### Pattern 2: `staticmethod` in a `@factory` (Grouping)

If you have *many* stateless providers, you can group them logically inside a class decorated with `@factory`. Using `@staticmethod` tells `pico-ioc` that it doesn't need to create an *instance* of the factory class.

```python
# factories.py
import redis
import boto3
from pico_ioc import factory, provides
from .config import RedisConfig, S3Config

@factory
class ExternalClientsFactory:
    # No __init__ needed, as methods are static

    @staticmethod
    @provides(redis.Redis)
    def build_redis(config: RedisConfig) -> redis.Redis:
        print("Building Redis client from static method...")
        return redis.Redis.from_url(config.URL)

    @staticmethod
    @provides(boto3.client)
    def build_s3(config: S3Config) -> boto3.client:
        print("Building S3 client from static method...")
  s3_client = boto3.client("s3", aws_access_key_id=config.KEY)
        return s3_client
```

### Pattern 3: `@factory` Instance Method (Stateful)

Use this pattern when your providers need to share a common state or resource, such as a connection pool.

Here, the `@factory` class *is* instantiated, and its `__init__` dependencies are injected. The `@provides` methods can then use `self` to access that shared state.

```python
# factories.py
from pico_ioc import factory, provides
from .config import PoolConfig

# Assume these classes exist and share a pool
class ConnectionPool: ...
class UserClient: ...
class AdminClient: ...

@factory
class DatabaseClientFactory:
    # This factory IS stateful. It creates one pool
    # and shares it with all clients it builds.
    def __init__(self, config: PoolConfig):
        print("Creating shared ConnectionPool...")
        self.pool = ConnectionPool.create(config) # State is stored on 'self'

    @provides(UserClient)
    def build_user_client(self) -> UserClient:
        # Uses the shared state
        return UserClient(self.pool)

    @provides(AdminClient)
    def build_admin_client(self) -> AdminClient:
        # Also uses the shared state
        return AdminClient(self.pool)
```

-----

## 4\. Using the Injected Component

The best part: your consumer classes **do not care** how a component was registered. They just ask for the type they need.

This decouples your business logic from the creation logic.

```python
# cache_service.py
import redis
from pico_ioc import component

@component
class CacheService:
    # pico-ioc knows it needs a 'redis.Redis' instance.
    # It will find your 'build_redis_client' (from Pattern 1 or 2)
    # run it, and inject the result here.
    def __init__(self, redis_client: redis.Redis):
        self.redis_client = redis_client

    def set_value(self, key: str, value: str):
        self.redis_client.set(key, value)
```

-----

## Summary: When to Use What

| | `@component` | `@provides` (Module, Static, or Instance) |
| :--- | :--- | :--- |
| **What is it?** | A decorator for a class. | A decorator for a "recipe" function/method. |
| **Use Case** | **Your own classes** that you can modify. | **Third-party classes** or complex creation logic. |
| **Creation Logic** | Simple `__init__` call. | Simple: Module function.<br>Grouped: `staticmethod` on `@factory`.<br>Stateful: Instance method on `@factory`. |
| **Example** | `@component`<br>`class UserService:` | `@provides(redis.Redis)`<br>`def build_redis(...):` |

**Rule of Thumb:** Always default to `@component`. When you can't, use the simplest `@provides` pattern that fits your needs (start with module-level).

-----

## Next Steps

Now that you understand how to register components, the next logical step is to learn how to configure them properly.

   * **[Basic Configuration (`@configuration`)](./configuration-basic.m.d)**: Learn how to inject simple key-value settings from environment variables.

