import types
from pico_ioc import init, component, factory_component, provides
from pico_ioc.decorators import primary, conditional, on_missing


def test_factory_two_provides_same_key_primary_breaks_tie():
    pkg = types.ModuleType("pkg_fact_primary")

    class Logger: ...
    class Stdout(Logger): ...
    class Json(Logger): ...

    @factory_component
    class LoggingFactory:
        # Both active → collapse by @primary
        @provides(Logger)
        def stdout_logger(self) -> Logger:
            return Stdout()

        @provides(Logger)
        @primary
        def json_logger(self) -> Logger:
            return Json()

    @component
    class Service:
        def __init__(self, logger: Logger):
            self.logger = logger

    pkg.Logger = Logger
    pkg.Stdout = Stdout
    pkg.Json = Json
    pkg.LoggingFactory = LoggingFactory
    pkg.Service = Service

    c = init(pkg)  # core policy is on by default
    s = c.get(Service)
    assert type(s.logger).__name__ == "Json"


def test_factory_two_provides_same_key_selected_by_profile():
    pkg = types.ModuleType("pkg_fact_profile")

    class Logger: ...
    class Dev(Logger): ...
    class Prod(Logger): ...

    @factory_component
    class LoggingFactory:
        @provides(Logger)
        @conditional(profiles=("dev",))
        def dev_logger(self) -> Logger:
            return Dev()

        @provides(Logger)
        @conditional(profiles=("prod",))
        def prod_logger(self) -> Logger:
            return Prod()

    @component
    class Service:
        def __init__(self, logger: Logger):
            self.logger = logger

    pkg.Logger = Logger
    pkg.Dev = Dev
    pkg.Prod = Prod
    pkg.LoggingFactory = LoggingFactory
    pkg.Service = Service

    c_prod = init(pkg, profiles=["prod"])
    assert type(c_prod.get(Service).logger).__name__ == "Prod"

    c_dev = init(pkg, profiles=["dev"], reuse=False)
    assert type(c_dev.get(Service).logger).__name__ == "Dev"


def test_factory_provides_activated_by_env(monkeypatch):
    pkg = types.ModuleType("pkg_fact_env")

    class Cache: ...
    class Redis(Cache): ...
    class Memcached(Cache): ...

    @factory_component
    class CacheFactory:
        @provides(Cache)
        @conditional(require_env=("REDIS_URL",))
        def redis(self) -> Cache:
            return Redis()

        @provides(Cache)
        @conditional(require_env=("MEMCACHED_URL",))
        def memcached(self) -> Cache:
            return Memcached()

    @component
    class Service:
        def __init__(self, cache: Cache):
            self.cache = cache

    pkg.Cache = Cache
    pkg.Redis = Redis
    pkg.Memcached = Memcached
    pkg.CacheFactory = CacheFactory
    pkg.Service = Service

    # Only REDIS_URL present -> Redis wins
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
    monkeypatch.delenv("MEMCACHED_URL", raising=False)

    c = init(pkg)  # profiles not needed; env drives activation
    assert type(c.get(Service).cache).__name__ == "Redis"

    # Only MEMCACHED_URL present -> Memcached wins
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("MEMCACHED_URL", "memcached://localhost:11211")

    c2 = init(pkg, reuse=False)
    assert type(c2.get(Service).cache).__name__ == "Memcached"


def test_factory_on_missing_default_applies_when_no_active_binding():
    pkg = types.ModuleType("pkg_fact_on_missing")

    class Storage: ...
    class Local(Storage): ...
    class S3(Storage): ...

    @factory_component
    class StorageFactory:
        # Default if nothing else binds Storage
        @provides(Storage)
        @on_missing(Storage, priority=1)
        def local(self) -> Storage:
            return Local()

    @component
    class Service:
        def __init__(self, storage: Storage):
            self.storage = storage

    pkg.Storage = Storage
    pkg.Local = Local
    pkg.S3 = S3
    pkg.StorageFactory = StorageFactory
    pkg.Service = Service

    c = init(pkg)
    assert type(c.get(Service).storage).__name__ == "Local"


def test_factory_on_missing_priority_picks_highest():
    pkg = types.ModuleType("pkg_fact_on_missing_prio")

    class DB: ...
    class H2(DB): ...
    class Postgres(DB): ...

    @factory_component
    class DBFactory:
        @provides(DB)
        @on_missing(DB, priority=1)
        def h2(self) -> DB:
            return H2()

        @provides(DB)
        @on_missing(DB, priority=10)
        def pg(self) -> DB:
            return Postgres()

    pkg.DB = DB
    pkg.H2 = H2
    pkg.Postgres = Postgres
    pkg.DBFactory = DBFactory

    c = init(pkg)
    assert type(c.get(DB)).__name__ == "Postgres"

