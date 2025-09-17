# tests/conftest.py
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pytest
from pico_ioc import reset

@pytest.fixture(autouse=True)
def clean_state():
    """Ensures a clean global state before and after each test."""
    reset()
    yield
    reset()

@pytest.fixture
def noop_scan(monkeypatch):
    """Fixture to mock the scanner so it does nothing."""
    monkeypatch.setattr("pico_ioc.builder.scan_and_configure", lambda *a, **k: (0, 0, []))
