# pico_ioc/_state.py
from contextvars import ContextVar
from typing import Optional
from contextlib import contextmanager

_scanning: ContextVar[bool] = ContextVar("pico_scanning", default=False)
_resolving: ContextVar[bool] = ContextVar("pico_resolving", default=False)

_container = None
_root_name: Optional[str] = None

@contextmanager
def scanning_flag():
    """Context manager: mark scanning=True within the block."""
    tok = _scanning.set(True)
    try:
        yield
    finally:
        _scanning.reset(tok)
