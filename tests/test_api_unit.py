# tests/test_api_unit.py
import pytest

from pico_ioc import _state
import pico_ioc.api as api
from pico_ioc.container import PicoContainer
from pico_ioc._state import _scanning


@pytest.fixture(autouse=True)
def clean_state():
    api.reset()
    assert _scanning.get() is False
    yield
    api.reset()
    assert _scanning.get() is False


def test_init_calls_scan_and_sets_scanning_and_eager(monkeypatch):
    called = {"scan": False, "eager": False, "scanning_true_inside": False}

    def fake_scan(root_package, container, *, exclude, plugins):
        called["scanning_true_inside"] = _scanning.get() is True
        called["scan"] = True

    monkeypatch.setattr(api, "scan_and_configure", fake_scan)

    orig_eager = PicoContainer.eager_instantiate_all
    def fake_eager(self):
        called["eager"] = True
        return orig_eager(self)
    monkeypatch.setattr(PicoContainer, "eager_instantiate_all", fake_eager)

    c = api.init("some_pkg")

    assert isinstance(c, PicoContainer)
    assert called["scan"] is True
    assert called["eager"] is True
    assert called["scanning_true_inside"] is True
    assert _scanning.get() is False


def test_init_reuse_short_circuits_scan(monkeypatch):
    counter = {"scan": 0}
    monkeypatch.setattr(api, "scan_and_configure", lambda *a, **k: counter.__setitem__("scan", counter["scan"] + 1))
    c1 = api.init("pkg", reuse=True)
    c2 = api.init("pkg", reuse=True)
    assert c1 is c2
    assert counter["scan"] == 1


def test_init_reuse_false_creates_new_container_and_scans(monkeypatch):
    counter = {"scan": 0}
    monkeypatch.setattr(api, "scan_and_configure", lambda *a, **k: counter.__setitem__("scan", counter["scan"] + 1))
    c1 = api.init("pkg", reuse=False)
    c2 = api.init("pkg", reuse=False)
    assert c1 is not c2
    assert counter["scan"] == 2


def test_reset_clears_cached_container(monkeypatch):
    counter = {"scan": 0}
    monkeypatch.setattr(api, "scan_and_configure", lambda *a, **k: counter.__setitem__("scan", counter["scan"] + 1))

    c1 = api.init("pkg", reuse=True)
    assert _state._container is c1
    api.reset()
    assert _state._container is None

    c2 = api.init("pkg", reuse=True)
    assert c2 is not c1
    assert counter["scan"] == 2


def test_auto_exclude_caller_when_no_exclude(monkeypatch):
    captured = {"exclude": None}
    monkeypatch.setattr(api, "scan_and_configure", lambda root_package, container, *, exclude, plugins: captured.__setitem__("exclude", exclude))

    api.init("pkg", auto_exclude_caller=True, reuse=False)
    ex = captured["exclude"]
    assert callable(ex)
    assert ex(__name__) is True
    assert ex("some.other.module") is False


def test_auto_exclude_caller_combines_with_user_exclude(monkeypatch):
    captured = {"exclude": None}
    monkeypatch.setattr(api, "scan_and_configure", lambda root_package, container, *, exclude, plugins: captured.__setitem__("exclude", exclude))

    def user_exclude(mod: str) -> bool:
        return mod == "foo.bar"

    api.init("pkg", exclude=user_exclude, auto_exclude_caller=True, reuse=False)

    ex = captured["exclude"]
    assert callable(ex)
    assert ex(__name__) is True
    assert ex("foo.bar") is True
    assert ex("x.y.z") is False


def test_plugin_hooks_are_called_in_order(monkeypatch):
    calls = []
    class DummyPlugin:
        def after_bind(self, container, binder): calls.append("after_bind")
        def before_eager(self, container, binder): calls.append("before_eager")
        def after_ready(self, container, binder): calls.append("after_ready")

    monkeypatch.setattr(api, "scan_and_configure", lambda *a, **k: None)

    api.init("pkg", plugins=(DummyPlugin(),), reuse=False)
    assert calls == ["after_bind", "before_eager", "after_ready"]


def test_logging_messages_emitted(caplog, monkeypatch):
    caplog.set_level("INFO")
    monkeypatch.setattr(api, "scan_and_configure", lambda *a, **k: None)

    api.init("pkg", reuse=False)
    msgs = [rec.message for rec in caplog.records]
    assert any("Initializing pico-ioc..." in m for m in msgs)
    assert any("Container configured and ready." in m for m in msgs)

