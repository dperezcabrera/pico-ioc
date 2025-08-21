# tests/test_container_unit.py
import pytest

from pico_ioc.container import PicoContainer, Binder
from pico_ioc import _state


# ---------------------------- PicoContainer -----------------------------------

def test_bind_and_get_caches_singleton():
    c = PicoContainer()
    calls = {"n": 0}

    def provider():
        calls["n"] += 1
        return object()

    c.bind("k", provider, lazy=False)

    a = c.get("k")
    b = c.get("k")

    assert a is b                    # same singleton
    assert calls["n"] == 1           # provider called once
    assert c.has("k") is True        # presence reported


def test_missing_key_raises_nameerror():
    c = PicoContainer()
    with pytest.raises(NameError):
        _ = c.get("nope")


def test_eager_instantiate_all_instantiates_only_non_lazy():
    c = PicoContainer()
    calls = {"eager": 0, "lazy": 0}

    def eager_p():
        calls["eager"] += 1
        return ("eager", calls["eager"])

    def lazy_p():
        calls["lazy"] += 1
        return ("lazy", calls["lazy"])

    c.bind("eager_key", eager_p, lazy=False)
    c.bind("lazy_key", lazy_p, lazy=True)

    c.eager_instantiate_all()

    # non-lazy was instantiated
    assert c.get("eager_key") == ("eager", 1)
    # lazy provider was NOT called during eager; first get triggers it
    assert calls["lazy"] == 0
    assert c.get("lazy_key") == ("lazy", 1)
    # further gets remain cached
    assert c.get("lazy_key") == ("lazy", 1)
    assert calls["lazy"] == 1


def test_reentrant_guard_raises_during_scan_only():
    c = PicoContainer()
    c.bind("x", lambda: object(), lazy=False)

    # scanning=True and resolving=False -> blocked
    tok_scan = _state._scanning.set(True)
    try:
        # ensure resolving is False (default)
        tok_resolve = None
        try:
            if _state._resolving.get():
                tok_resolve = _state._resolving.set(False)
            with pytest.raises(RuntimeError) as exc:
                _ = c.get("x")
            assert "re-entrant container access during scan" in str(exc.value)
        finally:
            if tok_resolve is not None:
                _state._resolving.reset(tok_resolve)
    finally:
        _state._scanning.reset(tok_scan)


def test_access_allowed_when_resolving_even_if_scanning():
    c = PicoContainer()
    calls = {"n": 0}

    def provider():
        calls["n"] += 1
        return object()

    c.bind("y", provider, lazy=False)

    # scanning=True but resolving=True -> allowed
    tok_scan = _state._scanning.set(True)
    tok_res = _state._resolving.set(True)
    try:
        obj1 = c.get("y")
        obj2 = c.get("y")
        assert obj1 is obj2
        assert calls["n"] == 1
    finally:
        _state._resolving.reset(tok_res)
        _state._scanning.reset(tok_scan)


def test_has_reports_singleton_after_first_get():
    c = PicoContainer()
    c.bind("k", lambda: "v", lazy=False)
    assert c.has("k") is True       # provider present
    _ = c.get("k")
    assert c.has("k") is True       # still true after caching


# ------------------------------- Binder ---------------------------------------

def test_binder_proxies_bind_has_get():
    c = PicoContainer()
    b = Binder(c)

    made = object()
    b.bind("key", lambda: made, lazy=False)

    assert b.has("key") is True
    assert b.get("key") is made

