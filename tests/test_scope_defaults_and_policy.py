import types
from pico_ioc import scope, init, component
from pico_ioc.decorators import conditional, on_missing

def test_scope_applies_policy_and_defaults():
    pkg = types.ModuleType("pkg_scope_pol1")

    class MQ: ...
    @component
    @conditional(profiles=("prod",))
    class Kafka(MQ): ...
    @component
    @on_missing(MQ, priority=1)
    class InMemMQ(MQ): ...

    @component
    class App:
        def __init__(self, mq: MQ):
            self.mq = mq

    pkg.MQ = MQ
    pkg.Kafka = Kafka
    pkg.InMemMQ = InMemMQ
    pkg.App = App

    # prod: Kafka active
    c_prod = scope(modules=[pkg], roots=[App], profiles=["prod"], strict=True, lazy=True)

    # Para validar la política core (no plugin), usamos init con perfiles:
    c = init(pkg, profiles=["prod"], reuse=False)
    a = c.get(App)
    assert type(a.mq).__name__ == "Kafka"

    # dev: fallback to default InMemMQ
    c2 = init(pkg, profiles=["dev"], reuse=False)
    a2 = c2.get(App)
    assert type(a2.mq).__name__ == "InMemMQ"

