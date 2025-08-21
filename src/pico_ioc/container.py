# pico_ioc/container.py

from typing import Any, Callable, Dict
from ._state import _scanning, _resolving

class PicoContainer:
    def __init__(self):
        self._providers: Dict[Any, Dict[str, Any]] = {}
        self._singletons: Dict[Any, Any] = {}

    def bind(self, key: Any, provider: Callable[[], Any], *, lazy: bool):
        self._providers[key] = {"factory": provider, "lazy": bool(lazy)}

    def has(self, key: Any) -> bool:
        return key in self._providers or key in self._singletons


    def get(self, key: Any) -> Any:
        if _scanning.get() and not _resolving.get():
            raise RuntimeError("pico-ioc: re-entrant container access during scan.")

        if key in self._singletons:
            return self._singletons[key]
        prov = self._providers.get(key)
        if prov is None:
            raise NameError(f"No provider found for key: {key}")
        instance = prov["factory"]()
        self._singletons[key] = instance
        return instance


    def eager_instantiate_all(self):
        for key, meta in list(self._providers.items()):
            if not meta.get("lazy", False) and key not in self._singletons:
                self.get(key)

class Binder:
    def __init__(self, container: PicoContainer):
        self._c = container
    def bind(self, key, provider, *, lazy=False): self._c.bind(key, provider, lazy=lazy)
    def has(self, key) -> bool: return self._c.has(key)
    def get(self, key): return self._c.get(key)

