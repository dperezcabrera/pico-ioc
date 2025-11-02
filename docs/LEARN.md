🗺️ Learning Roadmap: pico-ioc from Scratch
🎯 Objective
Learn Dependency Injection and master pico-ioc step-by-step, from fundamentals to advanced patterns.
📊 Roadmap Overview
graph TD
    A[Level 0: Python Basics] --> B[Level 1: What is DI?]
    B --> C[Level 2: First Steps with pico-ioc]
    C --> D[Level 3: Configuration]
    D --> E[Level 4: Lifecycles]
    E --> F[Level 5: Testing]
    F --> G[Level 6: Advanced Features]
    G --> H[Level 7: Architecture Patterns]

---
🚀 Level 0: Prerequisites
What you need to know before starting:
✅ Basic Python (version 3.10+)

# 1. Classes and inheritance
class Animal:
    def __init__(self, name: str):
        self.name = name
    
    def speak(self):
        pass

class Dog(Animal):
    def speak(self):
        return f"{self.name} says: Woof!"

# 2. Type hints (CRITICAL for DI)
def greet(name: str) -> str:
    return f"Hello, {name}"

# 3. Basic decorators
def my_decorator(func):
    def wrapper(*args, **kwargs):
        print("Before the function")
        result = func(*args, **kwargs)
        print("After the function")
        return result
    return wrapper

@my_decorator
def say_hello():
    print("Hello!")
📚 Resources if you need a review:

* Type hints: https://docs.python.org/3/library/typing.html
* Decorators: https://realpython.com/primer-on-python-decorators/
🎯 Checkpoint: If you understand the code above, you're ready!

---

🔰 Level 1: Understand the Problem DI Solves

Step 1.1: The Coupling Problem
❌ Bad Code (No DI)
```python
# database.py
class Database:
    def __init__(self):
        print("Connecting to PostgreSQL in production...")
        self.connection = "postgresql://prod-server/db"
    
    def query(self, sql: str):
        print(f"Executing: {sql}")
        return [{"id": 1, "name": "Juan"}]

# user_service.py
from database import Database

class UserService:
    def __init__(self):
        # ⚠️ PROBLEM 1: Direct creation = coupling
        self.db = Database()  
    
    def get_user(self, user_id: int):
        # ⚠️ PROBLEM 2: Always uses the real DB
        return self.db.query(f"SELECT * FROM users WHERE id={user_id}")

# main.py
from user_service import UserService

service = UserService()  # ⚠️ PROBLEM 3: Impossible to test without a real DB
user = service.get_user(1)
```

Problems identified:

❌ `UserService` creates its own `Database` → strong coupling
❌ You can't change the DB without modifying `UserService`
❌ Impossible to test with a fake DB (mock)
❌ Hard to reuse in different environments (dev, test, prod)
Step 1.2: Manual Solution (Constructor Injection)
✅ Improved Code (Manual DI)

```python
# database.py
from typing import Protocol

class Database(Protocol):
    def query(self, sql: str): ...

class PostgresDB(Database):
    def __init__(self):
        print("Connecting to PostgreSQL...")
        self.connection = "postgresql://server/db"
    
    def query(self, sql: str):
        print(f"Postgres: {sql}")
        return [{"id": 1}]

class MockDB(Database):
    def query(self, sql: str):
        print(f"Mock: {sql}")
        return [{"id": 999, "name": "Test User"}]

# user_service.py
from database import Database

class UserService:
    def __init__(self, db: Database):  # ✅ Receives the dependency
        self.db = db
    
    def get_user(self, user_id: int):
        return self.db.query(f"SELECT * FROM users WHERE id={user_id}")

# main.py (PRODUCTION)
from user_service import UserService
from database import PostgresDB

real_db = PostgresDB()
service = UserService(db=real_db)  # ✅ Manual injection
user = service.get_user(1)

# test.py (TESTING)
from user_service import UserService
from database import MockDB

mock_db = MockDB()
service = UserService(db=mock_db)  # ✅ Mock injection
user = service.get_user(1)  # Now it's testable!
```

✅ Improvements achieved:

✅ `UserService` doesn't know the concrete DB implementation
✅ You can change the DB without touching `UserService`
✅ Testable with mocks
✅ Reusable in any environment
❌ New problem:

If `UserService` has 5 dependencies, and each has 3 more → manual nightmare
Step 1.3: The "Container" Concept
🤔 What is a DI Container?
A container is a "robot" that:

📦 Stores recipes on how to create objects
🔍 Reads dependencies automatically (via type hints)
🏗️ Builds the entire object graph for you
💾 Caches instances (singleton pattern)
Analogy:

You without a container:
"I need `UserService`"
→ First I create `Database`
→ `Database` needs `ConnectionPool`
→ `ConnectionPool` needs `Config`
→ `Config` needs to read a file...
→ Then I create `Cache`
→ `Cache` needs...
→ FINALLY I create `UserService` with all that

You with a container:
`container.get(UserService)`  \# 🎉 Done\!
🎯 Practical Exercise:

1.  Copy the "Improved Code" from above
2.  Run `main.py` and `test.py`
3.  Add a third dependency to `UserService` (e.g., `Logger`)
4.  See how it gets complicated? → That's the problem pico-ioc solves

-----

🌱 Level 2: First Steps with pico-ioc
Step 2.1: Installation and "Hello World"

```bash
pip install pico-ioc
```

Your first DI program:

```python
# hello.py
from pico_ioc import component, init

@component  # 🎯 This says "I am a component"
class Greeter:
    def greet(self, name: str) -> str:
        return f"Hello, {name}!"

@component
class App:
    # 🎯 pico-ioc sees the type hint and auto-injects Greeter
    def __init__(self, greeter: Greeter):
        self.greeter = greeter
    
    def run(self):
        print(self.greeter.greet("World"))

# 🎯 Scans this file and finds @component
container = init(modules=[__name__])

# 🎯 Ask for App, and pico-ioc builds the whole graph
app = container.get(App)
app.run()
```

Output:

```
Hello, World!
```

🧠 New concepts:

  * **`@component`**: Marks a class as "manageable by the container"
  * **`init(modules=[...])`**: Scans modules looking for `@component`
  * **`container.get(Class)`**: "Give me an instance of Class (with its dependencies)"
    🎯 Exercises:

✏️ Change `Greeter` to greet in Spanish
✏️ Add a `@component` `class Logger` for `Greeter` to use
✏️ Create a `@component` `class Database` and use it in `App`
Step 2.2: Registering Third-Party Classes with @provides
Problem: You can't decorate `redis.Redis` or `requests.Session` with `@component`.
Solution: Use `@provides` to create a "recipe".

```python
# services.py
import redis
from dataclasses import dataclass
from pico_ioc import component, provides, init

# 🎯 Option 1: Simple function (most common)
@provides(redis.Redis)
def create_redis() -> redis.Redis:
    print("Creating Redis client...")
    return redis.Redis.from_url("redis://localhost")

# 🎯 Option 2: With configuration
@dataclass
class RedisConfig:
    url: str = "redis://localhost"
    port: int = 6379

@provides(redis.Redis)
def create_redis_with_config(config: RedisConfig) -> redis.Redis:
    # ✅ pico-ioc also injects 'config' automatically
    return redis.Redis.from_url(config.url)

@component
class CacheService:
    def __init__(self, redis: redis.Redis):  # ✅ Receives the Redis
        self.redis = redis
    
    def set(self, key: str, value: str):
        print(f"Saving {key}={value} in cache")
        self.redis.set(key, value)

# Initialize
container = init(modules=[__name__])
cache = container.get(CacheService)
cache.set("user:1", "Juan")
```

🧠 New concepts:

  * **`@provides(Type)`**: Creates a function that "provides" instances of `Type`
  * `@provides` functions also receive dependency injection
    🎯 Exercises:

✏️ Create a `@provides` for `requests.Session`
✏️ Make `Session` receive a timeout from a config
✏️ Use it in a `@component` `class ApiClient`


Step 2.3: Multiple Implementations (Interfaces)
Problem: You have `Database`, `PostgresDB`, and `MockDB`. How does pico-ioc choose which one to use?

```python
# databases.py
from typing import Protocol
from pico_ioc import component, init

# 🎯 Protocol (like an interface)
class Database(Protocol):
    def query(self, sql: str) -> list: ...

@component
class PostgresDB(Database):
    def query(self, sql: str) -> list:
        print(f"PostgreSQL: {sql}")
        return [{"id": 1}]

@component
class MockDB(Database):
    def query(self, sql: str) -> list:
        print(f"Mock: {sql}")
        return [{"id": 999}]

@component
class UserService:
    def __init__(self, db: Database):  # ⚠️ Asks for Database (interface)
        self.db = db

# ❌ THIS FAILS: "Ambiguous, there are 2 Databases!"
# container = init(modules=[__name__])
# service = container.get(UserService)
```

Solution 1: Use `primary=True`

```python
@component(primary=True)  # 🎯 "This is the default"
class PostgresDB(Database):
    ...

@component  # This is secondary
class MockDB(Database):
    ...

container = init(modules=[__name__])
service = container.get(UserService)  # ✅ Uses PostgresDB
```

Solution 2: Use `profiles` (we'll see this in Level 5)
🎯 Exercise:

✏️ Create `EmailSender` (interface) with `SmtpSender` and `ConsoleSender`
✏️ Mark `SmtpSender` as `primary=True`
✏️ Use it in a `@component` `class NotificationService`
🏆 Level 2 Checkpoint
You should be able to:

✅ Use `@component` for your classes
✅ Use `@provides` for third-party classes
✅ Resolve conflicts with `primary=True`
✅ Understand that the container auto-injects dependencies
📊 Quick Quiz:

```python
# What happens here?
@component
class A:
    def __init__(self, b: B): ...

@component
class B:
    def __init__(self, c: C): ...

@component
class C:
    pass

container = init(modules=[__name__])
a = container.get(A)
```

> Answer: pico-ioc creates `C` → `B` → `A` automatically

-----

⚙️ Level 3: Configuration
Step 3.1: Simple Environment Variables
Scenario: Your app needs `DB_HOST`, `DB_PORT`, `API_KEY` from the environment.

```python
# config.py
import os
from dataclasses import dataclass
from pico_ioc import configured, configuration, EnvSource, init

# 🎯 Option 1: Automatic mapping from ENV
@configured(prefix="APP_", mapping="auto")
@dataclass
class AppConfig:
    DB_HOST: str      # Reads APP_DB_HOST
    DB_PORT: int      # Reads APP_DB_PORT (converts to int!)
    API_KEY: str      # Reads APP_API_KEY
    DEBUG: bool = False  # Reads APP_DEBUG (optional with default)

# Create configuration context
ctx = configuration(
    EnvSource(prefix="")  # Reads environment variables
)

# Initialize container with config
container = init(modules=[__name__], config=ctx)

# Use
config = container.get(AppConfig)
print(f"DB: {config.DB_HOST}:{config.DB_PORT}")
print(f"Debug mode: {config.DEBUG}")
```

Run:

```bash
export APP_DB_HOST="localhost"
export APP_DB_PORT="5432"
export APP_API_KEY="secret123"
export APP_DEBUG="true"
python config.py
```

Output:

```
DB: localhost:5432
Debug mode: True
```

🎯 Exercises:

✏️ Add `REDIS_URL` and `REDIS_TIMEOUT` to the config
✏️ Create a `@component` `class RedisClient` that uses `AppConfig`
✏️ Test with different ENV values
Step 3.2: YAML Files (Complex Configuration)
Scenario: Hierarchical configuration (database, cache, external APIs).
`config.yml`:

```yaml
app:
  name: "My App"
  debug: true
  
database:
  host: "localhost"
  port: 5432
  credentials:
    username: "admin"
    password: "secret"
    
cache:
  type: "redis"
  url: "redis://localhost"
  ttl: 3600
```

`config.py`:

```python
# config.py
from dataclasses import dataclass
from pico_ioc import configured, configuration, YamlTreeSource, init

@dataclass
class Credentials:
    username: str
    password: str

@dataclass
class DatabaseConfig:
    host: str
    port: int
    credentials: Credentials

@dataclass
class CacheConfig:
    type: str
    url: str
    ttl: int

# 🎯 Mapping from YAML (automatic!)
@configured(prefix="app", mapping="auto")
@dataclass
class AppSettings:
    name: str
    debug: bool

@configured(prefix="database", mapping="auto")
@dataclass
class DbSettings:
    host: str
    port: int
    credentials: Credentials

# Create context
ctx = configuration(
    YamlTreeSource("config.yml")
)

container = init(modules=[__name__], config=ctx)

# Use
app = container.get(AppSettings)
db = container.get(DbSettings)

print(f"App: {app.name} (debug={app.debug})")
print(f"DB: {db.host}:{db.port}")
print(f"User: {db.credentials.username}")
```

🎯 Exercises:

✏️ Add an `email` section to the YAML with `smtp_server`, `port`
✏️ Create `@configured` `class EmailConfig`
✏️ Use it in a `@component` `class EmailService`
Step 3.3: Combining Sources (ENV + YAML)
Scenario: YAML for base config, ENV for secrets.
`base.yml`:

```yaml
database:
  host: "localhost"
  port: 5432
  # password is NOT here (it's a secret!)
```

`config.py`:

```python
# config.py
from dataclasses import dataclass
from typing import Annotated
from pico_ioc import configured, configuration, YamlTreeSource, EnvSource, Value, init

@dataclass
class DbConfig:
    host: str
    port: int
    password: str  # Will come from ENV

@configured(prefix="database", mapping="auto")
@dataclass
class Settings:
    host: str
    port: int
    # 🎯 This field ALWAYS comes from ENV (highest priority)
    password: Annotated[str, Value("${ENV:DB_PASSWORD}")]

# Context with multiple sources (order = priority)
ctx = configuration(
    YamlTreeSource("base.yml"),  # Base
    EnvSource(prefix=""),         # Overwrites/adds
)

container = init(modules=[__name__], config=ctx)
settings = container.get(Settings)
print(f"DB Password: {settings.password}")
```

Run:

```bash
export DB_PASSWORD="super_secret"
python config.py
```

Output:

```
DB Password: super_secret
```

🎯 Exercise:

✏️ Create `secrets.yml` with `api_keys`
✏️ Override a key from ENV
✏️ Use `Value()` to force a value
🏆 Level 3 Checkpoint
You should be able to:

## ✅ Map ENV vars to dataclasses ✅ Use YAML for hierarchical config ✅ Combine multiple sources ✅ Understand precedence (`Value` \> overrides \> sources)

🔄 Level 4: Lifecycles and Scopes
Step 4.1: Scopes (Singleton vs Prototype)

```python
# scopes.py
from pico_ioc import component, init

# 🎯 Singleton (default): One instance forever
@component(scope="singleton")
class DatabaseConnection:
    def __init__(self):
        print("🔌 Connecting to DB...")
        self.connection_id = id(self)

# 🎯 Prototype: New instance every time
@component(scope="prototype")
class RequestHandler:
    def __init__(self):
        print("📝 Creating handler...")
        self.handler_id = id(self)

container = init(modules=[__name__])

# Singleton: Same instance
db1 = container.get(DatabaseConnection)  # 🔌 Connecting...
db2 = container.get(DatabaseConnection)  # (no output, uses cache)
print(f"Same DB? {db1.connection_id == db2.connection_id}")  # True

# Prototype: Always new
req1 = container.get(RequestHandler)  # 📝 Creating...
req2 = container.get(RequestHandler)  # 📝 Creating...
print(f"Same handler? {req1.handler_id == req2.handler_id}")  # False
```

🎯 Exercises:

✏️ Create a `Logger` singleton
✏️ Create a `Report` prototype
✏️ Verify with `id()` that they work as expected
Step 4.2: Lifecycle Hooks (@configure and @cleanup)

```python
# lifecycle.py
from pico_ioc import component, configure, cleanup, init
import asyncio

@component
class Database:
    def __init__(self):
        print("1️⃣ __init__: Object created")
        self.connected = False
    
    @configure  # 🎯 Runs AFTER __init__
    def setup(self):
        print("2️⃣ @configure: Initializing connection...")
        self.connected = True
    
    @cleanup  # 🎯 Runs on shutdown
    def teardown(self):
        print("3️⃣ @cleanup: Closing connection...")
        self.connected = False

@component
class AsyncDatabase:
    async def __ainit__(self):  # 🎯 Async init
        print("⏳ Connecting async...")
        await asyncio.sleep(0.1)
        print("✅ Connected!")
    
    @cleanup
    async def close(self):  # 🎯 Async cleanup
        print("⏳ Disconnecting async...")
        await asyncio.sleep(0.1)
        print("✅ Disconnected!")

# Sync
print("--- Sync Lifecycle ---")
container_sync = init(modules=[__name__])
db = container_sync.get(Database)
print(f"Connected? {db.connected}")
container_sync.cleanup_all()

# Async
async def main():
    print("\n--- Async Lifecycle ---")
    container_async = init(modules=[__name__])
    db = await container_async.aget(AsyncDatabase)
    await container_async.cleanup_all_async()

asyncio.run(main())
```

Output:

```
--- Sync Lifecycle ---
1️⃣ __init__: Object created
2️⃣ @configure: Initializing connection...
Connected? True
3️⃣ @cleanup: Closing connection...

--- Async Lifecycle ---
⏳ Connecting async...
✅ Connected!
⏳ Disconnecting async...
✅ Disconnected!
```

🎯 Exercises:

✏️ Create a `FileWriter` with `@configure` (opens file) and `@cleanup` (closes)
✏️ Create an `AsyncHttpClient` with `__ainit__` (creates session) and `@cleanup` (closes)
Step 4.3: Request Scope (Web Apps)

```python
# web_scope.py
import uuid
from pico_ioc import component, init

# 🎯 One instance PER request
@component(scope="request")
class RequestContext:
    def __init__(self):
        self.request_id = None
        self.user_id = None
        print(f"📋 RequestContext created")

@component
class UserService:
    def __init__(self, ctx: RequestContext):
        self.ctx = ctx
    
    def get_user_data(self):
        return f"Data for user {self.ctx.user_id} (req {self.ctx.request_id})"

container = init(modules=[__name__])

# Simulate Request 1
print("\n--- REQUEST 1 ---")
req_id_1 = str(uuid.uuid4())[:8]
with container.scope("request", req_id_1):
    ctx = container.get(RequestContext)
    ctx.request_id = req_id_1
    ctx.user_id = "alice"
    
    service = container.get(UserService)
    print(service.get_user_data())

# Simulate Request 2 (isolated context!)
print("\n--- REQUEST 2 ---")
req_id_2 = str(uuid.uuid4())[:8]
with container.scope("request", req_id_2):
    ctx = container.get(RequestContext)
    ctx.request_id = req_id_2
    ctx.user_id = "bob"
    
    service = container.get(UserService)
    print(service.get_user_data())
```

Output:

```
--- REQUEST 1 ---
📋 RequestContext created
Data for user alice (req a3f8d2b1)

--- REQUEST 2 ---
📋 RequestContext created
Data for user bob (req 9e4c7f3a)
```

🎯 Exercise:

✏️ Integrate this into a FastAPI app (see Integrations)
🏆 Level 4 Checkpoint
You should be able to:

## ✅ Use `singleton` vs `prototype` ✅ Use `@configure` and `@cleanup` ✅ Handle async with `__ainit__` and `aget()` ✅ Use `scope="request"` for web apps

🧪 Level 5: Testing
Step 5.1: Mocking with overrides
`services.py`:

```python
# services.py
from pico_ioc import component
from typing import Protocol

class Database(Protocol):
    def get_user(self, user_id: int) -> dict:
        pass

@component
class PostgresDB(Database):
    def get_user(self, user_id: int) -> dict:
        print("📊 Querying PostgreSQL...")
        return {"id": user_id, "name": "Real User"}

@component
class UserService:
    def __init__(self, db: Database):
        self.db = db
    
    def get_username(self, user_id: int) -> str:
        user = self.db.get_user(user_id)
        return user["name"].upper()
```

`test_services.py`:

```python
# test_services.py
import pytest
from pico_ioc import init
from services import UserService, Database

class MockDB(Database):
    def get_user(self, user_id: int) -> dict:
        print("🧪 Using Mock DB")
        return {"id": user_id, "name": "Test User"}

def test_user_service():
    # 🎯 Replace the real DB with the mock
    container = init(
        modules=["services"],
        overrides={
            Database: MockDB()  # ✅ Injects the mock
        }
    )
    
    service = container.get(UserService)
    result = service.get_username(1)
    
    assert result == "TEST USER"
```

Run:

```bash
pip install pytest
pytest test_services.py -v -s
```

Output:

```
...
test_services.py::test_user_service 🧪 Using Mock DB
PASSED
...
```

🎯 Exercises:

✏️ Mock an `EmailSender` in a test
✏️ Mock an `ApiClient` with fake responses
✏️ Use `pytest.fixture` for the test container
Step 5.2: Testing with Profiles
`databases.py`:

```python
# databases.py
from pico_ioc import component
from typing import Protocol

class Database(Protocol):
    pass

@component(conditional_profiles=("prod",))  # Only in prod
class PostgresDB(Database):
    def __init__(self):
        print("🐘 Real PostgreSQL")

@component(on_missing_selector=Database)  # Fallback if no other
class InMemoryDB(Database):
    def __init__(self):
        print("💾 In-Memory DB (test)")
```

`app.py`:

```python
# app.py
from pico_ioc import init
from databases import Database

# Production
print("--- PROD ---")
prod_container = init(
    modules=["databases"],
    profiles=("prod",)
)
db_prod = prod_container.get(Database)

# Test
print("\n--- TEST ---")
test_container = init(
    modules=["databases"],
    profiles=("test",)  # "prod" is not active
)
db_test = test_container.get(Database)
```

Output:

```
--- PROD ---
🐘 Real PostgreSQL

--- TEST ---
💾 In-Memory DB (test)
```

🎯 Exercise:

✏️ Create `RealPaymentService` (prod) and `FakePaymentService` (test) using profiles
🏆 Level 5 Checkpoint
You should be able to:

## ✅ Write tests with `overrides` ✅ Use `profiles` for environments ✅ Create mocks without touching production code

🚀 Level 6: Advanced Features
Step 6.1: AOP - Logging Interceptor

```python
# interceptors.py
import time
from pico_ioc import component, MethodInterceptor, MethodCtx, intercepted_by, init

@component
class LoggingInterceptor(MethodInterceptor):
    def invoke(self, ctx: MethodCtx, call_next):
        print(f"⏱️  Calling {ctx.cls.__name__}.{ctx.name}...")
        start = time.time()
        
        result = call_next(ctx)  # Executes the original method
        
        duration = (time.time() - start) * 1000
        print(f"✅ {ctx.name} completed in {duration:.2f}ms")
        return result

@component
class UserService:
    @intercepted_by(LoggingInterceptor)
    def get_user(self, user_id: int):
        time.sleep(0.1)  # Simulates work
        return f"User {user_id}"
    
    @intercepted_by(LoggingInterceptor)
    def delete_user(self, user_id: int):
        time.sleep(0.05)
        return f"Deleted {user_id}"

container = init(modules=[__name__])
service = container.get(UserService)

service.get_user(1)
service.delete_user(1)
```

Output:

```
⏱️  Calling UserService.get_user...
✅ get_user completed in 100.45ms
⏱️  Calling UserService.delete_user...
✅ delete_user completed in 50.23ms
```

🎯 Exercises:

✏️ Create a `CachingInterceptor` that saves results
✏️ Create an `AuthInterceptor` that checks permissions
✏️ Apply multiple interceptors to a method
Step 6.2: Event Bus (Total Decoupling)

```python
# events.py
from dataclasses import dataclass
from pico_ioc import component, init
from pico_ioc.event_bus import Event, EventBus, subscribe, AutoSubscriberMixin

# 🎯 Define events
@dataclass
class UserCreatedEvent(Event):
    user_id: int
    email: str

@dataclass
class OrderPlacedEvent(Event):
    order_id: str
    total: float

# 🎯 Services that PUBLISH events
@component
class UserService:
    def __init__(self, bus: EventBus):
        self.bus = bus
    
    async def create_user(self, email: str):
        user_id = 123  # Simulates creation
        print(f"👤 User {email} created with ID {user_id}")
        
        # Publish the event
        await self.bus.publish(UserCreatedEvent(user_id=user_id, email=email))

# 🎯 Services that LISTEN for events
@component
class EmailService(AutoSubscriberMixin):
    @subscribe(UserCreatedEvent, priority=10)
    async def send_welcome_email(self, event: UserCreatedEvent):
        print(f"📧 Sending welcome email to {event.email}")

@component
class AnalyticsService(AutoSubscriberMixin):
    @subscribe(UserCreatedEvent, priority=5)
    async def track_signup(self, event: UserCreatedEvent):
        print(f"📊 Registering signup in analytics: user_{event.user_id}")

@component
class AuditService(AutoSubscriberMixin):
    @subscribe(UserCreatedEvent)
    async def log_event(self, event: UserCreatedEvent):
        print(f"📝 Audit: User {event.user_id} created at {event.email}")

# Run
import asyncio
import pico_ioc.event_bus

async def main():
    container = init(modules=[__name__, pico_ioc.event_bus])
    
    user_service = await container.aget(UserService)
    await user_service.create_user("alice@example.com")
    
    await container.cleanup_all_async()

asyncio.run(main())
```

Output:

```
👤 User alice@example.com created with ID 123
📧 Sending welcome email to alice@example.com
📊 Registering signup in analytics: user_123
📝 Audit: User 123 created at alice@example.com
```

✨ Advantages:

  * `UserService` does NOT know `EmailService`, `AnalyticsService`, or `AuditService`
  * You can add/remove listeners without touching the publisher
  * Testing: mock the `EventBus` easily
    🎯 Exercises:

✏️ Create `OrderPlacedEvent` and have `InventoryService` listen for it
✏️ Create a listener with `policy=ExecPolicy.TASK` (fire-and-forget)
✏️ Test by publishing events without the real listeners
Step 6.3: Qualifiers (Lists of Implementations)

```python
# senders.py
from typing import List, Annotated, Protocol
from pico_ioc import component, init, Qualifier

# 🎯 Define the tag
NOTIFICATION = Qualifier("notification")

# Interface
class Sender(Protocol):
    def send(self, msg: str): ...

# Implementations with the same qualifier
@component(qualifiers=[NOTIFICATION])
class EmailSender(Sender):
    def send(self, msg: str):
        print(f"📧 Email: {msg}")

@component(qualifiers=[NOTIFICATION])
class SmsSender(Sender):
    def send(self, msg: str):
        print(f"📱 SMS: {msg}")

@component(qualifiers=[NOTIFICATION])
class PushSender(Sender):
    def send(self, msg: str):
        print(f"🔔 Push: {msg}")

# 🎯 Service that receives ALL senders with that qualifier
@component
class NotificationService:
    def __init__(self, senders: Annotated[List[Sender], NOTIFICATION]):
        self.senders = senders
        print(f"🚀 NotificationService loaded with {len(senders)} senders")
    
    def notify_all(self, message: str):
        for sender in self.senders:
            sender.send(message)

container = init(modules=[__name__])
service = container.get(NotificationService)
service.notify_all("Hello everyone!")
```

Output:

```
🚀 NotificationService loaded with 3 senders
📧 Email: Hello everyone!
📱 SMS: Hello everyone!
🔔 Push: Hello everyone!
```

🎯 Exercises:

✏️ Create `PAYMENT` qualifier for `StripeProvider`, `PayPalProvider`
✏️ Create `PaymentService` that processes with all of them
✏️ Filter the list at runtime (e.g., only enabled ones)
Step 6.4: Lazy Loading (lazy=True)

```python
# lazy.py
import time
from pico_ioc import component, init

@component(lazy=True)  # 🎯 Is NOT created on startup
class HeavyService:
    def __init__(self):
        print("⏳ Initializing heavy service...")
        time.sleep(1)  # Simulates slow load
        print("✅ HeavyService ready")
        self.data = "important"

@component
class FastService:
    def __init__(self):
        print("⚡ FastService ready instantly")

print("🔄 Initializing container...")
start = time.time()
container = init(modules=[__name__])
print(f"✅ Container ready in {time.time() - start:.2f}s\n")

# FastService was loaded, but HeavyService was NOT
fast = container.get(FastService)
print(f"FastService obtained\n")

print("🔍 Now asking for HeavyService...")
heavy = container.get(HeavyService)  # Here it is created for the first time
print(f"HeavyService obtained: {heavy.data}")
```

Output:

```
🔄 Initializing container...
⚡ FastService ready instantly
✅ Container ready in 0.01s

FastService obtained

🔍 Now asking for HeavyService...
⏳ Initializing heavy service...
✅ HeavyService ready
HeavyService obtained: importante
```

🎯 Exercise:

✏️ Create a lazy `MLModelLoader` that loads a heavy ML model
Step 6.5: Observability (Stats & Observers)

```python
# observability.py
from pico_ioc import component, init, ContainerObserver

# 🎯 Custom Observer
class MyObserver(ContainerObserver):
    def __init__(self):
        self.resolves = []
    
    def on_resolve(self, key, took_ms: float):
        self.resolves.append((key, took_ms))
        print(f"📊 Resolved {key} in {took_ms:.2f}ms")
    
    def on_cache_hit(self, key):
        print(f"⚡ Cache hit: {key}")

@component
class ServiceA:
    def __init__(self):
        import time
        time.sleep(0.01)  # Simulates work

@component
class ServiceB:
    def __init__(self, a: ServiceA):
        import time
        time.sleep(0.02)

observer = MyObserver()
container = init(
    modules=[__name__],
    observers=[observer]
)

print("\n--- First call ---")
b = container.get(ServiceB)

print("\n--- Second call ---")
b2 = container.get(ServiceB)

print("\n--- Container Stats ---")
import json
print(json.dumps(container.stats(), indent=2))

print(f"\n--- Observer captured {len(observer.resolves)} resolutions ---")
```

Output:

```
--- First call ---
📊 Resolved <class '__main__.ServiceA'> in 10.45ms
📊 Resolved <class '__main__.ServiceB'> in 20.89ms

--- Second call ---
⚡ Cache hit: <class '__main__.ServiceB'>

--- Container Stats ---
{
  "container_id": "c68a1f...",
  "profiles": [],
  "uptime_seconds": 0.05,
  "total_resolves": 2,
  "cache_hits": 1,
  "cache_hit_rate": 0.33,
  "registered_components": 2
}

--- Observer captured 2 resolutions ---
```

🎯 Exercises:

✏️ Create an observer that sends metrics to Prometheus
✏️ Export the graph with `container.export_graph("deps.dot")`
✏️ Visualize with Graphviz: `dot -Tpng deps.dot -o deps.png`
🏆 Level 6 Checkpoint
You should be able to:

## ✅ Create interceptors for logging/caching/auth ✅ Use `EventBus` to decouple services ✅ Inject lists with `Qualifiers` ✅ Optimize startup with `lazy=True` ✅ Monitor with observers and stats

🏗️ Level 7: Architecture Patterns
Step 7.1: Multi-Tenant (SaaS)
Scenario: An app where each client (tenant) has its own isolated DB and config.

```python
# multi_tenant.py
import uuid
from dataclasses import dataclass
from pico_ioc import component, init, PicoContainer

# 🎯 Tenant-specific config
@dataclass
class TenantConfig:
    tenant_id: str
    database_url: str
    feature_flags: dict

@component
class TenantDatabase:
    def __init__(self, config: TenantConfig):
        self.config = config
        print(f"🗄️  DB for tenant {config.tenant_id}: {config.database_url}")
    
    def query(self, sql: str):
        return f"[{self.config.tenant_id}] {sql}"

@component
class TenantService:
    def __init__(self, db: TenantDatabase):
        self.db = db
    
    def do_work(self):
        return self.db.query("SELECT * FROM users")

# 🎯 Global manager (singleton) that creates containers per tenant
@component
class TenantManager:
    def __init__(self):
        self.containers = {}
    
    def get_container_for_tenant(self, tenant_id: str) -> PicoContainer:
        if tenant_id not in self.containers:
            print(f"🏗️  Creating container for tenant {tenant_id}")
            
            # Tenant config (would come from master DB)
            config = TenantConfig(
                tenant_id=tenant_id,
                database_url=f"postgres://db-{tenant_id}[.example.com/data](https://.example.com/data)",
                feature_flags={"beta": tenant_id == "acme"}
            )
            
            # Isolated container for this tenant
            self.containers[tenant_id] = init(
                modules=[__name__],
                container_id=f"tenant-{tenant_id}",
                overrides={TenantConfig: config}  # 🎯 Injects its config
            )
        
        return self.containers[tenant_id]

# Main app
root_container = init(modules=[__name__], container_id="root")
manager = root_container.get(TenantManager)

# Simulate requests from different tenants
print("\n--- Request from ACME Corp ---")
acme_container = manager.get_container_for_tenant("acme")
with acme_container.as_current():  # Activates context
    service = acme_container.get(TenantService)
    print(service.do_work())

print("\n--- Request from Beta Inc ---")
beta_container = manager.get_container_for_tenant("beta")
with beta_container.as_current():
    service = beta_container.get(TenantService)
    print(service.do_work())

print("\n--- Request from ACME Corp again ---")
acme_container = manager.get_container_for_tenant("acme")  # Uses cache
with acme_container.as_current():
    service = acme_container.get(TenantService)
    print(service.do_work())
```

Output:

```
--- Request from ACME Corp ---
🏗️  Creating container for tenant acme
🗄️  DB for tenant acme: postgres://[db-acme.example.com/data](https://db-acme.example.com/data)
[acme] SELECT * FROM users

--- Request from Beta Inc ---
🏗️  Creating container for tenant beta
🗄️  DB for tenant beta: postgres://[db-beta.example.com/data](https://db-beta.example.com/data)
[beta] SELECT * FROM users

--- Request from ACME Corp again ---
[acme] SELECT * FROM users
```

🎯 Exercise:

✏️ Integrate with FastAPI using middleware (see Cookbook)
Step 7.2: CQRS Command Bus
Scenario: Separate commands (writes) from queries (reads).

```python
# cqrs.py
from dataclasses import dataclass
from typing import Protocol, List, Type
from pico_ioc import component, init

# 🎯 Contracts
class Command:
    pass

class CommandHandler(Protocol):
    @property
    def command_type(self) -> Type[Command]: ...
    
    def handle(self, command: Command): ...

# 🎯 Concrete commands
@dataclass
class CreateUserCommand(Command):
    username: str
    email: str

@dataclass
class DeleteUserCommand(Command):
    user_id: int

# 🎯 Handlers
@component
class CreateUserHandler(CommandHandler):
    @property
    def command_type(self) -> Type[Command]:
        return CreateUserCommand
    
    def handle(self, command: CreateUserCommand):
        print(f"✅ Creating user: {command.username} ({command.email})")
        # Real DB logic would go here

@component
class DeleteUserHandler(CommandHandler):
    @property
    def command_type(self) -> Type[Command]:
        return DeleteUserCommand
    
    def handle(self, command: DeleteUserCommand):
        print(f"🗑️  Deleting user ID: {command.user_id}")

# 🎯 Command Bus (auto-discovers handlers)
@component
class CommandBus:
    def __init__(self, handlers: List[CommandHandler]):
        # pico-ioc injects ALL CommandHandlers automatically
        self.handlers_map = {
            h.command_type: h for h in handlers
        }
        print(f"📦 CommandBus with {len(handlers)} handlers registered")
    
    def dispatch(self, command: Command):
        handler = self.handlers_map.get(type(command))
        if not handler:
            raise ValueError(f"No handler for {type(command)}")
        
        print(f"🚀 Dispatching {type(command).__name__}...")
        handler.handle(command)

# Usage
container = init(modules=[__name__])
bus = container.get(CommandBus)

bus.dispatch(CreateUserCommand(username="alice", email="alice@example.com"))
bus.dispatch(DeleteUserCommand(user_id=123))
```

Output:

```
📦 CommandBus with 2 handlers registered
🚀 Dispatching CreateUserCommand...
✅ Creating user: alice (alice@example.com)
🚀 Dispatching DeleteUserCommand...
🗑️  Deleting user ID: 123
```

🎯 Exercises:

✏️ Add `UpdateUserCommand` and its handler
✏️ Create a similar `QueryBus` for reads
✏️ Validate commands with Pydantic before dispatch
Step 7.3: Feature Toggles with AOP

```python
# feature_toggles.py
import os
import functools
from pico_ioc import component, MethodInterceptor, MethodCtx, intercepted_by, init

# 🎯 Feature registry
@component
class FeatureToggleRegistry:
    def __init__(self):
        # Reads from ENV which features are disabled
        disabled = os.environ.get("FEATURES_DISABLED", "")
        self.disabled = set(f.strip() for f in disabled.split(",") if f)
        print(f"🚫 Disabled features: {self.disabled}")
    
    def is_enabled(self, feature_name: str) -> bool:
        return feature_name not in self.disabled

# 🎯 Decorator to mark methods with a feature flag
FEATURE_META = "_feature_name"

def feature(name: str):
    def decorator(func):
        setattr(func, FEATURE_META, name)
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        
        setattr(wrapper, FEATURE_META, name)
        return wrapper
    return decorator

# 🎯 Interceptor that checks the flag
@component
class FeatureToggleInterceptor(MethodInterceptor):
    def __init__(self, registry: FeatureToggleRegistry):
        self.registry = registry
    
    def invoke(self, ctx: MethodCtx, call_next):
        # Read method metadata
        original = getattr(ctx.cls, ctx.name)
        feature_name = getattr(original, FEATURE_META, None)
        
        if not feature_name:
            return call_next(ctx)  # No flag, continue
        
        if self.registry.is_enabled(feature_name):
            print(f"✅ Feature '{feature_name}' enabled")
            return call_next(ctx)
        else:
            print(f"🚫 Feature '{feature_name}' disabled")
            return None  # Blocks execution

# 🎯 Service with features
@component
class PaymentService:
    @feature("new-payment-flow")
    @intercepted_by(FeatureToggleInterceptor)
    def process_payment_v2(self, amount: float):
        print(f"💳 Processing ${amount} with NEW flow")
        return "success_v2"
    
    @feature("crypto-payments")
    @intercepted_by(FeatureToggleInterceptor)
    def process_crypto(self, amount: float):
        print(f"₿ Processing ${amount} in crypto")
        return "crypto_ok"
    
    def process_payment_v1(self, amount: float):
        print(f"💳 Processing ${amount} with LEGACY flow")
        return "success_v1"

# Test with different configurations
print("=== CONFIG 1: No disabled features ===")
os.environ["FEATURES_DISABLED"] = ""
container1 = init(modules=[__name__])
service1 = container1.get(PaymentService)
service1.process_payment_v2(100)
service1.process_crypto(50)

print("\n=== CONFIG 2: Disabling 'crypto-payments' ===")
os.environ["FEATURES_DISABLED"] = "crypto-payments"
container2 = init(modules=[__name__])
service2 = container2.get(PaymentService)
service2.process_payment_v2(100)
result = service2.process_crypto(50)
print(f"Result: {result}")  # Result: None because it's blocked

print("\n=== Fallback to v1 ===")
service2.process_payment_v1(100)  # Always works
```

Output:

```
=== CONFIG 1: No disabled features ===
🚫 Disabled features: set()
✅ Feature 'new-payment-flow' enabled
💳 Processing $100 with NEW flow
✅ Feature 'crypto-payments' enabled
₿ Processing $50 in crypto

=== CONFIG 2: Disabling 'crypto-payments' ===
🚫 Disabled features: {'crypto-payments'}
✅ Feature 'new-payment-flow' enabled
💳 Processing $100 with NEW flow
🚫 Feature 'crypto-payments' disabled
Result: None

=== Fallback to v1 ===
💳 Processing $100 with LEGACY flow
```

🎯 Exercise:

✏️ Implement gradual rollout (e.g., only 20% of users)
Step 7.4: Hot Reload (Dev Server)

> **Note:** This requires `watchdog` (`pip install watchdog`) and a file structure.
> Create a folder `app` with `__init__.py` and `service.py`.
> `app/service.py`:

```python
# app/service.py
from pico_ioc import component

@component
class MyService:
    VERSION = "1.0"  # ✏️ Change this while it's running
    
    def greet(self):
        return f"Hello from version {self.VERSION}"
```

`hot_reload.py`:

```python
# hot_reload.py
import sys
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from pico_ioc import init, PicoContainer

# 🎯 Watcher that reloads the container
class ReloadHandler(FileSystemEventHandler):
    def __init__(self, reload_callback):
        self.reload_callback = reload_callback
    
    def on_modified(self, event):
        if event.src_path.endswith(".py"):
            print(f"\n🔄 Change detected in {event.src_path}")
            self.reload_callback()

def reload_container():
    global container
    
    # Clear import cache
    modules_to_remove = [m for m in sys.modules if m.startswith("app.")]
    for mod in modules_to_remove:
        print(f"♻️  Reloading module: {mod}")
        del sys.modules[mod]
    
    try:
        # Create new container
        new_container = init(modules=["app.service"])
        
        # Shutdown the old one
        old = container
        container = new_container
        old.shutdown()
        
        print("✅ Container reloaded successfully\n")
        
    except Exception as e:
        print(f"❌ Error reloading: {e}")

# Setup
container = init(modules=["app.service"])

# Watcher
handler = ReloadHandler(reload_callback=reload_container)
observer = Observer()
observer.schedule(handler, path="./app", recursive=True)
observer.start()

print("🚀 Dev server started. Edit app/service.py...")
print("   Press Ctrl+C to exit\n")

try:
    while True:
        service = container.get("app.service.MyService")
        print(f"📡 {service.greet()}")
        time.sleep(2)
except KeyboardInterrupt:
    observer.stop()
    container.shutdown()
    
observer.join()
```

Flow:

1.  Run the script
2.  Edit `app/service.py` and change `VERSION = "2.0"`
3.  Save the file
4.  The container reloads automatically without restarting\!
    🎯 Exercise:

✏️ Integrate with Flask/FastAPI (see Cookbook)
Step 7.5: CLI App (Typer Integration)

> **Note:** Requires `typer` (`pip install typer`)

```python
# cli_app.py
import os
import typer
from dataclasses import dataclass
from pico_ioc import component, configured, configuration, EnvSource, init

# 🎯 Config from ENV
@configured(prefix="APP_", mapping="auto")
@dataclass
class AppConfig:
    API_KEY: str
    API_URL: str = "[https://api.example.com](https://api.example.com)"

# 🎯 Service with logic
@component
class ApiClient:
    def __init__(self, config: AppConfig):
        self.config = config
        print(f"🔌 API Client connected to {config.API_URL}")
    
    def create_user(self, username: str):
        print(f"📡 POST {self.config.API_URL}/users")
        print(f"🔑 API Key: {self.config.API_KEY[:4]}...")
        print(f"✅ User '{username}' created")
        return {"id": 123, "username": username}

# 🎯 CLI with Typer
app = typer.Typer()

# Initialize container once
ctx = configuration(EnvSource(prefix=""))
container = init(modules=[__name__], config=ctx)

@app.command()
def create_user(username: str = typer.Argument(..., help="Username")):
    """Creates a new user"""
    client = container.get(ApiClient)
    user = client.create_user(username)
    typer.echo(f"✅ User ID: {user['id']}")

@app.command()
def health():
    """Checks service status"""
    stats = container.stats()
    typer.echo(f"📊 Container: {stats['container_id'][:8]}")
    typer.echo(f"⏱️  Uptime: {stats['uptime_seconds']:.2f}s")

if __name__ == "__main__":
    # Setup for demo
    os.environ["APP_API_KEY"] = "sk-12345678"
    os.environ["APP_API_URL"] = "[https://dev.api.com](https://dev.api.com)"
    
    app()
```

Run:

```bash
$ python cli_app.py create-user alice
🔌 API Client connected to [https://dev.api.com](https://dev.api.com)
📡 POST [https://dev.api.com/users](https://dev.api.com/users)
🔑 API Key: sk-1...
✅ User 'alice' created
✅ User ID: 123

$ python cli_app.py health
🔌 API Client connected to [https://dev.api.com](https://dev.api.com)
📊 Container: c68a1f2b
⏱️  Uptime: 0.05s
```

🎯 Exercise:

✏️ Add a `delete-user` command that uses the same `ApiClient`
🏆 Level 7 Checkpoint
You should be able to:

## ✅ Implement multi-tenancy ✅ Create command/query buses ✅ Use feature toggles ✅ Hot reload in development ✅ Structure complex CLIs

🎓 Graduation: Final Project (1 week)
📋 Specifications
Build a Multi-Tenant Blog API with these features:
Functional Requirements:

✅ Multi-tenant (each blog has its own DB)
✅ Post CRUD (Create, Read, Update, Delete)
✅ Comment system
✅ Email notifications
✅ Analytics (view counter)
Technical Requirements:

🔧 FastAPI + pico-ioc
🔧 Config from YAML + ENV
🔧 Scopes: `singleton` (services), `request` (HTTP context)
🔧 `EventBus` for notifications
🔧 AOP for logging all operations
🔧 Tests with mocks (coverage \>80%)
🔧 Health check endpoint
Suggested Architecture:

```
blog_api/
├── config/
│   ├── base.yml          # Base config
│   └── config.py         # @configured classes
├── domain/
│   ├── events.py         # PostCreatedEvent, etc
│   └── models.py         # Post, Comment
├── services/
│   ├── post_service.py   # @component
│   ├── comment_service.py
│   ├── email_service.py  # AutoSubscriberMixin
│   └── analytics_service.py
├── repositories/
│   └── post_repository.py  # @component(scope="request")
├── api/
│   ├── middleware.py     # Tenant detection
│   └── routes.py         # FastAPI routes
├── interceptors/
│   └── logging.py        # LoggingInterceptor
└── main.py               # Entrypoint
```

Bonus Points:

## 🌟 Rate limiting with an interceptor 🌟 Caching with Redis 🌟 Export metrics to Prometheus 🌟 Docker Compose with multiple tenants

📚 Additional Resources

  * **Official Documentation**
      * [Getting Started](https://pico-ioc.readthedocs.io/en/latest/getting_started.html)
      * [User Guide](https://pico-ioc.readthedocs.io/en/latest/user_guide.html)
      * [Advanced Features](https://pico-ioc.readthedocs.io/en/latest/advanced.html)
      * [Cookbook](https://pico-ioc.readthedocs.io/en/latest/cookbook.html)
      * [API Reference](https://pico-ioc.readthedocs.io/en/latest/api.html)
  * **Comparisons**
      * [vs dependency-injector](https://pico-ioc.readthedocs.io/en/latest/comparison.html#vs-dependency-injector)
      * [vs Spring Framework](https://pico-ioc.readthedocs.io/en/latest/comparison.html#vs-spring-framework)
  * **Real-world Examples**
      * [FastAPI Integration](https://pico-ioc.readthedocs.io/en/latest/cookbook.html#fastapi-integration)
      * [Flask Integration](https://pico-ioc.readthedocs.io/en/latest/cookbook.html#flask-integration)
      * [LangChain Integration](https://pico-ioc.readthedocs.io/en/latest/cookbook.html#langchain-chatbot)

-----

✅ Mastery Checklist
**Beginner Level (1-2 weeks)**

  * [ ] Understand what DI is and why it exists
  * [ ] Use `@component` for your classes
  * [ ] Use `@provides` for third-party classes
  * [ ] Resolve with `container.get()`
  * [ ] Configure with simple ENV vars

**Intermediate Level (2-4 weeks)**

  * [ ] Use complex YAML config
  * [ ] Manage scopes (`singleton`, `prototype`, `request`)
  * [ ] Write tests with `overrides`
  * [ ] Use `profiles` for environments
  * [ ] Implement `@configure` and `@cleanup`

**Advanced Level (1-2 months)**

  * [ ] Create custom interceptors
  * [ ] Use `EventBus` to decouple services
  * [ ] Inject lists with `Qualifiers`
  * [ ] Optimize startup with `lazy=True`
  * [ ] Implement advanced patterns (CQRS, Multi-tenant)
  * [ ] Understand the full container lifecycle

<!-- end list -->

```
```
