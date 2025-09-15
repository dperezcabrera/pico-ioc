# pico_ioc/_state.py
from contextvars import ContextVar
from typing import Optional
from contextlib import contextmanager

_scanning: ContextVar[bool] = ContextVar("pico_scanning", default=False)
_resolving: ContextVar[bool] = ContextVar("pico_resolving", default=False)

_container = None
_root_name: Optional[str] = None
_fingerprint: Optional[tuple] = None
_fp_observed: bool = False

@contextmanager
def scanning_flag():
    """Context manager: mark scanning=True within the block."""
    tok = _scanning.set(True)
    try:
        yield
    finally:
        _scanning.reset(tok)

# ---- fingerprint helpers (public via api) ----
def set_fingerprint(fp: Optional[tuple]) -> None:
    global _fingerprint
    _fingerprint = fp

def get_fingerprint() -> Optional[tuple]:
    return _fingerprint
    
def reset_fp_observed() -> None:
    global _fp_observed
    _fp_observed = False

def mark_fp_observed() -> None:
    global _fp_observed
    _fp_observed = True

def was_fp_observed() -> bool:
    return _fp_observed
