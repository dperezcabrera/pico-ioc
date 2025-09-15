# src/pico_ioc/utils.py
from typing import Any, Callable
from .container import PicoContainer
from .proxy import ComponentProxy

def _wrap_if_lazy(provider: Callable, is_lazy: bool) -> Callable:
    """Wraps a provider in a ComponentProxy if it's marked as lazy."""
    return (lambda: ComponentProxy(provider)) if is_lazy else provider

def _provider_from_class(cls: type, *, resolver, lazy: bool):
    def _new():
        return resolver.create_instance(cls)
    return _wrap_if_lazy(_new, lazy)

def _provider_from_callable(fn, *, owner_cls, resolver, lazy: bool):
    def _invoke():
        kwargs = resolver.kwargs_for_callable(fn, owner_cls=owner_cls)
        return fn(**kwargs)
    return _wrap_if_lazy(_invoke, lazy)
        
def create_alias_provider(container: PicoContainer, target_key: Any) -> Callable[[], Any]:
    """Creates a provider that delegates the get() call to the container for another key."""
    def _provider():
        return container.get(target_key)
    return _provider
