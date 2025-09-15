# tests/test_api.py
import logging
import types # Import types to create fake modules
import pytest

from pico_ioc import _state, init, reset
from pico_ioc.container import PicoContainer
from pico_ioc.plugins import PicoPlugin


@pytest.fixture(autouse=True)
def clean_state():
    reset()
    yield
    reset()

# --- Init and Reuse Tests ---

def test_init_calls_scan_and_eager_instantiate(monkeypatch):
    called = {"scan": 0, "eager": 0}
    def fake_scan(*a, **k):
        called["scan"] += 1
        return (0, 0, [])
    # FIX: Patch the function where it is called (in the builder).
    monkeypatch.setattr("pico_ioc.builder.scan_and_configure", fake_scan)
    
    orig_eager = PicoContainer.eager_instantiate_all
    def fake_eager(self):
        called["eager"] += 1
        return orig_eager(self)
    monkeypatch.setattr(PicoContainer, "eager_instantiate_all", fake_eager)

    # FIX: Use a fake module object instead of a string.
    pkg = types.ModuleType("some_pkg")
    c = init(pkg)
    assert isinstance(c, PicoContainer)
    assert called["scan"] == 1
    assert called["eager"] == 1

def test_init_reuse_logic(monkeypatch):
    counter = {"scan": 0}
    def fake_scan(*a, **k):
        counter["scan"] += 1
        return (0, 0, [])
    monkeypatch.setattr("pico_ioc.builder.scan_and_configure", fake_scan)
    
    pkg = types.ModuleType("pkg")

    # Reuses if params are identical
    c1 = init(pkg, profiles=["a"], reuse=True)
    c2 = init(pkg, profiles=["a"], reuse=True)
    assert c1 is c2
    assert counter["scan"] == 1

    # Does not reuse if reuse=False
    c3 = init(pkg, profiles=["a"], reuse=False)
    assert c3 is not c1
    assert counter["scan"] == 2
    
    # Does not reuse if profiles change
    c4 = init(pkg, profiles=["b"], reuse=True)
    assert c4 is not c3 # Compare to the last created one
    assert counter["scan"] == 3

def test_reset_clears_cached_container(monkeypatch):
    monkeypatch.setattr("pico_ioc.builder.scan_and_configure", lambda *a, **k: (0, 0, []))
    pkg = types.ModuleType("pkg")
    c1 = init(pkg, reuse=True)
    assert _state._container is c1
    
    reset()
    assert _state._container is None

    c2 = init(pkg, reuse=True)
    assert c2 is not c1

# --- Configuration Tests (Profiles, Plugins, Overrides) ---

def test_init_reads_profiles_from_env_var(monkeypatch):
    monkeypatch.setattr("pico_ioc.builder.scan_and_configure", lambda *a, **k: (0, 0, []))
    monkeypatch.setenv("PICO_PROFILE", "prof1, prof2,prof3 ")
    pkg = types.ModuleType("pkg")
    container = init(pkg)
    assert getattr(container, "_active_profiles", None) == ("prof1", "prof2", "prof3")

def test_plugin_hooks_are_called_in_order(monkeypatch):
    calls = []
    class DummyPlugin(PicoPlugin):
        def after_bind(self, *a): calls.append("after_bind")
        def before_eager(self, *a): calls.append("before_eager")
        def after_ready(self, *a): calls.append("after_ready")
    
    monkeypatch.setattr("pico_ioc.builder.scan_and_configure", lambda *a, **k: (0, 0, []))
    pkg = types.ModuleType("pkg")
    init(pkg, plugins=(DummyPlugin(),), reuse=False)
    assert calls == ["after_bind", "before_eager", "after_ready"]

def test_init_continues_and_logs_on_plugin_failure(monkeypatch, caplog):
    caplog.set_level(logging.ERROR)
    class BadPlugin(PicoPlugin):
        def after_bind(self, *a): raise ValueError("Plugin failed!")
    
    monkeypatch.setattr("pico_ioc.builder.scan_and_configure", lambda *a, **k: (0, 0, []))
    pkg = types.ModuleType("pkg")
    container = init(pkg, plugins=(BadPlugin(),), reuse=False)
    assert isinstance(container, PicoContainer)
    assert "Plugin after_bind failed" in caplog.text
    assert "ValueError: Plugin failed!" in caplog.text

def test_overrides_are_applied(monkeypatch):
    monkeypatch.setattr("pico_ioc.builder.scan_and_configure", lambda *a, **k: (0, 0, []))
    pkg = types.ModuleType("pkg")
    
    c1 = init(pkg, reuse=True, overrides={"k": 1})
    assert c1.get("k") == 1
    
    # FIX: Overrides now correctly force a rebuild.
    c2 = init(pkg, reuse=True, overrides={"k": 2})
    assert c1 is not c2
    assert c2.get("k") == 2

    # FIX: Calling again with the *same* overrides reuses the container.
    c3 = init(pkg, reuse=True, overrides={"k": 2})
    assert c2 is c3

# --- Auto Exclude Tests ---

def test_auto_exclude_caller_combines_with_user_exclude(monkeypatch):
    captured = {}
    def fake_scan(root_package, container, *, exclude, plugins):
        captured["exclude"] = exclude
        return (0, 0, [])
    monkeypatch.setattr("pico_ioc.builder.scan_and_configure", fake_scan)

    def user_exclude(mod: str) -> bool:
        return mod == "foo.bar"
    
    pkg = types.ModuleType("pkg")
    init(pkg, exclude=user_exclude, auto_exclude_caller=True, reuse=False)
    
    ex = captured["exclude"]
    assert callable(ex)
    assert ex(__name__) is True  # from auto_exclude_caller
    assert ex("foo.bar") is True   # from user_exclude
    assert ex("x.y.z") is False
