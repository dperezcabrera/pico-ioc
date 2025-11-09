# Advanced: Conditional Binding

In a real application, you don't always want the same set of components.
* In production, you want the real `PostgresDatabase`.
* In development, you might want a local `SqliteDatabase`.
* In testing, you want a completely fake `MockDatabase`.

`pico-ioc` allows you to define all of these implementations and then use conditional binding to control which one is active when you call `init()`.

This is handled by arguments you pass to your main decorators (`@component`, `@factory`, `@provides`):

1.  primary=True: The simplest. When multiple components implement one interface, this one is the default choice.
2.  on_missing_selector=...: A fallback. This component only registers if no other implementation is found.
3.  conditional_*: The most powerful. This component only registers if rules (based on profiles, environment variables, or custom functions) are met.

The same arguments work for components, factories, and provider methods.

---

## 1. primary=True: The "Default" Choice

Problem: You have one interface and multiple implementations. If a component just asks for the interface, how does `pico-ioc` know which one to inject?

```python
from typing import Protocol
from pico_ioc import component

class Database(Protocol): ...

@component
class PostgresDatabase(Database): ...

@component
class SqliteDatabase(Database): ...

@component
class UserService:
    def __init__(self, db: Database):
        # Which one does 'db' get? Postgres or Sqlite?
        self.db = db
```

This causes an `InvalidBindingError` at startup because `pico-ioc` sees the ambiguity.

Solution: Use primary=True to mark one implementation as the default.

```python
from typing import Protocol
from pico_ioc import component

class Database(Protocol): ...

@component(primary=True)  # <-- This is the default
class PostgresDatabase(Database): ...

@component
class SqliteDatabase(Database): ...

@component
class UserService:
    def __init__(self, db: Database):
        # 'db' will now receive PostgresDatabase
        self.db = db
```

-----

## 2. on_missing_selector: The "Fallback" Choice

Problem: You want to provide a sensible default (like an in-memory cache) that is only used if no real implementation (like `RedisCache`) is registered. This is perfect for testing or development.

Solution: Use on_missing_selector. This argument registers a component only if no other component is registered for its key (or a type it implements).

Let's see how this works with profiles, which we covered in the Testing Guide.

### Step 1: Define the "Real" and "Fallback" Components

```python
# cache.py
from typing import Protocol
from pico_ioc import component

class Cache(Protocol): ...

# Use the 'conditional_profiles' parameter directly in @component
@component(conditional_profiles=("prod",))  # <-- Only active in "prod"
class RedisCache(Cache):
    ...
    print("Real RedisCache registered")

@component(on_missing_selector=Cache)  # <-- Activates if no other 'Cache' is found
class InMemoryCache(Cache):
    ...
    print("Fallback InMemoryCache registered")
```

### Step 2: Initialize with Different Profiles

Now, watch what happens when we change the profiles tuple during init().

#### Production Environment:

```python
from pico_ioc import init

# init(profiles=("prod",))
container = init(modules=["cache"], profiles=("prod",))
cache = container.get(Cache)

# Output:
# Real RedisCache registered
# (InMemoryCache is never registered)
```

In this case, `RedisCache` is registered first. When `pico-ioc` checks `InMemoryCache`, it sees that a `Cache` component already exists, so on_missing_selector causes it to be skipped.

#### Test/Dev Environment:

```python
from pico_ioc import init

# init(profiles=("test",))
container = init(modules=["cache"], profiles=("test",))
cache = container.get(Cache)

# Output:
# Fallback InMemoryCache registered
```

In this case, `RedisCache` is skipped (its conditional_profiles check fails). When `pico-ioc` checks `InMemoryCache`, it sees that no other `Cache` component exists, so on_missing_selector allows it to be registered.

For more on profiles, see the Testing Guide: ../user-guide/testing.md

-----

## 3. conditional_* Arguments: The "Rules-Based" Choice

This is the most powerful set of arguments. They let you register a component based on a set of rules. All specified conditions must be true:

- conditional_profiles: Tuple[str, ...]
- conditional_require_env: Tuple[str, ...]
- conditional_predicate: Callable[[], bool]

### Example 1: Conditional on Profile

The component is only registered if one of the listed profiles is active.

```python
from pico_ioc import component

@component(conditional_profiles=("prod", "staging"))
class RealPaymentService:
    ...
```

- init(profiles=("prod",)) will register this.
- init(profiles=("dev",)) will not.

### Example 2: Conditional on Environment Variable

The component is only registered if the environment variable exists and is not empty or None.

```python
from pico_ioc import component

@component(conditional_require_env=("ENABLE_BETA_FEATURES",))
class BetaFeatureService:
    ...
```

This service will only be registered if you run your app with, for example:
ENABLE_BETA_FEATURES=true python app.py

### Example 3: Conditional on Predicate

You can provide a custom function. The component is only registered if the function returns True.

```python
import os
from pico_ioc import component

def is_analytics_enabled():
    # You can run any complex logic here
    return os.environ.get("ANALYTICS_KEY") is not None

@component(conditional_predicate=is_analytics_enabled)
class AnalyticsService:
    ...
```

### Example 4: Combining All Rules

You can combine all rules. The component is only registered if all conditions are met.

```python
from pico_ioc import component

def is_stripe_enabled() -> bool:
    # your custom logic here
    return True

@component(
    conditional_profiles=("prod",),
    conditional_require_env=("STRIPE_API_KEY",),
    conditional_predicate=is_stripe_enabled,
)
class StripePaymentProvider:
    ...
```

This component will only be registered if:
1) The active profile is "prod" AND
2) The STRIPE_API_KEY environment variable is set AND
3) The is_stripe_enabled() function returns True.

-----

## Notes and Tips

- These arguments also work with @factory and @provides. You can make factory-produced or provider-produced beans conditional in the same way.
- Environment and predicate checks are evaluated during init(). If you change environment variables after init(), they won’t affect already-built containers.
- If multiple implementations are eligible, use primary=True to choose the default. If none are eligible, you’ll get an InvalidBindingError when something depends on that type.

-----

## Next Steps

You've now seen how to control your application's architecture based on its environment. The final piece of the advanced puzzle is monitoring your application's health.

- Health Checks: Learn how to use the @health decorator to create a simple, aggregated health report for your application. See ./health-checks.md
