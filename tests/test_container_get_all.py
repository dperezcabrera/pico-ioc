from __future__ import annotations
from typing import Protocol
from pico_ioc import component, init

class H(Protocol):
    def x(self) -> str: ...

@component
class A:
    def x(self) -> str: return "a"

@component
class B:
    def x(self) -> str: return "b"

def test_get_all_protocol_like():
    import types
    pkg = types.ModuleType("xx")
    pkg.__dict__.update(globals())
    c = init(pkg)
    items = c.get_all(H)
    assert {i.x() for i in items} == {"a", "b"}

