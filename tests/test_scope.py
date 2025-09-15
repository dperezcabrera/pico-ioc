# tests/test_scope.py
import types
import pytest
from pico_ioc import component, scope, init, on_missing, conditional, reset

@pytest.fixture(autouse=True)
def clean_state():
    reset()
    yield
    reset()

# --- Filtering and Basic Structure ---

def test_scope_filters_by_tags():
    pkg = types.ModuleType("pkg_scope_tags")
    @component(tags=("a", "common"))
    class ComponentA: ...
    @component(tags=("b", "common"))
    class ComponentB: ...
    pkg.__dict__.update(locals())

    c_include = scope(modules=[pkg], include_tags={"a"}, roots=[ComponentA, ComponentB])
    assert c_include.has(ComponentA) is True
    assert c_include.has(ComponentB) is False
    
    c_exclude = scope(modules=[pkg], exclude_tags={"a"}, roots=[ComponentA, ComponentB])
    assert c_exclude.has(ComponentA) is False
    assert c_exclude.has(ComponentB) is True

def test_scope_with_base_container_and_strict_mode():
    # Base container
    base_pkg = types.ModuleType("base_pkg")
    @component
    class BaseService: pass
    base_pkg.BaseService = BaseService
    base_container = init(base_pkg, reuse=False)
    
    # Scope depends on base
    scope_pkg = types.ModuleType("scope_pkg")
    @component
    class ScopedComponent:
        def __init__(self, base_service: BaseService): self.base_service = base_service
    scope_pkg.ScopedComponent = ScopedComponent

    # With strict=False, it resolves from base
    scoped_container = scope(modules=[scope_pkg], base=base_container, strict=False, lazy=False, roots=[ScopedComponent])
    instance = scoped_container.get(ScopedComponent)
    assert isinstance(instance.base_service, BaseService)

    # With strict=True, it fails
    with pytest.raises(NameError):
        # lazy=False forces eager instantiation, triggering the error inside scope()
        scope(modules=[scope_pkg], base=base_container, strict=True, lazy=False, roots=[ScopedComponent])

# --- Policy Tests in `scope` ---

def test_scope_applies_policy_and_defaults_correctly():
    pkg = types.ModuleType("pkg_scope_policy")
    class MQ: ...
    
    @component 
    @conditional(profiles=["prod"])
    class Kafka(MQ): ...
    
    @component 
    @on_missing(MQ)
    class InMemMQ(MQ): ...
    @component
    class App:
        def __init__(self, mq: MQ): self.mq = mq

    pkg.__dict__.update(locals())

    # With 'prod' profile, scope should choose Kafka
    c_prod = scope(modules=[pkg], roots=[App], profiles=["prod"], lazy=False)
    assert isinstance(c_prod.get(App).mq, Kafka)

    # Without a matching profile, scope should use the @on_missing fallback
    c_dev = scope(modules=[pkg], roots=[App], profiles=["dev"], lazy=False)
    assert isinstance(c_dev.get(App).mq, InMemMQ)
