"""Provider metadata and low-level component factory.

This module defines :class:`ProviderMetadata` (the immutable descriptor for a
registered provider), :class:`ComponentFactory` (the key-to-provider registry),
and :class:`DeferredProvider` (a provider whose resolution is deferred until
the container and locator are available).
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Set, Tuple, Union

from .analysis import DependencyRequest
from .exceptions import ProviderNotFoundError

KeyT = Union[str, type]
Provider = Callable[[], Any]


@dataclass(frozen=True)
class ProviderMetadata:
    """Immutable descriptor for a registered provider.

    Captures everything the container needs to know about a provider: its
    registration key, the types it produces, its scope, qualifiers, and
    the static dependency graph.

    Attributes:
        key: The resolution key (a type or string).
        provided_type: The type of object the provider produces.
        concrete_class: The concrete implementation class, if known.
        factory_class: The ``@factory`` class that owns this provider, if any.
        factory_method: The name of the ``@provides`` method, if any.
        qualifiers: Set of qualifier strings for multi-binding.
        primary: Whether this provider is the primary choice for its type.
        lazy: Whether the component uses deferred (proxy-based) creation.
        infra: Infrastructure role (``'component'``, ``'factory'``,
            ``'provides'``, ``'configured'``).
        pico_name: Human-readable name for the provider.
        dependencies: Statically analysed constructor/factory-method
            dependencies.
        override: Whether this provider was registered via ``overrides``.
        scope: Lifecycle scope name.
    """
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
    dependencies: Tuple[DependencyRequest, ...] = ()
    override: bool = False
    scope: str = "singleton"


class ComponentFactory:
    """Simple key-to-provider registry.

    Stores the final provider callable for each resolution key. Providers
    are zero-argument callables that return the component instance (or an
    awaitable for async components).
    """

    def __init__(self) -> None:
        self._providers: Dict[KeyT, Provider] = {}

    def bind(self, key: KeyT, provider: Provider) -> None:
        """Bind a provider callable to a key, replacing any previous binding.

        Args:
            key: The resolution key (type or string).
            provider: A zero-argument callable that produces the component.
        """
        self._providers[key] = provider

    def has(self, key: KeyT) -> bool:
        """Check whether a provider is bound to *key*.

        Args:
            key: The resolution key to check.

        Returns:
            ``True`` if a provider exists for *key*.
        """
        return key in self._providers

    def get(self, key: KeyT, origin: KeyT) -> Provider:
        """Retrieve the provider for *key*.

        Args:
            key: The resolution key.
            origin: The component requesting this key (for error messages).

        Returns:
            The provider callable.

        Raises:
            ProviderNotFoundError: If no provider is bound to *key*.
        """
        if key not in self._providers:
            raise ProviderNotFoundError(key, origin)
        return self._providers[key]


class DeferredProvider:
    """A provider whose execution is deferred until the container is ready.

    During scanning, providers are created before the container and locator
    exist. ``DeferredProvider`` captures a builder callable and replays it
    once :meth:`attach` has been called.

    Raises:
        RuntimeError: If called before :meth:`attach`.
    """
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
