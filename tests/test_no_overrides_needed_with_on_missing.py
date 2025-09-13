import types
from pico_ioc import init, component
from pico_ioc.decorators import on_missing, conditional

def test_no_overrides_needed_default_fills_in():
    pkg = types.ModuleType("pkg_noovr1")

    class Storage: ...
    @component
    @conditional(profiles=("prod",))
    class S3Storage(Storage): ...
    @component
    @on_missing(Storage, priority=1)
    class LocalStorage(Storage): ...

    @component
    class Service:
        def __init__(self, storage: Storage):
            self.storage = storage

    pkg.Storage = Storage
    pkg.S3Storage = S3Storage
    pkg.LocalStorage = LocalStorage
    pkg.Service = Service

    # Without profile match -> only LocalStorage via on_missing
    c = init(pkg, plugins=())
    s = c.get(Service)
    assert type(s.storage).__name__ == "LocalStorage"

