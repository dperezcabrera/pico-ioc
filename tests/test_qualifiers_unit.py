from __future__ import annotations
try:
    from typing import Protocol, Annotated  # type: ignore
except Exception:
    from typing_extensions import Protocol, Annotated  # type: ignore

from pico_ioc import component, Qualifier, qualifier, init


class Handler(Protocol):
    def handle(self, s: str) -> str: ...


PAYMENTS = Qualifier("payments")
NOTIF = Qualifier("notifications")


@component
@qualifier(PAYMENTS)
class StripeHandler:
    def handle(self, s: str) -> str:
        return f"stripe:{s}"


@component
@qualifier(PAYMENTS)
class PaypalHandler:
    def handle(self, s: str) -> str:
        return f"paypal:{s}"


@component
@qualifier(NOTIF)
class EmailHandler:
    def handle(self, s: str) -> str:
        return f"email:{s}"


@component
class OrchestratorAll:
    def __init__(self, handlers: list[Handler]):
        self.handlers = handlers


@component
class OrchestratorPayments:
    def __init__(self, handlers: list[Annotated[Handler, PAYMENTS]]):
        self.handlers = handlers


def test_collection_injection_all(tmp_path, monkeypatch):
    import types
    pkg = types.ModuleType("qualpkg_all")
    pkg.__dict__.update(globals())
    # Build container from this module namespace
    c = init(pkg)
    orch = c.get(OrchestratorAll)
    names = {type(h).__name__ for h in orch.handlers}
    assert names == {"StripeHandler", "PaypalHandler", "EmailHandler"}


def test_collection_injection_with_qualifier(tmp_path, monkeypatch):
    import types
    pkg = types.ModuleType("qualpkg_pay")
    pkg.__dict__.update(globals())
    c = init(pkg)
    orch = c.get(OrchestratorPayments)
    names = {type(h).__name__ for h in orch.handlers}
    assert names == {"StripeHandler", "PaypalHandler"}

