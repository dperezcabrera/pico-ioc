# Pico-IoC Documentation

`pico-ioc` is a lightweight, async-native Inversion of Control (IoC) container for Python 3.11+. It brings enterprise-grade dependency injection, configuration binding, and AOP to the Python ecosystem.

---

## Quick Install

```bash
pip install pico-ioc

# Optional: YAML configuration support
pip install pico-ioc[yaml]
```

---

## 30-Second Example

```python
from pico_ioc import component, init

@component
class Database:
    def query(self) -> str:
        return "data from DB"

@component
class UserService:
    def __init__(self, db: Database):  # Auto-injected
        self.db = db

    def get_users(self) -> str:
        return self.db.query()

# Initialize and use
container = init(modules=[__name__])
service = container.get(UserService)
print(service.get_users())  # "data from DB"
```

---

## Key Features

| Feature | Description |
|---------|-------------|
| **Async-Native** | Full `async`/`await` support: `aget()`, `__ainit__`, async `@cleanup` |
| **Unified Configuration** | `@configured` maps ENV vars or YAML/JSON to dataclasses |
| **Fail-Fast Validation** | All wiring errors detected at `init()`, not runtime |
| **AOP Interceptors** | `@intercepted_by` for logging, caching, security |
| **Scoped Lifecycles** | singleton, prototype, request, session, transaction |
| **Observable** | Built-in stats, health checks, dependency graph export |

---

## Documentation Structure

| # | Section | Description | Link |
|---|---------|-------------|------|
| 1 | **Getting Started** | 5-minute tutorial | [getting-started.md](./getting-started.md) |
| 2 | **User Guide** | Core concepts, configuration, scopes, testing | [user-guide/](./user-guide/README.md) |
| 3 | **Advanced Features** | Async, AOP, Event Bus, conditional binding | [advanced-features/](./advanced-features/README.md) |
| 4 | **Observability** | Metrics, tracing, graph export | [observability/](./observability/README.md) |
| 5 | **Cookbook** | Real-world patterns (multi-tenant, CQRS, etc.) | [cookbook/](./cookbook/README.md) |
| 6 | **Architecture** | Design principles, internals | [architecture/](./architecture/README.md) |
| 7 | **API Reference** | Decorators, exceptions, protocols | [api-reference/](./api-reference/README.md) |
| 8 | **FAQ** | Common questions and solutions | [faq.md](./faq.md) |
| 9 | **Troubleshooting** | Symptom-first debugging guide | [troubleshooting.md](./troubleshooting.md) |
| 10 | **Examples** | Complete runnable applications | [examples/](./examples/README.md) |
| 11 | **Learning Roadmap** | Step-by-step path from zero to advanced | [LEARN.md](./LEARN.md) |

---

## Core APIs at a Glance

### Registration

```python
from pico_ioc import component, factory, provides

@component                    # Register a class
class MyService: ...

@factory                      # Group related providers
class ClientFactory:
    @provides(RedisClient)    # Provide third-party types
    def build_redis(self, config: RedisConfig) -> RedisClient:
        return RedisClient(config.url)
```

### Configuration

```python
from dataclasses import dataclass
from pico_ioc import configured, configuration, init

@configured(prefix="DB_")
@dataclass
class DBConfig:
    host: str = "localhost"
    port: int = 5432

container = init(
    modules=[__name__],
    config=configuration()  # Reads from ENV: DB_HOST, DB_PORT
)
```

### Async Support

```python
@component
class AsyncService:
    async def __ainit__(self):
        self.conn = await open_connection()

    @cleanup
    async def close(self):
        await self.conn.close()

# Resolve async components
service = await container.aget(AsyncService)

# Cleanup
await container.ashutdown()
```

### Testing with Overrides

```python
container = init(
    modules=[__name__],
    overrides={Database: FakeDatabase()}  # Replace for tests
)
```

---

## Next Steps

1. **New to pico-ioc?** Start with the [Getting Started](./getting-started.md) tutorial
2. **Learning from scratch?** Follow the [Learning Roadmap](./LEARN.md) from zero to advanced
3. **Coming from Spring/Guice?** Check the [Architecture Comparison](./architecture/comparison.md)
4. **Building a real app?** See the [Cookbook](./cookbook/README.md) patterns
