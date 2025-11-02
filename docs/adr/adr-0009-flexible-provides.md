# ADR-0009: Flexible `@provides` for Module-level and Static Methods

**Status:** Accepted

## Context

In many DI frameworks, providers (methods that create components) are required to be *instance methods* on a dedicated factory class.

```python
# The "heavy" factory pattern
@factory
class ServiceFactory:
    def __init__(self, db: Database):
        self.db = db # Factory instance holds state

    @provides(Service)
    def build_service(self) -> Service:
        return Service(self.db) # Uses 'self'
```

While this pattern is powerful for providers that need shared state or configuration (from the factory's `__init__`), it creates unnecessary boilerplate for two common use cases:

1.  **Stateless Providers:** If a provider method doesn't depend on `self`, forcing the container to instantiate the factory class first is inefficient or unnecessary.
2.  **Simple Providers:** If a module only needs to provide one or two simple components, creating an entire `@factory` class just to host the `@provides` methods is verbose and adds a layer of indirection.

We needed a lighter-weight, more "Pythonic" way to declare simple providers.

## Decision

We decided to make the `@provides` decorator flexible, allowing it to be used in two additional contexts beyond just factory instance methods:

1.  **On regular, module-level functions:** The container discovers these functions during module scanning and treats them as direct providers. Dependencies are injected based on the function signature. This is the preferred method for simple, standalone providers.
2.  **On `@staticmethod` and `@classmethod` methods within a `@factory` class:** The container treats these as provider functions and injects dependencies from their signatures, without needing to instantiate the factory class (unless the factory *also* contains stateful instance-method providers).

### Example 1: Module-level function (Preferred for Simplicity)

This is the simplest pattern for a single provider.

```python
# services.py

@component
class Database: ...

# No factory class needed
@provides(Service)
def build_service(db: Database) -> Service:
    # Dependencies (Database) are injected directly
    return Service(db)
```

### Example 2: `staticmethod` (For Grouping Stateless Providers)

This is useful for grouping related, stateless providers in a `@factory` class namespace.

```python
@factory
class ClientFactory:
    @staticmethod
    @provides(S3Client)
    def build_s3(config: S3Config) -> S3Client:
        # Dependencies (S3Config) are injected into the static method
        return S3Client.from_config(config)

    @staticmethod
    @provides(RedisClient)
    def build_redis(config: RedisConfig) -> RedisClient:
        return RedisClient.from_url(config.url)
```

## Consequences

**Positive:** 👍

  * **Significantly Reduces Boilerplate:** Eliminates the need for a `@factory` class for simple cases (module-level functions).
  * **Improves Ergonomics:** Feels more natural to Python developers who are used to module-level helper functions.
  * **Clearer Code Structure:** Allows simple providers to live at the module level, while complex, stateful providers remain encapsulated in factory instances. Grouping stateless providers via `staticmethod` or `classmethod` is possible.

**Negative:** 👎

  * **Multiple Patterns:** Introduces multiple ways to register a provider (instance method, static/class method, module function). Requires clear documentation (`user-guide/core-concepts.md`) to guide users.

