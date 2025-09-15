# tests/test_fingerprint_public.py
import types
import pytest
from pico_ioc import init, reset, component, container_fingerprint

def test_fingerprint_exposed_and_changes_on_params(monkeypatch):
    # FIX: Patch the function in the builder.
    monkeypatch.setattr("pico_ioc.builder.scan_and_configure", lambda *a, **k: (0, 0, []))

    fp1 = container_fingerprint()
    assert fp1 is None

    c1 = init("pkgA", profiles=["dev"], auto_scan=("lib.x",), reuse=True)
    fp_after_first = container_fingerprint()
    assert isinstance(fp_after_first, tuple)

    c2 = init("pkgA", profiles=["prod"], auto_scan=("lib.x",), reuse=True)
    fp_after_second = container_fingerprint()
    assert fp_after_second != fp_after_first

def test_fingerprint_resets_on_reset(monkeypatch):
    # FIX: Patch the function in the builder.
    monkeypatch.setattr("pico_ioc.builder.scan_and_configure", lambda *a, **k: (0, 0, []))
    _ = init("pkgZ")
    assert container_fingerprint() is not None
    reset()
    assert container_fingerprint() is None
