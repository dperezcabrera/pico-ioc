# Core Concepts: @component, @factory, @provides

To inject an object (a "component"), `pico-ioc` first needs to know how to create it. This is called **registration**.

There are two primary ways to register a component. Your choice depends on one simple question: **"Do I own the code for this class?"**

1.  **`@component`**: The default choice. You use this decorator **on your own classes**.
2.  **`@factory` / `@provides`**: The factory pattern. You use this to register **third-party classes** (which you can't decorate) or for any object that requires complex creation logic.

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
````

**When to use `@component`:**

  * It's a class you wrote and can modify.
  * The `__init__` method is all that's needed to create a valid instance.

-----

## 2\. The Problem: When `@component` Isn't Enough

You **cannot** use `@component` when:

1.  **You don't own the class:** You can't add `@component` to `redis.Redis` from `redis-py` or `S3Client` from `boto3`.
2.  **Creation logic is complex:** You can't just call the constructor. You need to call a static method (like `redis.Redis.from_url(...)`) or run `if/else` logic first.
3.  **You are implementing a Protocol:** You want to register a *concrete class* as the provider for an *abstract protocol*.

For all these cases, you use the **Factory Pattern**.

-----

## 3\. `@factory` and `@provides`: The Factory Pattern

This pattern splits the creation logic into its own class.

  * `@factory`: Decorates a class whose *job* is to build other objects. The factory itself becomes a component and can have its own dependencies injected (like configuration).
  * `@provides(SomeType)`: Decorates a *method* inside the factory. It tells `pico-ioc`: "When someone asks for `SomeType`, run this method to get the instance."

### Example: Registering a Third-Party Client

Let's solve the problem of registering a `redis.Redis` client.

#### Step 1: Define the Configuration

First, we'll need a configuration object for the Redis URL (we'll cover `@configuration` in the next guide, but the concept is simple).

```python
# config.py
from dataclasses import dataclass
from pico_ioc import configuration

@configuration(prefix="REDIS_")
@dataclass
class RedisConfig:
    URL: str
```

#### Step 2: Create the Factory

Next, we create a factory. This factory *depends* on the `RedisConfig` and *provides* the `redis.Redis` instance.

```python
# factories.py
import redis
from pico_ioc import factory, provides
from .config import RedisConfig

@factory
class ExternalClientsFactory:

    # The factory itself can have dependencies,
    # just like any other component.
    def __init__(self, config: RedisConfig):
        self.redis_url = config.URL

    # This method is the "recipe" for building a redis.Redis client
    @provides(redis.Redis)
    def build_redis_client(self) -> redis.Redis:
        # Here we can run complex logic
        print(f"Connecting to Redis at {self.redis_url}...")
        return redis.Redis.from_url(self.redis_url)
```

#### Step 3: Use the Injected Component

Now, any other component can simply ask for `redis.Redis` by its type. `pico-ioc` knows to use your factory method to build it.

```python
# cache_service.py
import redis
from pico_ioc import component

@component
class CacheService:

    # pico-ioc knows it needs a redis.Redis instance.
    # It will find your 'build_redis_client' method,
    # run it, and inject the result here.
    def __init__(self, redis_client: redis.Redis):
        self.redis_client = redis_client

    def set_value(self, key: str, value: str):
        self.redis_client.set(key, value)
```

When you call `container.get(CacheService)`, `pico-ioc` will automatically:

1.  See `CacheService` needs `redis.Redis`.
2.  Find `@provides(redis.Redis)` on the `build_redis_client` method.
3.  See that it must build `ExternalClientsFactory` first.
4.  See that `ExternalClientsFactory` needs `RedisConfig`.
5.  Build `RedisConfig` (from environment variables).
6.  Build `ExternalClientsFactory` (injecting `RedisConfig`).
7.  Call `build_redis_client()` to get the `redis.Redis` instance.
8.  Build `CacheService` (injecting the `redis.Redis` instance).

-----

## Summary: When to Use What

| | `@component` | `@factory` / `@provides` |
| :--- | :--- | :--- |
| **What is it?** | A decorator for a class. | Decorators for a "builder" class and its methods. |
| **Use Case** | **Your own classes** that you can modify. | **Third-party classes** you can't modify. |
| **Creation Logic** | Simple `__init__` call. | Complex logic (e.g., `if/else`, static methods). |
| **Example** | `@component`<br>`class UserService:` | `@factory`<br>`class ClientFactory:`<br>    `@provides(boto3.S3Client)`<br>    `def build_s3(...):` |

**Rule of Thumb:** Always default to `@component`. Only use `@factory` when you have a specific reason to.

-----

## Next Steps

Now that you understand how to register components, the next logical step is to learn how to configure them properly.

  * **[Basic Configuration (`@configuration`)](./configuration-basic.md)**: Learn how to inject simple key-value settings from environment variables.

<!-- end list -->

