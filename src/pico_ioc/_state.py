from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from contextvars import ContextVar
from contextlib import contextmanager
from typing import Optional, TYPE_CHECKING

# Type-only import to avoid cycles
if TYPE_CHECKING:
    from .container import PicoContainer


# ---- Task/process context for the active container ----

@dataclass(frozen=True, slots=True)
class ContainerContext:
    """Immutable snapshot for the active container state."""
    container: "PicoContainer"
    fingerprint: tuple
    root_name: Optional[str]


# Process-wide fallback (for non-async code) guarded by a lock
_lock = RLock()
_current_context: Optional[ContainerContext] = None

# Task-local context (for async isolation)
_ctxvar: ContextVar[Optional[ContainerContext]] = ContextVar("pico_ioc_ctx", default=None)


def get_context() -> Optional[ContainerContext]:
    """Return the current context (task-local first, then process-global)."""
    ctx = _ctxvar.get()
    return ctx if ctx is not None else _current_context


def set_context(ctx: Optional[ContainerContext]) -> None:
    """Atomically set both task-local and process-global context."""
    with _lock:
        _ctxvar.set(ctx)
        globals()["_current_context"] = ctx


# Optional compatibility helpers (only used by legacy API paths)
def get_fingerprint() -> Optional[tuple]:
    ctx = get_context()
    return ctx.fingerprint if ctx else None


def set_fingerprint(fp: Optional[tuple]) -> None:
    """Compatibility shim: setting None clears the active context."""
    if fp is None:
        set_context(None)
        return
    ctx = get_context()
    if ctx is not None:
        set_context(ContainerContext(container=ctx.container, fingerprint=fp, root_name=ctx.root_name))


# ---- Scan/resolve guards (kept as-is) ----

_scanning: ContextVar[bool] = ContextVar("pico_scanning", default=False)
_resolving: ContextVar[bool] = ContextVar("pico_resolving", default=False)


@contextmanager
def scanning_flag():
    """Mark scanning=True within the block."""
    tok = _scanning.set(True)
    try:
        yield
    finally:
        _scanning.reset(tok)

