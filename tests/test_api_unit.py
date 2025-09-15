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
        return (0, 0, [])

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
    def fake_scan(*a, **k):
        counter["scan"] += 1
        return (0, 0, [])
    monkeypatch.setattr(api, "scan_and_configure", fake_scan)

    c1 = api.init("pkg", reuse=True)
    c2 = api.init("pkg", reuse=True)
    assert c1 is c2
    assert counter["scan"] == 1


def test_init_reuse_false_creates_new_container_and_scans(monkeypatch):
    counter = {"scan": 0}
    def fake_scan(*a, **k):
        counter["scan"] += 1
        return (0, 0, [])
    monkeypatch.setattr(api, "scan_and_configure", fake_scan)

    c1 = api.init("pkg", reuse=False)
    c2 = api.init("pkg", reuse=False)
    assert c1 is not c2
    assert counter["scan"] == 2


def test_reset_clears_cached_container(monkeypatch):
    counter = {"scan": 0}
    def fake_scan(*a, **k):
        counter["scan"] += 1
        return (0, 0, [])
    monkeypatch.setattr(api, "scan_and_configure", fake_scan)

    c1 = api.init("pkg", reuse=True)
    assert _state._container is c1
    api.reset()
    assert _state._container is None

    c2 = api.init("pkg", reuse=True)
    assert c2 is not c1
    assert counter["scan"] == 2


def test_auto_exclude_caller_when_no_exclude(monkeypatch):
    captured = {"exclude": None}
    def fake_scan(root_package, container, *, exclude, plugins):
        captured["exclude"] = exclude
        return (0, 0, [])
    monkeypatch.setattr(api, "scan_and_configure", fake_scan)

    api.init("pkg", auto_exclude_caller=True, reuse=False)
    ex = captured["exclude"]
    assert callable(ex)
    assert ex(__name__) is True
    assert ex("some.other.module") is False


def test_auto_exclude_caller_combines_with_user_exclude(monkeypatch):
    captured = {"exclude": None}
    def fake_scan(root_package, container, *, exclude, plugins):
        captured["exclude"] = exclude
        return (0, 0, [])
    monkeypatch.setattr(api, "scan_and_configure", fake_scan)

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

    monkeypatch.setattr(api, "scan_and_configure", lambda *a, **k: (0, 0, []))

    api.init("pkg", plugins=(DummyPlugin(),), reuse=False)
    assert calls == ["after_bind", "before_eager", "after_ready"]


def test_logging_messages_emitted(caplog, monkeypatch):
    caplog.set_level("INFO")
    monkeypatch.setattr(api, "scan_and_configure", lambda *a, **k: (0, 0, []))

    api.init("pkg", reuse=False)
    msgs = [rec.message for rec in caplog.records]
    # We no longer log "Initializing pico-ioc...", but we do log scan summaries and readiness
    assert any("Scanned 'pkg' (components:" in m for m in msgs)
    assert any("Container configured and ready." in m for m in msgs)


# --- Overrides tests -----------------------------------------------------------

def test_overrides_bind_instance_provider_and_lazy(monkeypatch):
    calls = {"scanned_x": 0, "prov_y": 0, "lazy_z": 0}

    def fake_scan(root_package, container, *, exclude, plugins):
        container.bind("x", lambda: ("scanned", calls.__setitem__("scanned_x", calls["scanned_x"] + 1)), lazy=False)
        return (0, 0, [])

    monkeypatch.setattr(api, "scan_and_configure", fake_scan)

    def prov_y():
        calls["prov_y"] += 1
        return {"y": "from-provider"}

    def prov_z():
        calls["lazy_z"] += 1
        return {"z": "lazy-provider"}

    c = api.init(
        "pkg",
        reuse=False,
        overrides={
            "x": {"x": "constant"},
            "y": prov_y,
            "z": (prov_z, True),
        },
    )

    assert c.get("x") == {"x": "constant"}
    assert calls["scanned_x"] == 0

    assert c.get("y") == {"y": "from-provider"}
    assert calls["prov_y"] == 1

    assert calls["lazy_z"] == 0
    assert c.get("z") == {"z": "lazy-provider"}
    assert calls["lazy_z"] == 1
    assert c.get("z") == {"z": "lazy-provider"}
    assert calls["lazy_z"] == 1


def test_overrides_apply_on_reused_container(monkeypatch):
    def fake_scan(*a, **k):
        return (0, 0, [])
    monkeypatch.setattr(api, "scan_and_configure", fake_scan)

    c1 = api.init("pkg", reuse=True, overrides={"k": {"v": 1}})
    assert c1.get("k") == {"v": 1}

    c2 = api.init("pkg", reuse=True, overrides={"k": {"v": 2}})
    assert c1 is c2
    assert c2.get("k") == {"v": 2}

