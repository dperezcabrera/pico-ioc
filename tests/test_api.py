# tests/test_api.py
import logging
import types
import pytest

from pico_ioc import _state, init, reset, scope, component
from pico_ioc.container import PicoContainer
from pico_ioc.plugins import PicoPlugin

# --- Fixture ---

@pytest.fixture(autouse=True)
def clean_state():
    """Ensure a clean global state before and after each test."""
    reset()
    yield
    reset()

# --- Init, Reuse, and Reset Tests ---

def test_init_calls_scan_and_eager_instantiate(monkeypatch):
    """
    Verifies the main initialization flow: scanning is called within a specific
    context and eager instantiation happens at the end.
    """
    called = {"scan": 0, "eager": 0, "scanning_true_inside": False}
    
    def fake_scan(*a, **k):
        called["scan"] += 1
        # Check that the scanning flag is active during the scan
        called["scanning_true_inside"] = _state._scanning.get()
        return (0, 0, [])
    monkeypatch.setattr("pico_ioc.builder.scan_and_configure", fake_scan)
    
    # Patch eager instantiation to track its call
    orig_eager = PicoContainer.eager_instantiate_all
    def fake_eager(self):
        called["eager"] += 1
        return orig_eager(self)
    monkeypatch.setattr(PicoContainer, "eager_instantiate_all", fake_eager)

    pkg = types.ModuleType("some_pkg")
    container = init(pkg)
    
    assert isinstance(container, PicoContainer)
    assert called["scan"] == 1
    assert called["eager"] == 1
    assert called["scanning_true_inside"] is True
    # Ensure scanning flag is reset after init
    assert _state._scanning.get() is False

def test_init_reuse_logic(monkeypatch):
    """Tests the container reuse logic based on parameters and the 'reuse' flag."""
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
    assert c4 is not c3
    assert counter["scan"] == 3

def test_reset_clears_cached_container(monkeypatch):
    """Ensures reset() clears the global container, forcing a rebuild on the next init."""
    monkeypatch.setattr("pico_ioc.builder.scan_and_configure", lambda *a, **k: (0, 0, []))
    pkg = types.ModuleType("pkg")
    
    c1 = init(pkg, reuse=True)
    ctx = _state.get_context()
    assert ctx is not None and ctx.container is c1
    
    reset()
    assert _state.get_context() is None

    # Next call should create a new container
    c2 = init(pkg, reuse=True)
    assert c2 is not c1

# --- Configuration Tests (Profiles, Plugins, Overrides) ---

def test_init_reads_profiles_from_env_var(monkeypatch):
    """Checks that profiles are correctly read from the PICO_PROFILE environment variable."""
    monkeypatch.setattr("pico_ioc.builder.scan_and_configure", lambda *a, **k: (0, 0, []))
    monkeypatch.setenv("PICO_PROFILE", "prof1, prof2,prof3 ")
    
    pkg = types.ModuleType("pkg")
    container = init(pkg)
    
    assert getattr(container, "_active_profiles", None) == ("prof1", "prof2", "prof3")

def test_plugin_hooks_are_called_in_order(monkeypatch):
    """Verifies that plugin lifecycle hooks are executed in the correct sequence."""
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
    """Ensures that a failing plugin does not crash init(), but logs an error."""
    caplog.set_level(logging.ERROR)
    class BadPlugin(PicoPlugin):
        def after_bind(self, *a): raise ValueError("Plugin failed!")
    
    monkeypatch.setattr("pico_ioc.builder.scan_and_configure", lambda *a, **k: (0, 0, []))
    pkg = types.ModuleType("pkg")
    
    container = init(pkg, plugins=(BadPlugin(),), reuse=False)
    
    assert isinstance(container, PicoContainer)
    assert "Plugin after_bind failed" in caplog.text
    assert "ValueError: Plugin failed!" in caplog.text

def test_overrides_are_applied_and_affect_reuse(monkeypatch):
    """Checks that overrides are applied and that changes to them correctly affect container reuse."""
    monkeypatch.setattr("pico_ioc.builder.scan_and_configure", lambda *a, **k: (0, 0, []))
    pkg = types.ModuleType("pkg")
    
    c1 = init(pkg, reuse=True, overrides={"k": 1})
    assert c1.get("k") == 1
    
    # Different overrides should force a rebuild
    c2 = init(pkg, reuse=True, overrides={"k": 2})
    assert c1 is not c2
    assert c2.get("k") == 2

    # The same overrides should allow reuse
    c3 = init(pkg, reuse=True, overrides={"k": 2})
    assert c2 is c3

# --- Scanning and Exclude Logic ---

def test_auto_exclude_caller_when_no_user_exclude(monkeypatch):
    """Tests that auto_exclude_caller works correctly on its own."""
    captured = {}
    def fake_scan(root_package, container, *, exclude, plugins):
        captured["exclude"] = exclude
        return (0, 0, [])
    monkeypatch.setattr("pico_ioc.builder.scan_and_configure", fake_scan)
    
    pkg = types.ModuleType("pkg")
    init(pkg, auto_exclude_caller=True, reuse=False)
    
    ex = captured["exclude"]
    assert callable(ex)
    assert ex(__name__) is True  # Excludes the test module itself
    assert ex("some.other.module") is False

def test_auto_exclude_caller_combines_with_user_exclude(monkeypatch):
    """Tests that auto_exclude_caller correctly combines with a user-provided exclude function."""
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
    assert ex(__name__) is True      # From auto_exclude_caller
    assert ex("foo.bar") is True     # From user_exclude
    assert ex("x.y.z") is False

# --- Scope Function Tests ---

def test_scope_filters_by_include_tag():
    """Verifies that scope() can filter components to include by tag."""
    pkg = types.ModuleType("pkg_scope_include")
    @component(tags=("tag_a",))
    class ComponentA: ...
    pkg.ComponentA = ComponentA
    @component(tags=("tag_b",))
    class ComponentB: ...
    pkg.ComponentB = ComponentB

    container = scope(modules=[pkg], include_tags={"tag_a"})

    assert container.has(ComponentA) is True
    assert container.has(ComponentB) is False

def test_scope_filters_by_exclude_tag():
    """Verifies that scope() can filter components to exclude by tag."""
    pkg = types.ModuleType("pkg_scope_exclude")
    @component(tags=("tag_a", "common"))
    class ComponentA: ...
    pkg.ComponentA = ComponentA
    @component(tags=("tag_b", "common"))
    class ComponentB: ...
    pkg.ComponentB = ComponentB

    container = scope(modules=[pkg], exclude_tags={"tag_a"})

    assert container.has(ComponentA) is False
    assert container.has(ComponentB) is True

def test_scope_with_base_container_and_strict_mode():
    """Tests how scope() interacts with a base container in strict and non-strict modes."""
    # Base container setup
    base_pkg = types.ModuleType("base_pkg")
    @component
    class BaseService:
        def get_value(self): return 42
    base_pkg.BaseService = BaseService
    base_container = init(base_pkg)

    # Scoped container setup
    scope_pkg = types.ModuleType("scope_pkg")
    @component
    class ScopedComponent:
        def __init__(self, base_service: BaseService):
            self.base_service = base_service
    scope_pkg.ScopedComponent = ScopedComponent

    # Non-strict mode should allow resolving dependencies from the base container
    scoped_container = scope(
        modules=[scope_pkg], base=base_container, strict=False, roots=[ScopedComponent]
    )
    instance = scoped_container.get(ScopedComponent)
    assert isinstance(instance, ScopedComponent)
    assert instance.base_service.get_value() == 42

    # Strict mode should fail because BaseService is not in the scoped modules
    with pytest.raises(NameError):
        strict_scope = scope(
            modules=[scope_pkg], base=base_container, strict=True, roots=[ScopedComponent]
        )
        _ = strict_scope.get(ScopedComponent)

# --- Logging Tests ---

def test_logging_messages_emitted(caplog, monkeypatch):
    """Ensures key informational messages are logged during initialization."""
    caplog.set_level("INFO")
    monkeypatch.setattr("pico_ioc.builder.scan_and_configure", lambda *a, **k: (0, 0, []))

    pkg = types.ModuleType("pkg_log")
    init(pkg, reuse=False)
    
    msgs = [rec.message for rec in caplog.records]
    assert any("Scanned 'pkg_log' (components:" in m for m in msgs)
    assert any("Container configured and ready." in m for m in msgs)

