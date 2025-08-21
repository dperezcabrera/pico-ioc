# tests/test_proxy_unit.py
import pytest

from pico_ioc.proxy import ComponentProxy


# ---------- helpers ------------------------------------------------------------

class Tracker:
    created = 0

    def __init__(self):
        type(self).created += 1
        self.attr = "init"
        self.calls = 0
        self.entered = False
        self.exited = False
        self.store = {}

    def __call__(self, x):
        self.calls += 1
        return f"called:{x}"

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, exc_type, exc, tb):
        self.exited = True
        return False  # do not suppress


# ---------- tests --------------------------------------------------------------

def test_lazy_instantiation_on_first_attribute_access():
    Tracker.created = 0

    def factory():
        return Tracker()

    p = ComponentProxy(factory)
    assert Tracker.created == 0  # not created yet

    # first touch creates the real object
    assert p.attr == "init"
    assert Tracker.created == 1

    # subsequent touches reuse same instance
    p.attr = "changed"
    assert p.attr == "changed"
    assert Tracker.created == 1


def test_dunder_len_iter_contains_with_list():
    created = {"n": 0}

    def factory():
        created["n"] += 1
        return [1, 2, 3]

    p = ComponentProxy(factory)
    assert created["n"] == 0

    assert len(p) == 3
    assert list(iter(p)) == [1, 2, 3]
    assert 2 in p
    assert created["n"] == 1  # instantiated once

    # reversed delegates too
    assert list(reversed(p)) == [3, 2, 1]
    assert created["n"] == 1


def test_item_get_set_del_with_dict():
    created = {"n": 0}

    def factory():
        created["n"] += 1
        return {"a": 1}

    p = ComponentProxy(factory)
    assert created["n"] == 0

    assert p["a"] == 1
    p["b"] = 2
    assert p["b"] == 2
    del p["a"]
    assert "a" not in p
    assert created["n"] == 1  # single instantiation


def test_math_ops_and_reflected_ops_with_int():
    made = {"n": 0}

    def factory():
        made["n"] += 1
        return 10

    p = ComponentProxy(factory)

    # forward
    assert p + 5 == 15
    assert p - 3 == 7
    assert p * 2 == 20
    assert p // 3 == 3
    assert p % 4 == 2
    assert p ** 2 == 100

    # reflected
    assert 5 + p == 15
    assert 30 - p == 20
    assert 2 * p == 20

    # hash/bool/eq delegate
    assert hash(p) == hash(10)
    assert bool(p) is True
    assert p == 10
    assert made["n"] == 1  # created once


def test_call_delegation_and_repr_str():
    Tracker.created = 0

    def factory():
        return Tracker()

    p = ComponentProxy(factory)

    assert str(p) == str(p._get_real_object())
    assert repr(p) == repr(p._get_real_object())

    out = p("X")
    assert out == "called:X"
    assert p.calls == 1
    # created once
    assert Tracker.created == 1


def test_context_manager_delegation():
    Tracker.created = 0

    def factory():
        return Tracker()

    p = ComponentProxy(factory)

    with p as obj:
        assert obj.entered is True
        obj.attr = "inside"

    assert p.exited is True
    assert p.attr == "inside"  # mutation persisted on real object
    assert Tracker.created == 1


def test_dir_and_getattr_delattr_passthrough():
    def factory():
        return Tracker()

    p = ComponentProxy(factory)

    # dir delegates to real object
    names = dir(p)
    assert "attr" in names and "__class__" in names

    # getattr / setattr / delattr
    assert getattr(p, "attr") == "init"
    setattr(p, "attr", "new")
    assert p.attr == "new"
    delattr(p, "attr")
    with pytest.raises(AttributeError):
        _ = p.attr

def test___class___property_mirrors_real_class_and_affects_isinstance():
    def factory():
        return Tracker()

    p = ComponentProxy(factory)

    # Real Python type is still ComponentProxy
    from pico_ioc.proxy import ComponentProxy as _ProxyType
    assert type(p) is _ProxyType

    # __class__ property mirrors the real object's class
    assert p.__class__ is Tracker

    # Because type.__instancecheck__ consults obj.__class__, this is True
    assert isinstance(p, Tracker) is True

class Mat:
    """Minimal object supporting @ and r@ to test matmul delegation."""
    def __init__(self, val):
        self.val = val

    def __matmul__(self, other):
        right = other.val if hasattr(other, "val") else other
        return ("matmul", self.val, right)

    def __rmatmul__(self, other):
        left = other.val if hasattr(other, "val") else other
        return ("rmatmul", left, self.val)


# -------------------------- tests ---------------------------------------------

def test_true_div_and_reflected_and_divmod():
    calls = {"n": 0}
    def factory():
        calls["n"] += 1
        return 10  # int supports / and divmod

    p = ComponentProxy(factory)

    # true division
    assert p / 4 == pytest.approx(2.5)
    assert 20 / p == pytest.approx(2.0)

    # divmod and reflected divmod
    assert divmod(p, 6) == (1, 4)
    assert divmod(23, p) == (2, 3)

    # still one instantiation
    assert calls["n"] == 1


def test_bitwise_ops_and_reflected():
    calls = {"n": 0}
    def factory():
        calls["n"] += 1
        return 0b0110  # 6

    p = ComponentProxy(factory)

    # forward
    assert (p & 0b0011) == 0b0010
    assert (p | 0b1000) == 0b1110
    assert (p ^ 0b0101) == 0b0011

    # reflected
    assert (0b0011 & p) == 0b0010
    assert (0b1000 | p) == 0b1110
    assert (0b0101 ^ p) == 0b0011

    assert calls["n"] == 1


def test_shift_ops_and_reflected():
    calls = {"n": 0}
    def factory():
        calls["n"] += 1
        return 3

    p = ComponentProxy(factory)

    # forward
    assert (p << 2) == 12
    assert (p >> 1) == 1

    # reflected
    # Python's reflected shift on int returns NotImplemented usually;
    # but our proxy delegates so we only assert forward shifts and ensure single instantiation.
    # For completeness, test reflected via __rlshift__/__rrshift__ with ints:
    class Shiftable:
        def __init__(self, v): self.v = v
        def __lshift__(self, other): return ("L", self.v, other)
        def __rshift__(self, other): return ("R", self.v, other)

    s = Shiftable(5)
    # left operand is Shiftable so its method takes precedence
    assert (s << p) == ("L", 5, 3)
    assert (s >> p) == ("R", 5, 3)

    assert calls["n"] == 1


def test_unary_ops_and_ordered_comparisons():
    calls = {"n": 0}
    def factory():
        calls["n"] += 1
        return -3

    p = ComponentProxy(factory)

    # unary
    assert -p == 3
    assert +p == -3
    assert abs(p) == 3
    assert ~p == 2  # ~(-3) == 2

    # ordered comparisons
    assert p < -2
    assert p <= -3
    assert p > -4
    assert p >= -3

    assert calls["n"] == 1


def test_matmul_and_reflected_matmul():
    calls = {"n": 0}
    def factory():
        calls["n"] += 1
        return Mat(2)

    p = ComponentProxy(factory)

    # forward @
    out1 = p @ 5
    assert out1 == ("matmul", 2, 5)

    # reflected @ (int doesn't implement @)
    out2 = 7 @ p
    assert out2 == ("rmatmul", 7, 2)

    # proxied vs real Mat:
    other = Mat(9)
    assert (p @ other) == ("matmul", 2, 9)
    # Left Mat.__matmul__ sees p has 'val' via delegation, so NOT rmatmul:
    assert (other @ p) == ("matmul", 9, 2)

    assert calls["n"] == 1

