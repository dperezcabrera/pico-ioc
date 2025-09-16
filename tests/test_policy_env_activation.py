import os, types
from pico_ioc import init, component
from pico_ioc.decorators import conditional

def test_conditional_require_env_activates_without_overrides(monkeypatch):
    pkg = types.ModuleType("pkg_pol_env1")

    class Cache: ...
    @component
    @conditional(require_env=("REDIS_URL",))
    class RedisCache(Cache): ...
    @component
    @conditional(require_env=("MEMCACHED_URL",))
    class MemcachedCache(Cache): ...

    @component
    class Service:
        def __init__(self, cache: Cache):
            self.cache = cache

    pkg.Cache = Cache
    pkg.RedisCache = RedisCache
    pkg.MemcachedCache = MemcachedCache
    pkg.Service = Service

    # Only REDIS_URL present -> Redis wins
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
    monkeypatch.delenv("MEMCACHED_URL", raising=False)

    c = init(pkg)
    s = c.get(Service)
    assert type(s.cache).__name__ == "RedisCache"

