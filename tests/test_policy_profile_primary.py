import types
from pico_ioc import init, component
from pico_ioc.decorators import conditional, primary


def test_profile_selects_and_primary_breaks_ties():
    pkg = types.ModuleType("pkg_pol1")

    class Logger: ...
    @component
    @conditional(profiles=("dev",))
    class DevLogger(Logger): ...
    @component
    @conditional(profiles=("prod",))
    @primary
    class JsonLogger(Logger): ...

    @component
    class Service:
        def __init__(self, logger: Logger):
            self.logger = logger

    pkg.Logger = Logger
    pkg.DevLogger = DevLogger
    pkg.JsonLogger = JsonLogger
    pkg.Service = Service

    c = init(pkg, profiles=["prod"])
    s = c.get(Service)
    assert type(s.logger).__name__ == "JsonLogger"

    c2 = init(pkg, profiles=["dev"], reuse=False)
    s2 = c2.get(Service)
    assert type(s2.logger).__name__ == "DevLogger"

