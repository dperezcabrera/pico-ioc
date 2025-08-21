# tests/test_typing_utils_unit.py
import typing
import pytest

from pico_ioc.typing_utils import evaluated_hints, resolve_annotation_to_type


# ---- Module-scope helpers so module globals are available to evaluated_hints/eval ----

class ModG:
    pass

def f_mod_hints(a: int, b: "ModG") -> None:
    return None


class ModY:
    pass

def f_mod_resolve(a: "ModY"):
    return None


# ---------- evaluated_hints ----------------------------------------------------

def test_evaluated_hints_basic_module_globals():
    hints = evaluated_hints(f_mod_hints)
    assert hints["a"] is int
    assert hints["b"] is ModG


def test_evaluated_hints_uses_owner_cls_locals():
    class Owner:
        class T:
            pass

        def m(self, x: "T"):
            return x

    hints = evaluated_hints(Owner.m, owner_cls=Owner)
    assert hints["x"] is Owner.T


def test_evaluated_hints_forward_ref_builtin_and_typing():
    def f(a: "int", b: "typing.List[int]"):
        return None

    hints = evaluated_hints(f)
    assert hints["a"] is int
    assert getattr(hints["b"], "__origin__", None) is list
    assert hints["b"].__args__ == (int,)


def test_evaluated_hints_is_exception_safe(monkeypatch):
    def f(a: "UnknownType"):
        return None

    # Force typing.get_type_hints to raise to exercise the exception path.
    monkeypatch.setattr(typing, "get_type_hints", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    hints = evaluated_hints(f)
    assert hints == {}  # falls back to empty dict


# ---------- resolve_annotation_to_type ----------------------------------------

def test_resolve_annotation_to_type_non_str_returns_input():
    assert resolve_annotation_to_type(int, func=test_resolve_annotation_to_type_non_str_returns_input) is int


def test_resolve_annotation_to_type_uses_module_globals():
    out = resolve_annotation_to_type("ModY", func=f_mod_resolve, owner_cls=None)
    assert out is ModY


def test_resolve_annotation_to_type_uses_owner_cls_locals():
    class Owner:
        class Z:
            pass

        def m(self, v: "Z"):
            return v

    out = resolve_annotation_to_type("Z", func=Owner.m, owner_cls=Owner)
    assert out is Owner.Z


def test_resolve_annotation_to_type_handles_qualified_typing():
    def f(a: "typing.Dict[str, int]"):
        return None

    out = resolve_annotation_to_type("typing.Dict[str, int]", func=f, owner_cls=None)
    assert getattr(out, "__origin__", None) is dict
    assert out.__args__ == (str, int)


def test_resolve_annotation_to_type_on_eval_failure_returns_original():
    def f(a: "NotDefinedAnywhere"):
        return None

    out = resolve_annotation_to_type("NotDefinedAnywhere", func=f, owner_cls=None)
    assert out == "NotDefinedAnywhere"

