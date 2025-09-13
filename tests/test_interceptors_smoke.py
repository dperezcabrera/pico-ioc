# tests/test_interceptors_smoke.py
import pico_ioc
from pico_ioc import component
import asyncio

events = []

class CollectLogger:
    def __call__(self, msg): events.append(msg)

class LoggingInterceptor:
    def __init__(self, container):
        self._logger = CollectLogger()

    def __call__(self, inv, proceed):
        self._logger(f"call:{inv.method_name}")
        out = proceed()
        self._logger(f"ret:{inv.method_name}")
        return out

@component
class Svc:
    def ping(self, x): return x + 1
    async def aping(self, y): return y + 2

def test_sync_and_async():
    c = pico_ioc.PicoContainer(method_interceptors=(LoggingInterceptor,))
    binder = pico_ioc.Binder(c)
    binder.bind(Svc, lambda: Svc(), lazy=False)

    # Build interceptors explicitly for this bare container
    c._build_interceptors()

    s = c.get(Svc)
    assert s.ping(41) == 42

    asyncio.run(s.aping(40))
    assert any("call:ping" in e for e in events)
    assert any("ret:ping" in e for e in events)

