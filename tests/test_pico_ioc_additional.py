import sys
import logging
import pytest
import pico_ioc

@pytest.fixture
def ext_project(tmp_path):
    """
    Build a real importable package layout:

    <tmp>/
      extproj/
        __init__.py
        pkg/
          __init__.py
          components.py
          factories.py
          more_factories.py

    And put <tmp> on sys.path so 'import extproj.pkg' works.
    """
    project_root = tmp_path                  # parent dir that must be on sys.path
    extpkg_root = project_root / "extproj"   # top-level package
    pkg = extpkg_root / "pkg"                # subpackage we pass to pico_ioc.init

    # Create directories
    extpkg_root.mkdir()
    pkg.mkdir()

    # Make <tmp> importable root
    sys.path.insert(0, str(project_root))

    # Mark both 'extproj' and 'extproj.pkg' as packages
    (extpkg_root / "__init__.py").write_text("")
    (pkg / "__init__.py").write_text("")

    # Components
    (pkg / "components.py").write_text(
        """
from pico_ioc import component

@component
class AppConfig:
    def __init__(self):
        self.name = "ext-config"
        self.version = 1

@component
class Logger:
    def __init__(self):
        self.logs = []
    def info(self, msg):
        self.logs.append(("INFO", msg))

@component
class Counter:
    def __init__(self):
        self.value = 0

@component
class NeedsListLike:
    def __init__(self, data_list):
        self.data_list = data_list
"""
    )

    # Factories
    (pkg / "factories.py").write_text(
        """
from pico_ioc import factory_component, provides
from .components import AppConfig, Logger, Counter

CONSTRUCTOR_HITS = {"value": 0}
EAGER_HITS = {"value": 0}
LAZY_HITS = {"value": 0}
STATIC_HITS = {"value": 0}
CLASS_HITS = {"value": 0}

@factory_component
class MainFactory:
    def __init__(self, app_config: AppConfig, logger: Logger):
        CONSTRUCTOR_HITS["value"] += 1
        self.app_config = app_config
        self.logger = logger

    @provides("service_info")  # eager
    def make_service_info(self, logger: Logger):
        EAGER_HITS["value"] += 1
        logger.info("building service_info")
        return {"name": self.app_config.name, "version": self.app_config.version}

    @provides("data_list", lazy=True)
    def make_data_list(self, counter: Counter):
        LAZY_HITS["value"] += 1
        return [counter.value, counter.value + 1, counter.value + 2]

    @staticmethod
    @provides("static_result", lazy=True)
    def make_static(logger: Logger):
        STATIC_HITS["value"] += 1
        logger.info("static called")
        return "static-ok"

    @classmethod
    @provides("class_result")
    def make_class(cls, logger: Logger):
        CLASS_HITS["value"] += 1
        logger.info("class called")
        return "class-ok"

@factory_component
class ErrorFactory:
    @provides("will_fail", lazy=True)
    def make_will_fail(self, missing_dep):
        return 123  # never reached
"""
    )

    # Another factory module with an eager provider
    (pkg / "more_factories.py").write_text(
        """
from pico_ioc import factory_component, provides

EAGER_ON_INIT_HITS = {"value": 0}

@factory_component
class BootFactory:
    @provides("boot_marker")  # eager
    def make_boot_marker(self):
        EAGER_ON_INIT_HITS["value"] += 1
        return {"boot": True}
"""
    )

    # Yield the subpackage name passed to pico_ioc.init
    yield "extproj.pkg"

    # Teardown
    sys.path.pop(0)
    pico_ioc._container = None
    to_del = [m for m in list(sys.modules) if m == "extproj" or m.startswith("extproj.")]
    for m in to_del:
        sys.modules.pop(m, None)

def test_name_precedence_in_provider_params(ext_project):
    """
    If both a name-based binding and a type-based binding exist, the provider DI
    should prefer the name-based one (matching Pico's resolve_param behavior).
    """
    import importlib, pathlib, sys as _sys
    base = pathlib.Path(_sys.path[0]) / "extproj" / "pkg"

    # Create a component bound by NAME and a factory that asks for both name and type.
    (base / "extra.py").write_text(
        '''
from pico_ioc import component, factory_component, provides

class BaseType: ...
class Impl(BaseType): ...

@component(name="inject_by_name")
class InjectByName:
    def __init__(self):
        self.value = "by-name"

@factory_component
class NameVsTypeFactory:
    @provides("choose", lazy=True)
    def make(self, inject_by_name, hint: BaseType = None):
        # Name should win over type when both could match.
        return inject_by_name.value
'''
    )
    importlib.invalidate_caches()

    # Force a fresh scan: reset container and unload package modules
    import pico_ioc
    pico_ioc._container = None
    for m in list(_sys.modules):
        if m == "extproj" or m.startswith("extproj."):
            _sys.modules.pop(m, None)

    # Re-init so the scanner picks up extra.py
    c = pico_ioc.init(ext_project)
    assert c.get("choose") == "by-name"

