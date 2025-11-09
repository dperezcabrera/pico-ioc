# ADR-0009: Flexible `@provides` for Module-level and Static/Class Methods

Status: Accepted

## Context

In many DI frameworks, providers (methods that create components) are required to be instance methods on a dedicated factory class.

```python
# The "heavy" factory pattern
@factory
class ServiceFactory:
    def __init__(self, db: Database):
        self.db = db  # Factory instance holds state

    @provides(Service)
    def build_service(self) -> Service:
        return Service(self.db)  # Uses 'self'
```

While this pattern is powerful for providers that need shared state or configuration (from the factory's `__init__`), it creates unnecessary boilerplate for two common use cases:

1. Stateless providers: If a provider method doesn't depend on `self`, forcing the container to instantiate the factory class first is inefficient or unnecessary.
2. Simple providers: If a module only needs to provide one or two simple components, creating an entire `@factory` class just to host the `@provides` methods is verbose and adds a layer of indirection.

We needed a lighter-weight, more Pythonic way to declare simple providers.

## Decision

The `@provides` decorator is now flexible and supported in the following contexts beyond factory instance methods:

1. Module-level functions: The container discovers these functions during module scanning and treats them as direct providers. Dependencies are injected based on the function signature. This is the preferred method for simple, standalone providers.
2. `@staticmethod` and `@classmethod` within a `@factory` class: The container treats these as provider functions and injects dependencies from their signatures, without needing to instantiate the factory class (unless the factory also contains stateful instance-method providers).

### Rules and Constraints

- Providers must be importable symbols at module load time (not nested or dynamically defined).
- Dependencies are resolved by type hints on parameters. The first parameter of `@classmethod` (`cls`) is not considered a dependency; the same applies to `self` for instance methods and no implicit parameter for `@staticmethod`.
- The declared component in `@provides(ComponentType)` must match the function’s return type annotation. A mismatch results in a configuration error.
- Static/class method providers do not require instantiating the factory. If a factory also declares instance-method providers, the container may instantiate the factory only when those stateful providers are needed.
- Providers should be side-effect free and deterministic. Shared state should be handled via instance-method providers on a factory.

## Examples

### Example 1: Module-level function (Preferred for simplicity)

This is the simplest pattern for a single provider.

```python
# services.py

@component
class Database:
    ...

@component
class Service:
    def __init__(self, db: Database):
        self.db = db

# No factory class needed
@provides(Service)
def build_service(db: Database) -> Service:
    # Dependencies (Database) are injected directly
    return Service(db)
```

### Example 2: `staticmethod` (Grouping stateless providers)

Useful for grouping related, stateless providers in a `@factory` namespace.

```python
@component
class S3Client:
    @staticmethod
    def from_config(config: "S3Config") -> "S3Client":
        ...

@component
class RedisClient:
    @staticmethod
    def from_url(url: str) -> "RedisClient":
        ...

@component
class S3Config:
    ...

@component
class RedisConfig:
    def __init__(self, url: str):
        self.url = url

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

### Example 3: `classmethod` (When class context is useful)

A `@classmethod` is treated similarly to a static method for dependency injection; the `cls` parameter is not injected.

```python
@component
class TokenSigner:
    @classmethod
    def from_settings(cls, settings: "SignerSettings") -> "TokenSigner":
        ...

@component
class SignerSettings:
    ...

@factory
class SecurityFactory:
    @classmethod
    @provides(TokenSigner)
    def signer(cls, settings: SignerSettings) -> TokenSigner:
        # 'cls' is the factory class; not a dependency
        return TokenSigner.from_settings(settings)
```

## Migration Guidance

- If an existing provider does not use `self`, convert it to a module-level function or a static/class method within a `@factory` to remove unnecessary instantiation:

```python
# Before: instance method provider that doesn't use self
@factory
class ServiceFactory:
    @provides(Service)
    def build_service(self, db: Database) -> Service:
        return Service(db)

# After: module-level function provider
@provides(Service)
def build_service(db: Database) -> Service:
    return Service(db)
```

- Keep instance-method providers for cases where you need shared state in the factory (e.g., configuration loaded in `__init__`, caches, or coordination across providers).

## Consequences

Positive:
- Significantly reduces boilerplate: Eliminates the need for a `@factory` class for simple cases (module-level functions).
- Improves ergonomics: Feels more natural to Python developers who are used to module-level helper functions.
- Clearer code structure: Allows simple providers to live at the module level, while complex, stateful providers remain encapsulated in factory instances. Grouping stateless providers via `staticmethod` or `classmethod` is possible.
- More flexible discovery: Providers can be organized by module or by factory class without forcing instantiation.

Negative:
- Multiple patterns: Introduces multiple ways to register a provider (instance method, static/class method, module function). Requires clear documentation in the user guide to guide users.
- Potential inconsistency: Teams must adopt conventions to avoid mixing styles arbitrarily within the same module.
- Validation complexity: Type-hint mismatches or mis-declared return types can lead to configuration errors that need clear diagnostics.
