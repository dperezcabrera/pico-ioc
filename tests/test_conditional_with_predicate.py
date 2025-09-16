import types
import pytest

from pico_ioc import component, conditional, on_missing, scope


@pytest.mark.parametrize(
    "case, predicate_behavior, expected_impl",
    [
        ("true", lambda: True, "Redis"),
        ("false", lambda: False, "InMem"),
        ("error", lambda: (_ for _ in ()).throw(RuntimeError("boom")), "InMem"),
    ],
)
def test_conditional_with_predicate(case, predicate_behavior, expected_impl):
    pkg = types.ModuleType(f"pkg_cond_pred_{case}")

    class MQ: ...
    pkg.MQ = MQ

    @component
    @conditional(predicate=predicate_behavior)
    class Redis(MQ): ...
    pkg.Redis = Redis

    @component
    @on_missing(MQ, priority=1)
    class InMem(MQ): ...
    pkg.InMem = InMem

    @component
    class App:
        def __init__(self, mq: MQ):
            self.mq = mq
    pkg.App = App

    c = scope(modules=[pkg], roots=[App], strict=True, lazy=True)

    app = c.get(App)
    impl_name = type(app.mq).__name__
    assert impl_name == expected_impl, f"for case '{case}' expected {expected_impl}, got {impl_name}"

