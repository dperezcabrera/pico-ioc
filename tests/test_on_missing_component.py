import types
from pico_ioc import init, scope, component
from pico_ioc.decorators import on_missing, conditional, primary

def test_on_missing_component_applies_when_no_binding():
    pkg = types.ModuleType("pkg_omc1")

    class RepoBase: ...
    @component
    @on_missing(RepoBase, priority=5)
    class InMemoryRepo(RepoBase): ...
    pkg.RepoBase = RepoBase
    pkg.InMemoryRepo = InMemoryRepo

    c = init(pkg, plugins=())
    r = c.get(RepoBase)
    assert isinstance(r, InMemoryRepo)

def test_on_missing_component_priority_wins():
    pkg = types.ModuleType("pkg_omc2")

    class RepoBase: ...
    @component
    @on_missing(RepoBase, priority=1)
    class Low(RepoBase): ...
    @component
    @on_missing(RepoBase, priority=10)
    class High(RepoBase): ...
    pkg.RepoBase = RepoBase
    pkg.Low = Low
    pkg.High = High

    c = init(pkg, plugins=())
    r = c.get(RepoBase)
    assert isinstance(r, High)

def test_on_missing_applied_in_scope_too():
    pkg = types.ModuleType("pkg_omc3")

    class RepoBase: ...
    @component
    @on_missing(RepoBase, priority=1)
    class DefaultRepo(RepoBase): ...
    pkg.RepoBase = RepoBase
    pkg.DefaultRepo = DefaultRepo

    c = scope(modules=[pkg], roots=[RepoBase], strict=True, lazy=True)
    r = c.get(RepoBase)
    assert isinstance(r, DefaultRepo)

