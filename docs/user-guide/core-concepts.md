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
from pico_ioc import component # Assuming pico_ioc import

@component
class Database:
    """A simple component with no dependencies."""
    def query(self, sql: str) -> dict:
        # ... logic to run query
        print(f"DB: Executing query: {sql}")
        return {"data": "..."}

# user_service.py
# from pico_ioc import component # Assuming pico_ioc import
# from .database import Database # Assuming relative import

@component
class UserService:
    """This component *depends* on the Database."""
    
    # pico-ioc will automatically inject the Database instance
    def __init__(self, db: Database):
        self.db = db

    def get_user(self, user_id: int) -> dict:
        return self.db.query(f"SELECT * FROM users WHERE id = {user_id}")

# Example Usage (in main.py or similar)
# from pico_ioc import init
# container = init(modules=['database', 'user_service'])
# user_svc = container.get(UserService)
# user_data = user_svc.get_user(1)
# print(user_data)
```

**When to use `@component`:**

  * It's a class you wrote and can modify.
  * The `__init__` method is all that's needed to create a valid instance.

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

(The following examples assume you have a `config.py` module defining configuration dataclasses, as seen in the configuration guides).

### Pattern 1: Module-Level `@provides` (Simplest)

This is the simplest, lightest, and often-preferred method for registering a single third-party object or a component with complex logic.

You just write a function in any scanned module and decorate it.

```python
# factories.py or clients.py
import redis
from pico_ioc import provides
# Assume RedisConfig is a @configured dataclass defined elsewhere
from .config import RedisConfig

# No factory class needed!
# This function is the "recipe" for building a redis.Redis client.
@provides(redis.Redis)
def build_redis_client(config: RedisConfig) -> redis.Redis:
    # Dependencies (RedisConfig) are injected into the function's arguments
    print(f"Connecting to Redis at {config.URL} from module function...")
    # Assume RedisConfig has a URL attribute
    return redis.Redis.from_url(config.URL)
```

### Pattern 2: `staticmethod` or `classmethod` in a `@factory` (Grouping)

If you have *many* stateless providers, you can group them logically inside a class decorated with `@factory`. Using `@staticmethod` or `@classmethod` tells `pico-ioc` that it doesn't need to create an *instance* of the factory class itself.

```python
# factories.py
import redis
import boto3 # Assuming boto3 library
from pico_ioc import factory, provides
# Assume RedisConfig and S3Config are @configured dataclasses
from .config import RedisConfig, S3Config

# Assume S3Config has KEY and SECRET attributes
# Assume RedisConfig has URL attribute

@factory
class ExternalClientsFactory:
    # No __init__ needed, as methods are static

    @staticmethod
    @provides(redis.Redis)
    def build_redis(config: RedisConfig) -> redis.Redis:
        print("Building Redis client from static method...")
        return redis.Redis.from_url(config.URL)

    @classmethod
    @provides(boto3.client) # Providing the generic client function result
    def build_s3(cls, config: S3Config) -> 'boto3.client': # Type hint might need quotes or specific client type
        print(f"Building S3 client from class method {cls.__name__}...")
        # Example using boto3 client factory
        s3_client = boto3.client(
            "s3",
            aws_access_key_id=config.KEY,
            aws_secret_access_key=config.SECRET # Assuming SECRET attribute exists
        )
        return s3_client
```

### Pattern 3: `@factory` Instance Method (Stateful)

Use this pattern when your providers need to share a common state or resource, such as a connection pool managed by the factory instance.

Here, the `@factory` class *is* instantiated, and its `__init__` dependencies are injected. The `@provides` methods can then use `self` to access that shared state.

```python
# factories.py
from pico_ioc import factory, provides
# Assume PoolConfig is a @configured dataclass
from .config import PoolConfig

# Assume these classes exist and share a pool
class ConnectionPool:
    @staticmethod
    def create(config):
        print(f"Pool created with config: {config}")
        return ConnectionPool() # Return instance
    def get_connection(self):
        print("Getting connection from pool")
        return "fake_connection"

class UserClient:
    def __init__(self, pool): self.pool = pool; print("UserClient created")
    def do_user_stuff(self): conn = self.pool.get_connection(); print(f"UserClient using {conn}")

class AdminClient:
    def __init__(self, pool): self.pool = pool; print("AdminClient created")
    def do_admin_stuff(self): conn = self.pool.get_connection(); print(f"AdminClient using {conn}")

@factory
class DatabaseClientFactory:
    # This factory IS stateful. It creates one pool
    # and shares it with all clients it builds.
    def __init__(self, config: PoolConfig):
        print("Creating shared ConnectionPool...")
        # State (the pool) is stored on 'self'
        self.pool = ConnectionPool.create(config)

    @provides(UserClient)
    def build_user_client(self) -> UserClient:
        # Uses the shared state from 'self.pool'
        return UserClient(self.pool)

    @provides(AdminClient)
    def build_admin_client(self) -> AdminClient:
        # Also uses the shared state from 'self.pool'
        return AdminClient(self.pool)

# Example Config Dataclass (needed for the above)
# from dataclasses import dataclass
# from pico_ioc import configured
# @configured(prefix="DB_POOL_")
# @dataclass
# class PoolConfig:
#    MAX_SIZE: int = 10
```

-----

## 4\. Using the Injected Component

The best part: your consumer classes **do not care** how a component was registered (`@component` or `@provides`). They just ask for the type they need via constructor injection.

This decouples your business logic (the "what") from the creation logic (the "how").

```python
# cache_service.py
import redis
from pico_ioc import component

@component
class CacheService:
    # pico-ioc knows it needs a 'redis.Redis' instance.
    # It will find your 'build_redis_client' (from Pattern 1 or 2)
    # run it (injecting its dependencies like RedisConfig),
    # and inject the resulting redis.Redis instance here.
    def __init__(self, redis_client: redis.Redis):
        self.redis_client = redis_client
        print(f"CacheService initialized with Redis client: {redis_client}")

    def set_value(self, key: str, value: str):
        print(f"CacheService: Setting '{key}' to '{value}'")
        self.redis_client.set(key, value) # Assuming redis-py API
```

-----

## Summary: When to Use What

| Feature        | `@component`                                | `@provides` (Module, Static, or Instance)s       |
| :------------- | :------------------------------------------ | :----------------------------------------------- |
| **What is it?**| A decorator **for a class**.                | A decorator **for a "recipe" function/method**.  |
| **Use Case** | **Your own classes** that you can modify. Simple `__init__`. | **Third-party classes** or complex creation logic. |
| **Styles** | N/A                                         | Simple: Module function.<br>Grouped: `staticmethod` or `classmethod` on `@factory`.<br>Stateful: Instance method on `@factory`. |
| **Example** | `@component`<br>`class UserService:`        | `@provides(redis.Redis)`<br>`def build_redis(...):` |

**Rule of Thumb:** Always default to `@component`. When you can't, use the simplest `@provides` pattern that fits your needs (start with module-level functions).

-----

## Next Steps

Now that you understand how to register components, the next logical step is to learn how to configure them using the unified configuration system.

  * **[Configuration: Basic Concepts](./configuration-basic.md)**: Learn about the `configuration(...)` builder and how `pico-ioc` handles different sources.


