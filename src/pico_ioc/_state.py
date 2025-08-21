# pico_ioc/_state.py
from contextvars import ContextVar

_scanning: ContextVar[bool] = ContextVar("pico_scanning", default=False)
_resolving: ContextVar[bool] = ContextVar("pico_resolving", default=False)

_container = None

