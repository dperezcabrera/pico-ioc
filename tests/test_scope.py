# tests/test_scope.py
import types
import pytest
from pico_ioc import component, scope, init, on_missing, conditional

# --- Filtering and Basic Structure ---

def test_scope_filters_by_tags():
    """Tests that include_tags and exclude_tags filter components correctly."""
    pkg = types.ModuleType("pkg_scope_tags")

    @component(tags=("a", "common"))
    class ComponentA: ...
    @component(tags=("b", "common"))
    class ComponentB: ...
    pkg.__dict__.update(locals())

    # Include only 'a'
    c_include = scope(modules=[pkg], include_tags={"a"}, roots=[ComponentA, ComponentB])
    assert c_include.has(ComponentA) is True
    assert c_include.has(ComponentB) is False
    
    # Exclude 'a'
    c_exclude = scope(modules=[pkg], exclude_tags={"a"}, roots=[ComponentA, ComponentB])
    assert c_exclude.has(ComponentA) is False
    assert c_exclude.has(ComponentB) is True

def test_scope_with_base_container_and_strict_mode():
    """Tests dependency resolution from a base container."""
    # Base container with a service
    base_pkg = types.ModuleType("base_pkg")
    @component
    class BaseService: pass
    base_pkg.BaseService = BaseService
    base_container = init(base_pkg)
    
    # Scope that depends on the base service
    scope_pkg = types.ModuleType("scope_pkg")
    @component
    class ScopedComponent:
        def __init__(self, base_service: BaseService):
            self.base_service = base_service
    scope_pkg.ScopedComponent = ScopedComponent

    # With strict=False, dependency is resolved from the base container
    scoped_container = scope(modules=[scope_pkg], base=base_container, strict=False, roots=[ScopedComponent])
    instance = scoped_container.get(ScopedComponent)
    assert isinstance(instance.base_service, BaseService)

    # With strict=True, dependency is not found in the scope and fails
    with pytest.raises(NameError):
        strict_scope = scope(modules=[scope_pkg], base=base_container, strict=True, roots=[ScopedComponent])
        _ = strict_scope.get(ScopedComponent)

# --- Policy Tests in `scope` ---

def test_scope_applies_policy_and_defaults_correctly():
    """Verifies that scope also uses the @on_missing and @conditional logic."""
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
    c_prod = scope(modules=[pkg], roots=[App], profiles=["prod"])
    assert isinstance(c_prod.get(App).mq, Kafka)

    # Without a matching profile, scope should use the @on_missing fallback
    c_dev = scope(modules=[pkg], roots=[App], profiles=["dev"])
    assert isinstance(c_dev.get(App).mq, InMemMQ)
