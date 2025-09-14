# tests/test_policy_and_container_helpers.py
import os
import pytest
from typing import Protocol

from pico_ioc.decorators import CONDITIONAL_META
from pico_ioc.policy import _has_flag, _get_meta, _conditional_active
from pico_ioc.container import _is_compatible


# --- Test Helpers for Introspection ---

FLAG_A = "_flag_a_for_test"
META_B = "_meta_b_for_test"
META_B_VAL = {"value": "B"}

def standalone_func(): ...
setattr(standalone_func, FLAG_A, True)
setattr(standalone_func, META_B, META_B_VAL)

class MethodHost:
    def regular_method(self): ...
    setattr(regular_method, FLAG_A, True)
    setattr(regular_method, META_B, META_B_VAL)

    def get_closure(self):
        # Create a closure over the method
        def provider():
            return self.regular_method()
        return provider

# --- Tests for policy.py helpers ---

@pytest.mark.parametrize("obj, expected_flag, expected_meta", [
    (standalone_func, True, META_B_VAL),
    (MethodHost().regular_method, True, META_B_VAL),
])
def test_introspection_helpers(obj, expected_flag, expected_meta):
    # Verifies that _has_flag and _get_meta can read metadata from functions and methods.
    assert _has_flag(obj, FLAG_A) is expected_flag
    assert _get_meta(obj, META_B) == expected_meta


def test_conditional_active_with_combined_conditions(monkeypatch):
    # Verifies the AND logic for multiple conditions in @conditional.
    class Target: ...

    # Condition requires both a profile AND an environment variable.
    meta = {
        "profiles": ("prod",),
        "require_env": ("DATABASE_URL",),
        "predicate": None
    }
    setattr(Target, CONDITIONAL_META, meta)

    # Case 1: Neither condition met
    assert _conditional_active(Target, profiles=["dev"]) is False

    # Case 2: Only profile condition met
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert _conditional_active(Target, profiles=["prod"]) is False

    # Case 3: Only env var condition met
    monkeypatch.setenv("DATABASE_URL", "some-url")
    assert _conditional_active(Target, profiles=["dev"]) is False

    # Case 4: Both conditions met -> active
    monkeypatch.setenv("DATABASE_URL", "some-url")
    assert _conditional_active(Target, profiles=["prod"]) is True


# --- Tests for container.py helpers ---

class CompatibleProtocol(Protocol):
    def method_a(self) -> int: ...
    property_b: str

class Implementation:
    def method_a(self) -> int:
        return 1
    property_b = "test"

class AlmostImplementation: # Missing property_b
    def method_a(self) -> int:
        return 1

class NotAnImplementation:
    def other_method(self) -> bool:
        return False

def test_is_compatible_for_protocols():
    # Verifies structural checks for Protocol types.
    assert _is_compatible(Implementation, CompatibleProtocol) is True
    assert _is_compatible(AlmostImplementation, CompatibleProtocol) is False
    assert _is_compatible(NotAnImplementation, CompatibleProtocol) is False


def test_is_compatible_for_inheritance():
    # Verifies standard subclass checks.
    class Base: ...
    class Derived(Base): ...
    class Unrelated: ...

    assert _is_compatible(Derived, Base) is True
    assert _is_compatible(Base, Derived) is False
    assert _is_compatible(Unrelated, Base) is False
