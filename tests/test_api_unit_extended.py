# tests/test_api_unit_extended.py
import logging
import pytest

from pico_ioc import init, reset
from pico_ioc.container import PicoContainer
from pico_ioc.plugins import PicoPlugin


@pytest.fixture(autouse=True)
def clean_state():
    reset()
    yield
    reset()


def test_init_reuse_is_false_when_profiles_change(monkeypatch):
    counter = {"scan": 0}

    def fake_scan(*a, **k):
        counter["scan"] += 1
        return (0, 0, [])

    monkeypatch.setattr("pico_ioc.api.scan_and_configure", fake_scan)

    c1 = init("pkg", profiles=["a"], reuse=True)
    assert counter["scan"] == 1
    assert getattr(c1, "_active_profiles", None) == ("a",)

    c2 = init("pkg", profiles=["b"], reuse=True)
    assert counter["scan"] == 2
    assert c2 is not c1
    assert getattr(c2, "_active_profiles", None) == ("b",)


def test_init_reads_profiles_from_env_var(monkeypatch):
    def fake_scan(*a, **k):
        return (0, 0, [])
    monkeypatch.setattr("pico_ioc.api.scan_and_configure", fake_scan)
    monkeypatch.setenv("PICO_PROFILE", "prof1, prof2,prof3 ")

    container = init("pkg")

    assert hasattr(container, "_active_profiles")
    assert getattr(container, "_active_profiles") == ("prof1", "prof2", "prof3")


def test_init_continues_and_logs_on_plugin_failure(monkeypatch, caplog):
    caplog.set_level(logging.ERROR)

    class BadPlugin(PicoPlugin):
        def after_bind(self, container, binder):
            raise ValueError("Plugin failed!")

    def fake_scan(*a, **k):
        return (0, 0, [])
    monkeypatch.setattr("pico_ioc.api.scan_and_configure", fake_scan)

    container = init("pkg", plugins=(BadPlugin(),), reuse=False)

    assert isinstance(container, PicoContainer)
    # run_plugin_hook logs: "Plugin %s failed" % hook_name with stacktrace
    assert "Plugin after_bind failed" in caplog.text
    assert "ValueError: Plugin failed!" in caplog.text


def test_scope_filters_by_include_tag(tmp_path):
    import types
    from pico_ioc import component, scope

    pkg = types.ModuleType("pkg_scope_include")

    @component(tags=("tag_a",))
    class ComponentA: ...
    pkg.ComponentA = ComponentA

    @component(tags=("tag_b",))
    class ComponentB: ...
    pkg.ComponentB = ComponentB

    container = scope(modules=[pkg], include_tags={"tag_a"}, roots=[ComponentA, ComponentB])

    assert container.has(ComponentA) is True
    assert container.has(ComponentB) is False


def test_scope_filters_by_exclude_tag(tmp_path):
    import types
    from pico_ioc import component, scope

    pkg = types.ModuleType("pkg_scope_exclude")

    @component(tags=("tag_a", "common"))
    class ComponentA: ...
    pkg.ComponentA = ComponentA

    @component(tags=("tag_b", "common"))
    class ComponentB: ...
    pkg.ComponentB = ComponentB

    container = scope(modules=[pkg], exclude_tags={"tag_a"}, roots=[ComponentA, ComponentB])

    assert container.has(ComponentA) is False
    assert container.has(ComponentB) is True


def test_scope_with_base_container_and_strict_false(tmp_path):
    import types
    from pico_ioc import component, scope, init

    base_pkg = types.ModuleType("base_pkg")

    @component
    class BaseService:
        def get_value(self):
            return 42
    base_pkg.BaseService = BaseService
    base_container = init(base_pkg)

    scope_pkg = types.ModuleType("scope_pkg")

    @component
    class ScopedComponent:
        def __init__(self, base_service: BaseService):
            self.base_service = base_service
    scope_pkg.ScopedComponent = ScopedComponent

    scoped_container = scope(
        modules=[scope_pkg],
        base=base_container,
        strict=False,
        roots=[ScopedComponent]
    )

    instance = scoped_container.get(ScopedComponent)
    assert isinstance(instance, ScopedComponent)
    assert instance.base_service.get_value() == 42

    with pytest.raises(NameError):
        strict_scope = scope(
            modules=[scope_pkg],
            base=base_container,
            strict=True,
            roots=[ScopedComponent]
        )
        _ = strict_scope.get(ScopedComponent)

