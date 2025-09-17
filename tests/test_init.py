import pytest
import sys
import logging
import importlib
import textwrap
from pathlib import Path

import pico_ioc

@pytest.fixture
def temp_project(tmp_path):
    project_root = tmp_path / "test_project"
    project_root.mkdir()
    sys.path.insert(0, str(tmp_path))
    (project_root / "__init__.py").touch()
    pkg_dir = project_root / "pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").touch()
    def create_file(path, content):
        (pkg_dir / path).write_text(textwrap.dedent(content))
    yield "test_project.pkg", create_file
    sys.path.pop(0)
    mods_to_del = [m for m in list(sys.modules.keys()) if m.startswith("test_project")]
    for m in mods_to_del:
        sys.modules.pop(m, None)

class TestCoreBehaviors:
    def test_simple_component_retrieval(self, temp_project):
        pkg_name, create_file = temp_project
        create_file("components.py", """
            from pico_ioc import component
            @component
            class SimpleService: pass
        """)
        container = pico_ioc.init(pkg_name)
        SimpleService = importlib.import_module(f"{pkg_name}.components").SimpleService
        service = container.get(SimpleService)
        assert service is not None
        assert isinstance(service, SimpleService)

    def test_dependency_injection_by_type_hint(self, temp_project):
        pkg_name, create_file = temp_project
        create_file("components.py", """
            from pico_ioc import component
            @component
            class SimpleService: pass
            @component
            class AnotherService:
                def __init__(self, simple_service: SimpleService):
                    self.child = simple_service
        """)
        container = pico_ioc.init(pkg_name)
        mdl = importlib.import_module(f"{pkg_name}.components")
        SimpleService, AnotherService = mdl.SimpleService, mdl.AnotherService
        another = container.get(AnotherService)
        assert another is not None
        assert isinstance(another.child, SimpleService)

    def test_components_are_singletons_by_default(self, temp_project):
        pkg_name, create_file = temp_project
        create_file("components.py", """
            from pico_ioc import component
            @component
            class SimpleService:
                def get_id(self): return id(self)
        """)
        container = pico_ioc.init(pkg_name)
        SimpleService = importlib.import_module(f"{pkg_name}.components").SimpleService
        s1 = container.get(SimpleService)
        s2 = container.get(SimpleService)
        assert s1 is s2
        assert s1.get_id() == s2.get_id()

    def test_get_unregistered_component_raises_error(self, temp_project):
        pkg_name, _ = temp_project
        container = pico_ioc.init(pkg_name)
        class Unregistered: ...
        with pytest.raises(NameError, match="No provider found for key"):
            container.get(Unregistered)

    def test_component_with_custom_name(self, temp_project):
        pkg_name, create_file = temp_project
        create_file("components.py", """
            from pico_ioc import component
            @component(name="custom_name_service")
            class CustomNameService: pass
        """)
        container = pico_ioc.init(pkg_name)
        mdl = importlib.import_module(f"{pkg_name}.components")
        CustomNameService = mdl.CustomNameService
        svc = container.get("custom_name_service")
        assert isinstance(svc, CustomNameService)
        with pytest.raises(NameError):
            container.get(CustomNameService)

class TestFactories:
    def test_factory_provides_component_by_name(self, temp_project):
        pkg_name, create_file = temp_project
        create_file("factories.py", """
            from pico_ioc import factory_component, provides
            @factory_component
            class ServiceFactory:
                @provides(key="complex_service", lazy=True)
                def create_complex_service(self):
                    return "This is a complex service"
        """)
        container = pico_ioc.init(pkg_name)
        svc = container.get("complex_service")
        assert svc == "This is a complex service"

    def test_factory_instantiation_is_lazy_and_singleton(self, temp_project):
        pkg_name, create_file = temp_project
        create_file("factories.py", """
            from pico_ioc import factory_component, provides
            CREATION_COUNTER = {"value": 0}
            @factory_component
            class ServiceFactory:
                @provides(key="complex_service", lazy=True)
                def create_complex_service(self):
                    CREATION_COUNTER["value"] += 1
                    return "This is a complex service"
        """)
        container = pico_ioc.init(pkg_name)
        mdl = importlib.import_module(f"{pkg_name}.factories")
        CREATION_COUNTER = mdl.CREATION_COUNTER
        assert CREATION_COUNTER["value"] == 0
        proxy = container.get("complex_service")
        assert CREATION_COUNTER["value"] == 0
        up = proxy.upper()
        assert up == "THIS IS A COMPLEX SERVICE"
        assert CREATION_COUNTER["value"] == 1
        _ = proxy.lower()
        assert CREATION_COUNTER["value"] == 1
        again = container.get("complex_service")
        assert again is proxy
        assert CREATION_COUNTER["value"] == 1

    def test_provides_static_and_class_methods(self, temp_project):
        pkg_name, create_file = temp_project
        create_file("components.py", """
            from pico_ioc import component
            @component
            class Logger: pass
        """)
        create_file("factories.py", """
            from pico_ioc import factory_component, provides
            from .components import Logger
            @factory_component
            class MainFactory:
                @staticmethod
                @provides("static_result", lazy=True)
                def make_static(logger: Logger):
                    return "static-ok"
                @classmethod
                @provides("class_result")
                def make_class(cls, logger: Logger):
                    return "class-ok"
        """)
        container = pico_ioc.init(pkg_name)
        assert container.get("static_result") == "static-ok"
        assert container.get("class_result") == "class-ok"

class TestResolutionPrecedence:
    def test_resolution_prefers_name_over_type(self, temp_project):
        pkg_name, create_file = temp_project
        create_file("components.py", """
            from pico_ioc import component
            class BaseInterface: ...
            @component
            class NeedsNameVsType:
                def __init__(self, fast_model: BaseInterface):
                    self.model = fast_model
        """)
        create_file("factories.py", """
            from pico_ioc import factory_component, provides
            from .components import BaseInterface
            @factory_component
            class ServiceFactory:
                @provides(key="fast_model")
                def create_fast_model(self): return {"who": "fast"}
                @provides(key=BaseInterface, lazy=True)
                def create_base_interface(self): return {"who": "base"}
        """)
        container = pico_ioc.init(pkg_name)
        mdl = importlib.import_module(f"{pkg_name}.components")
        NeedsNameVsType = mdl.NeedsNameVsType
        comp = container.get(NeedsNameVsType)
        assert comp.model == {"who": "fast"}

    def test_resolution_by_name_only(self, temp_project):
        pkg_name, create_file = temp_project
        create_file("components.py", """
            from pico_ioc import component
            @component
            class NeedsByName:
                def __init__(self, fast_model):
                    self.model = fast_model
        """)
        create_file("factories.py", """
            from pico_ioc import factory_component, provides
            @factory_component
            class ServiceFactory:
                @provides(key="fast_model")
                def create_fast_model(self): return {"who": "fast"}
        """)
        container = pico_ioc.init(pkg_name)
        NeedsByName = importlib.import_module(f"{pkg_name}.components").NeedsByName
        comp = container.get(NeedsByName)
        assert comp.model == {"who": "fast"}

    def test_resolution_fallback_to_type_mro(self, temp_project):
        pkg_name, create_file = temp_project
        create_file("components.py", """
            from pico_ioc import component
            class BaseInterface: ...
            class SubInterface(BaseInterface): ...
            @component
            class NeedsTypeFallback:
                def __init__(self, impl: SubInterface): self.impl = impl
        """)
        create_file("factories.py", """
            from pico_ioc import factory_component, provides
            from .components import BaseInterface
            @factory_component
            class ServiceFactory:
                @provides(key=BaseInterface, lazy=True)
                def create_base_interface(self): return {"who": "base"}
        """)
        container = pico_ioc.init(pkg_name)
        NeedsTypeFallback = importlib.import_module(f"{pkg_name}.components").NeedsTypeFallback
        comp = container.get(NeedsTypeFallback)
        assert comp.impl == {"who": "base"}

    def test_name_precedence_in_provider_params(self, temp_project):
        pkg_name, create_file = temp_project
        create_file("extra.py", """
            from pico_ioc import component, factory_component, provides
            class BaseType: ...
            @component(name="inject_by_name")
            class InjectByName:
                def __init__(self): self.value = "by-name"
            @factory_component
            class NameVsTypeFactory:
                @provides("choose", lazy=True)
                def make(self, inject_by_name, hint: BaseType = None):
                    return inject_by_name.value
        """)
        importlib.invalidate_caches()
        c = pico_ioc.init(pkg_name)
        assert c.get("choose") == "by-name"

class TestDiscoveryAndErrors:
    def test_missing_provider_raises_clear_error(self, temp_project):
        pkg_name, create_file = temp_project
        create_file("service.py", """
            from pico_ioc import component
            class MissingService: pass
            @component
            class MyService:
                def __init__(self, missing_service: MissingService):
                    self.dep = missing_service
        """)
        with pytest.raises(NameError) as ei:
            pico_ioc.init(pkg_name)
        msg = str(ei.value)
        assert "No provider found for key" in msg
        assert "MissingService" in msg

    def test_missing_dependency_in_lazy_component(self, temp_project):
        pkg_name, create_file = temp_project
        create_file("components.py", """
            from pico_ioc import component
            @component(lazy=True)
            class MissingDep:
                def __init__(self, missing): self.missing = missing
        """)
        container = pico_ioc.init(pkg_name)
        MissingDep = importlib.import_module(f"{pkg_name}.components").MissingDep
        proxy = container.get(MissingDep)
        with pytest.raises(NameError, match="No provider found for key"):
            _ = bool(proxy)

    def test_reentrant_access_is_blocked(self, temp_project, caplog):
        pkg_name, _ = temp_project
        root_dir = Path(sys.path[0]) / "test_project"
        (root_dir / "entry.py").write_text(textwrap.dedent("""
            import pico_ioc
            pico_ioc.init("test_project.pkg")
        """))
        caplog.set_level(logging.INFO)
        pico_ioc.init("test_project.entry")
        assert any("re-entrant" in rec.message for rec in caplog.records)

class TestPlugins:
    def test_plugin_hooks_and_binder(self, temp_project):
        pkg_name, create_file = temp_project
        create_file("components.py", """
            from pico_ioc import component
            @component
            class SimpleService: pass
        """)
        calls = []
        class MyPlugin:
            def before_scan(self, package, binder): calls.append("before_scan")
            def visit_class(self, module, cls, binder):
                if cls.__name__ == "SimpleService" and not binder.has("marker"):
                    binder.bind("marker", lambda: True, lazy=False)
            def after_scan(self, package, binder): calls.append("after_scan")
            def after_bind(self, container, binder): calls.append("after_bind")
            def before_eager(self, container, binder): calls.append("before_eager")
            def after_ready(self, container, binder): calls.append("after_ready")
        container = pico_ioc.init(pkg_name, plugins=(MyPlugin(),))
        for expected in ["before_scan", "after_scan", "after_bind", "before_eager", "after_ready"]:
            assert expected in calls
        assert container.get("marker") is True

