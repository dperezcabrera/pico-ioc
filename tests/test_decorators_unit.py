# tests/test_decorators_unit.py
import types
import pytest

from pico_ioc.decorators import (
    component,
    factory_component,
    provides,
    COMPONENT_FLAG,
    COMPONENT_KEY,
    COMPONENT_LAZY,
    FACTORY_FLAG,
    PROVIDES_KEY,
    PROVIDES_LAZY,
)


# --------------------- component ----------------------------------------------

def test_component_simple_usage_sets_flags_and_key_is_class():
    @component
    class A:
        pass

    assert getattr(A, COMPONENT_FLAG) is True
    assert getattr(A, COMPONENT_KEY) is A
    assert getattr(A, COMPONENT_LAZY) is False  # default


def test_component_with_args_custom_name_and_lazy_bool_coercion():
    @component(name="svc_name", lazy=1)  # non-bool truthy should coerce to True
    class B:
        pass

    assert getattr(B, COMPONENT_FLAG) is True
    assert getattr(B, COMPONENT_KEY) == "svc_name"
    assert getattr(B, COMPONENT_LAZY) is True


def test_component_accepts_non_string_key_objects():
    key_obj = object()

    @component(name=key_obj, lazy=False)
    class C:
        pass

    assert getattr(C, COMPONENT_KEY) is key_obj


def test_component_returns_same_class_object_identity():
    class D:
        pass

    D2 = component(D)
    assert D2 is D
    assert getattr(D, COMPONENT_FLAG) is True


# --------------------- factory_component --------------------------------------

def test_factory_component_sets_flag_and_preserves_class_identity():
    class F:
        pass

    F2 = factory_component(F)
    assert F2 is F
    assert getattr(F, FACTORY_FLAG) is True


# --------------------- provides ------------------------------------------------

def test_provides_sets_metadata_on_wrapper_and_wraps_preserves_attrs():
    def original(x):  # noqa: ARG001
        """docstring-marker"""
        return "ok"

    wrapped = provides("keyX", lazy=True)(original)

    # wrapper must be callable and return original result
    assert callable(wrapped)
    assert wrapped(1) == "ok"

    # metadata set on the wrapper
    assert getattr(wrapped, PROVIDES_KEY) == "keyX"
    assert getattr(wrapped, PROVIDES_LAZY) is True

    # functools.wraps should preserve name/module/doc
    assert wrapped.__name__ == original.__name__
    assert wrapped.__doc__ == original.__doc__
    assert wrapped.__module__ == original.__module__


def test_provides_on_method_keeps_binding_and_metadata():
    class G:
        def __init__(self, tag):
            self.tag = tag

        @provides("made", lazy=False)
        def make(self, prefix: str = ""):
            return f"{prefix}{self.tag}"

    g = G("X")
    # The attribute on the function object is attached to the wrapper stored on the class
    func_obj = G.__dict__["make"]
    assert getattr(func_obj, PROVIDES_KEY) == "made"
    assert getattr(func_obj, PROVIDES_LAZY) is False

    # Bound method call still works
    assert g.make(prefix=">") == ">X"


def test_provides_lazy_flag_is_bool_coerced():
    def f():
        return 123

    w = provides("k", lazy=42)(f)  # truthy -> True
    assert getattr(w, PROVIDES_LAZY) is True


# --------------------- integration sanity -------------------------------------

def test_component_and_provides_can_coexist_in_factory_pattern():
    @component
    class Dep:
        pass

    @factory_component
    class Factory:
        @provides(Dep)  # providing by type key is allowed metadata-wise
        def build(self):
            return Dep()

    # Pure decorator layer test: flags/keys are present
    assert getattr(Dep, COMPONENT_FLAG) is True
    assert getattr(Dep, COMPONENT_KEY) is Dep
    assert getattr(Factory, FACTORY_FLAG) is True
    assert getattr(Factory.__dict__["build"], PROVIDES_KEY) is Dep

