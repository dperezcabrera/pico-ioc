# src/pico_ioc/factory.py
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Set, Tuple, Union
from .exceptions import ProviderNotFoundError

KeyT = Union[str, type]
Provider = Callable[[], Any]

@dataclass(frozen=True)
class ProviderMetadata:
    key: KeyT
    provided_type: Optional[type]
    concrete_class: Optional[type]
    factory_class: Optional[type]
    factory_method: Optional[str]
    qualifiers: Set[str]
    primary: bool
    lazy: bool
    infra: Optional[str]
    pico_name: Optional[Any]
    override: bool = False
    scope: str = "singleton"

class ComponentFactory:
    def __init__(self) -> None:
        self._providers: Dict[KeyT, Provider] = {}
    def bind(self, key: KeyT, provider: Provider) -> None:
        self._providers[key] = provider
    def has(self, key: KeyT) -> bool:
        return key in self._providers
    def get(self, key: KeyT) -> Provider:
        if key not in self._providers:
            raise ProviderNotFoundError(key)
        return self._providers[key]

class DeferredProvider:
    def __init__(self, builder: Callable[[Any, Any], Any]) -> None:
        self._builder = builder
        self._pico: Any = None
        self._locator: Any = None
    def attach(self, pico, locator) -> None:
        self._pico = pico
        self._locator = locator
    def __call__(self) -> Any:
        if self._pico is None or self._locator is None:
            raise RuntimeError("DeferredProvider must be attached before use")
        return self._builder(self._pico, self._locator)

