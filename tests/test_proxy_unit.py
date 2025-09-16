# tests/test_proxy_unit.py
import pytest
import operator

from pico_ioc.proxy import ComponentProxy

# ----- Helpers (unchanged) -----

class Tracker:
    """Helper class to track instance creation and calls."""
    created = 0

    def __init__(self):
        type(self).created += 1
        self.attr = "init"
        self.calls = 0
        self.entered = False
        self.exited = False

    def __call__(self, x):
        self.calls += 1
        return f"called:{x}"

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, exc_type, exc, tb):
        self.exited = True
        return False

class Mat:
    """Helper class to test the matrix multiplication operator (@)."""
    def __init__(self, val):
        self.val = val

    def __matmul__(self, other):
        right = getattr(other, "val", other)
        return "matmul", self.val, right

    def __rmatmul__(self, other):
        left = getattr(other, "val", other)
        return "rmatmul", left, self.val

# ----- Pytest Fixture -----

@pytest.fixture(autouse=True)
def reset_tracker():
    """
    A fixture that runs automatically before each test in this module.
    It resets the creation counter of the Tracker class.
    """
    Tracker.created = 0

# ----- Refactored Tests -----

class TestComponentProxy:
    """Groups all unit tests for ComponentProxy."""

    def test_lazy_instantiation(self):
        """The real object is only created on first access."""
        proxy = ComponentProxy(Tracker)
        assert Tracker.created == 0, "Should not be created on proxy initialization."

        # First access
        assert proxy.attr == "init"
        assert Tracker.created == 1, "Should be created on first access."

        # Subsequent accesses
        proxy.attr = "changed"
        assert Tracker.created == 1, "Should not be created again."
        assert proxy._get_real_object().attr == "changed"

    def test_class_property_and_isinstance(self):
        """The proxy mimics the real object's class, affecting isinstance."""
        proxy = ComponentProxy(Tracker)
        
        # The proxy's actual type does not change
        assert type(proxy) is ComponentProxy
        
        # But `__class__` and `isinstance` are delegated
        assert proxy.__class__ is Tracker
        assert isinstance(proxy, Tracker)

    def test_attribute_and_dir_delegation(self):
        """Delegates __getattr__, __setattr__, __delattr__, and __dir__."""
        proxy = ComponentProxy(Tracker)
        
        assert "attr" in dir(proxy)
        assert getattr(proxy, "attr") == "init"
        
        setattr(proxy, "attr", "new")
        assert proxy.attr == "new"
        
        delattr(proxy, "attr")
        with pytest.raises(AttributeError):
            _ = proxy.attr

    def test_string_and_repr_delegation(self):
        """Delegates __str__ and __repr__."""
        proxy = ComponentProxy(Tracker)
        real_obj = proxy._get_real_object()
        
        assert str(proxy) == str(real_obj)
        assert repr(proxy) == repr(real_obj)

    def test_call_delegation(self):
        """Delegates __call__."""
        proxy = ComponentProxy(Tracker)
        assert proxy("X") == "called:X"
        assert proxy.calls == 1
        assert Tracker.created == 1

    def test_context_manager_delegation(self):
        """Delegates __enter__ and __exit__."""
        proxy = ComponentProxy(Tracker)
        with proxy as p_obj:
            assert p_obj.entered is True
            p_obj.attr = "inside"
        
        assert proxy.exited is True
        assert proxy.attr == "inside"
        assert Tracker.created == 1

    def test_container_dunders_delegation(self):
        """Delegates container dunders like __len__, __iter__, etc."""
        proxy = ComponentProxy(lambda: [1, 2, 3])
        assert len(proxy) == 3
        assert list(iter(proxy)) == [1, 2, 3]
        assert 2 in proxy
        assert list(reversed(proxy)) == [3, 2, 1]

    def test_item_dunders_delegation(self):
        """Delegates item access dunders like __getitem__."""
        proxy = ComponentProxy(lambda: {"a": 1})
        assert proxy["a"] == 1
        proxy["b"] = 2
        assert proxy["b"] == 2
        del proxy["a"]
        assert "a" not in proxy

    @pytest.mark.parametrize("op, operand, expected", [
        (operator.lt, 11, True), (operator.le, 10, True),
        (operator.gt, 9, True), (operator.ge, 11, False),
        (operator.eq, 10, True), (operator.ne, 11, True),
    ])
    def test_comparison_operators(self, op, operand, expected):
        """Tests comparison operators in a parameterized way."""
        proxy = ComponentProxy(lambda: 10)
        assert op(proxy, operand) is expected
        assert Tracker.created == 0 # Tracker is not used here

    @pytest.mark.parametrize("op, expected", [
        (operator.neg, 10), (operator.pos, -10),
        (abs, 10), (operator.invert, 9),
    ])
    def test_unary_operators(self, op, expected):
        """Tests unary operators in a parameterized way."""
        proxy = ComponentProxy(lambda: -10)
        assert op(proxy) == expected

    @pytest.mark.parametrize("op, left, right, expected", [
        (operator.add, 10, 5, 15), (operator.sub, 10, 3, 7),
        (operator.mul, 10, 2, 20), (operator.truediv, 10, 4, 2.5),
        (operator.floordiv, 10, 3, 3), (operator.mod, 10, 4, 2),
        (pow, 10, 2, 100), (operator.and_, 0b1100, 0b1010, 0b1000),
        (operator.or_, 0b1100, 0b1010, 0b1110), (operator.xor, 0b1100, 0b1010, 0b0110),
        (operator.lshift, 3, 2, 12), (operator.rshift, 12, 1, 6),
        (operator.matmul, Mat(2), Mat(5), ("matmul", 2, 5)),
    ])
    def test_binary_operators(self, op, left, right, expected):
        """Tests binary operators in a parameterized way (e.g., proxy + val)."""
        proxy = ComponentProxy(lambda: left)
        assert proxy._get_real_object() is not None # Force creation
        result = op(proxy, right)
        assert result == expected

    @pytest.mark.parametrize("op, left, right, expected", [
        (operator.add, 5, 10, 15), (operator.sub, 12, 10, 2),
        (operator.mul, 2, 10, 20), (operator.truediv, 25, 10, 2.5),
        (operator.matmul, Mat(7), Mat(2), ("matmul", 7, 2)), # Note: left-hand __matmul__ takes precedence
    ])
    def test_reflected_binary_operators(self, op, left, right, expected):
        """Tests reflected binary operators (e.g., val + proxy)."""
        proxy = ComponentProxy(lambda: right)
        assert proxy._get_real_object() is not None # Force creation
        result = op(left, proxy)
        assert result == expected
