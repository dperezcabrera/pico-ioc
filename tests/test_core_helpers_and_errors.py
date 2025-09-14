# tests/test_core_helpers_and_errors.py
from __future__ import annotations
import pytest
from typing import List, Tuple, Annotated

from pico_ioc import init, component
from pico_ioc.container import _requires_collection_of_base
from pico_ioc.scanner import _as_module


# --- Test classes defined at module level for correct type hint resolution ---

class MissingComponent: ...

@component
class ComponentC:
    def __init__(self, missing: MissingComponent): ...

@component
class ComponentB:
    def __init__(self, c: ComponentC): ...

@component
class ComponentA:
    def __init__(self, b: ComponentB): ...


def test_resolver_error_message_shows_full_dependency_chain(tmp_path):
    # Verifies that NameError includes the full chain of dependencies.
    import types

    pkg = types.ModuleType("pkg_chain_err")
    # Assign the module-level classes to the dynamic module.
    pkg.ComponentA = ComponentA
    pkg.ComponentB = ComponentB
    pkg.ComponentC = ComponentC

    with pytest.raises(NameError) as exc_info:
        init(pkg)

    # The error message should trace the path to the missing dependency.
    msg = str(exc_info.value)
    assert "No provider found for key" in msg
    assert "MissingComponent" in msg
    assert "(required by ComponentA.__init__.b -> ComponentB.__init__.c -> ComponentC.__init__.missing)" in msg


def test_scanner_as_module_raises_on_invalid_type():
    # Verifies that _as_module raises TypeError for unsupported input types.
    with pytest.raises(TypeError, match="must be a module or importable package name"):
        _as_module(123) # Pass an integer instead of a module or string.


# --- Tests for _requires_collection_of_base ---

class Base: ...
class Unrelated: ...

class ConsumerNormal:
    def __init__(self, dep: Base): ...

class ConsumerList:
    def __init__(self, deps: List[Base]): ...

class ConsumerTuple:
    def __init__(self, deps: Tuple[Base, ...]): ...

class ConsumerAnnotated:
    def __init__(self, deps: List[Annotated[Base, "some-qualifier"]]): ...

class ConsumerUnrelated:
    def __init__(self, deps: List[Unrelated]): ...


@pytest.mark.parametrize("consumer_cls, base_type, expected", [
    (ConsumerNormal, Base, False),
    (ConsumerList, Base, True),
    (ConsumerTuple, Base, True),
    (ConsumerAnnotated, Base, True),
    (ConsumerUnrelated, Base, False),
    (ConsumerList, Unrelated, False),
])
def test_requires_collection_of_base(consumer_cls, base_type, expected):
    # Verifies the helper that detects circular dependencies in collection injections.
    result = _requires_collection_of_base(consumer_cls, base_type)
    assert result is expected
