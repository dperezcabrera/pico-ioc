# tests/test_resolver.py

import types
import pytest

from pico_ioc.container import PicoContainer
from pico_ioc.resolver import Resolver
from pico_ioc._state import _resolving


# ----- Test helpers -----

class Base: ...
class Derived(Base): ...
class Unrelated: ...

def bind_value(container: PicoContainer, key, value):
    """
    Convenience: bind a key to a fixed value (non-lazy).
    PicoContainer.bind expects a provider callable.
    """
    container.bind(key, lambda: value, lazy=False)


# ----- Tests -----

def test_resolution_order_prefers_param_name_over_annotation_and_mro():
    """
    Resolution precedence in _resolve_param:
    1) direct name key
    2) annotation exact key
    3) MRO (parent classes)
    4) str(name)
    5) fallback -> container.get(key) with name/ann (shouldn't be reached here)
    """
    c = PicoContainer()
    r = Resolver(c)

    # For param name 'dep' with annotation Derived:
    bind_value(c, Derived, "by_ann")         # 2) exact annotation
    bind_value(c, Base, "by_mro")            # 3) via MRO
    bind_value(c, str("dep"), "by_str_name") # 4) str(name)
    bind_value(c, "dep", "by_name") # same as prev (kept)
    
    def fn(dep: Derived):  # noqa: ANN001 - annotations intentional
        return dep

    kwargs = r.kwargs_for_callable(fn)
    assert kwargs["dep"] == "by_name"


def test_resolution_uses_annotation_when_name_missing():
    c = PicoContainer()
    r = Resolver(c)

    bind_value(c, Derived, "by_ann")
    bind_value(c, Base, "by_mro_fallback_should_not_be_used")

    def fn(dep: Derived):
        return dep

    kwargs = r.kwargs_for_callable(fn)
    assert kwargs["dep"] == "by_ann"


def test_resolution_uses_mro_when_no_name_or_annotation_binding():
    c = PicoContainer()
    r = Resolver(c)

    bind_value(c, Base, "by_mro")

    def fn(dep: Derived):
        return dep

    kwargs = r.kwargs_for_callable(fn)
    assert kwargs["dep"] == "by_mro"


def test_resolution_uses_str_name_when_no_name_ann_or_mro():
    c = PicoContainer()
    r = Resolver(c)

    bind_value(c, "dep", "by_str_name")

    def fn(dep: Unrelated):  # no binding for Unrelated nor its MRO
        return dep

    kwargs = r.kwargs_for_callable(fn)
    assert kwargs["dep"] == "by_str_name"


def test_missing_provider_raises_nameerror_with_proper_key_in_message():
    """
    When no provider and no default, Resolver.kwargs_for_callable should raise
    NameError with the missing key: the annotation if present, else the param name.
    """
    c = PicoContainer()
    r = Resolver(c)

    def fn(dep: Derived):
        return dep

    with pytest.raises(NameError) as ei:
        r.kwargs_for_callable(fn)
    # The message should include the annotation object (Derived) or its name
    assert "No provider found for key" in str(ei.value)
    assert "Derived" in str(ei.value)


def test_defaulted_parameter_is_skipped_when_provider_missing():
    """
    If a parameter has a default value and there's no provider, it should be
    skipped (not included in the kwargs dict) rather than raising.
    """
    c = PicoContainer()
    r = Resolver(c)

    fn = lambda dep=None: dep  # noqa: E731 - intentional inline fn
    kwargs = r.kwargs_for_callable(fn)
    assert "dep" not in kwargs

