"""``container.scope(name, id, cleanup=...)`` -- the per-scope cache
eviction option.

With ``cleanup=True`` the instances cached under the scope id are evicted
when the block exits and their ``@cleanup`` hooks run, so short-lived
scopes (request, transaction) do not accumulate instances. With the
default ``cleanup=False`` the cached instance survives the block.
"""

from pico_ioc import cleanup, component, init


@component(scope="request")
class ReqScoped:
    created = 0
    cleaned = 0

    def __init__(self) -> None:
        ReqScoped.created += 1
        self.id = ReqScoped.created

    @cleanup
    def _done(self) -> None:
        ReqScoped.cleaned += 1


def _fresh_container():
    return init(modules=[__name__])


def test_cleanup_true_evicts_and_runs_hook():
    ReqScoped.created = ReqScoped.cleaned = 0
    c = _fresh_container()
    try:
        with c.scope("request", "r1", cleanup=True):
            first = c.get(ReqScoped).id
            assert c.get(ReqScoped).id == first  # cached within the scope
        assert ReqScoped.cleaned == 1, "cleanup=True must run the @cleanup hook on exit"

        # A new scope with the same id starts empty -> a fresh instance.
        with c.scope("request", "r1", cleanup=True):
            assert c.get(ReqScoped).id != first
    finally:
        c.shutdown()


def test_cleanup_false_is_default_and_preserves_instance():
    ReqScoped.created = ReqScoped.cleaned = 0
    c = _fresh_container()
    try:
        with c.scope("request", "keep"):
            first = c.get(ReqScoped).id
        assert ReqScoped.cleaned == 0, "default cleanup=False must not run the hook"

        # Same scope id still holds the cached instance.
        with c.scope("request", "keep"):
            assert c.get(ReqScoped).id == first
    finally:
        c.shutdown()
