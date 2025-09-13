import types
from pico_ioc import init, component
from pico_ioc.decorators import on_missing, primary, conditional

def test_on_missing_used_only_if_no_active_binding():
    pkg = types.ModuleType("pkg_mix1")

    class DB: ...
    @component
    @on_missing(DB, priority=1)
    class H2(DB): ...

    @component
    @conditional(profiles=("prod",))
    @primary
    class Postgres(DB): ...

    pkg.DB = DB
    pkg.H2 = H2
    pkg.Postgres = Postgres

    # prod profile -> Postgres active; on_missing ignored
    c = init(pkg,profiles=["prod"])
    assert type(c.get(DB)).__name__ == "Postgres"

    # dev (no active bindings) -> H2 via on_missing
    c2 = init(pkg, reuse=False)
    assert type(c2.get(DB)).__name__ == "H2"

