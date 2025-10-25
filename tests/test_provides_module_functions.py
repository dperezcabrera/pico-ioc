# tests/test_provides_module_functions.py
import types
import pytest
from pico_ioc.api import component, provides, init
from pico_ioc.exceptions import ProviderNotFoundError, InvalidBindingError

class Service:
    pass

class Dep:
    pass

class Impl(Service):
    def __init__(self, dep: Dep) -> None:
        self.dep = dep

def build_module_with_module_level_provides():
    m = types.ModuleType("module_level_provides")

    @component
    class MyDep(Dep):
        pass

    @provides(Service)
    def build_service(dep: Dep) -> Service:
        return Impl(dep)

    setattr(m, "MyDep", MyDep)
    setattr(m, "build_service", build_service)
    return m

def build_module_with_string_key():
    m = types.ModuleType("module_level_string_key")

    @provides("cache")
    def build_cache() -> dict:
        return {"ok": True}

    setattr(m, "build_cache", build_cache)
    return m

def build_module_with_profiles():
    m = types.ModuleType("module_level_profiles")

    @provides(Service, conditional_profiles=("prod",))
    def build_service_prod_only() -> Service:
        return Impl(Dep())

    setattr(m, "build_service_prod_only", build_service_prod_only)
    return m

def build_module_with_missing_dependency():
    m = types.ModuleType("module_level_missing_dep")

    class Missing:
        pass

    @provides(Service)
    def build_service(missing: "Missing") -> Service:
        return Impl(Dep())

    setattr(m, "Missing", Missing)
    setattr(m, "build_service", build_service)
    return m

def test_module_level_provides_binds_and_injects_dependency():
    mod = build_module_with_module_level_provides()
    pico = init(mod)
    s = pico.get(Service)
    assert isinstance(s, Impl)
    assert isinstance(s.dep, Dep)

def test_module_level_provides_with_string_key_and_retrieval_by_key():
    mod = build_module_with_string_key()
    pico = init(mod)
    c = pico.get("cache")
    assert isinstance(c, dict)
    assert c.get("ok") is True

def test_module_level_provides_respects_profiles_enabled():
    mod = build_module_with_profiles()
    pico = init(mod, profiles=("prod",))
    s = pico.get(Service)
    assert isinstance(s, Service)

def test_module_level_provides_respects_profiles_disabled():
    mod = build_module_with_profiles()
    pico = init(mod, profiles=("dev",))
    with pytest.raises(ProviderNotFoundError):
        pico.get(Service)

def test_module_level_provides_validation_reports_missing_dependencies():
    mod = build_module_with_missing_dependency()
    with pytest.raises(InvalidBindingError):
        init(mod, validate_only=True)

