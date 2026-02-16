"""Exception hierarchy for pico-ioc.

All framework-specific exceptions inherit from :class:`PicoError`, making it
easy to catch any pico-ioc error with a single ``except PicoError`` clause.
"""

from typing import Any, Iterable


class PicoError(Exception):
    """Base exception for all pico-ioc errors."""

    pass


class ProviderNotFoundError(PicoError):
    """Raised when the container cannot find a provider for a requested key.

    Attributes:
        key: The resolution key that was not found.
        origin: The component or context that requested the key.
    """

    def __init__(self, key: Any, origin: Any | None = None):
        key_name = getattr(key, "__name__", str(key))
        origin_name = getattr(origin, "__name__", str(origin)) if origin else "init"
        super().__init__(f"Provider for key '{key_name}' not found (required by: '{origin_name}')")
        self.key = key
        self.origin = origin


class ComponentCreationError(PicoError):
    """Raised when a provider callable fails while creating a component.

    Attributes:
        key: The resolution key whose creation failed.
        cause: The original exception that caused the failure.
    """

    def __init__(self, key: Any, cause: Exception):
        k = getattr(key, "__name__", key)
        super().__init__(f"Failed to create component for key: {k}; cause: {cause.__class__.__name__}: {cause}")
        self.key = key
        self.cause = cause


class ScopeError(PicoError):
    """Raised for scope-related errors (unknown scope, missing scope ID, reserved name)."""

    def __init__(self, msg: str):
        super().__init__(msg)


class ConfigurationError(PicoError):
    """Raised for configuration problems (missing keys, invalid sources, bad interpolation)."""

    def __init__(self, msg: str):
        super().__init__(msg)


class SerializationError(PicoError):
    """Raised when a proxy target cannot be serialized or deserialized."""

    def __init__(self, msg: str):
        super().__init__(msg)


class ValidationError(PicoError):
    """Raised when startup validation detects wiring problems."""

    def __init__(self, msg: str):
        super().__init__(msg)


class InvalidBindingError(ValidationError):
    """Raised when one or more dependency bindings are invalid.

    Attributes:
        errors: List of human-readable error descriptions.
    """

    def __init__(self, errors: list[str]):
        super().__init__("Invalid bindings:\n" + "\n".join(f"- {e}" for e in errors))
        self.errors = errors


class AsyncResolutionError(PicoError):
    """Raised when ``get()`` encounters an awaitable result.

    This means the component requires asynchronous initialisation; use
    ``await container.aget(key)`` instead.

    Attributes:
        key: The resolution key that produced an awaitable.
    """

    def __init__(self, key: Any):
        key_name = getattr(key, "__name__", str(key))
        super().__init__(f"Synchronous get() received an awaitable for key '{key_name}'. Use aget() instead.")
        self.key = key


class EventBusError(PicoError):
    """Base exception for EventBus-related errors."""

    def __init__(self, msg: str):
        super().__init__(msg)


class EventBusClosedError(EventBusError):
    """Raised when an operation is attempted on a closed EventBus."""

    def __init__(self):
        super().__init__("EventBus is closed")


class EventBusQueueFullError(EventBusError):
    """Raised when the EventBus worker queue is full and cannot accept new events."""

    def __init__(self):
        super().__init__("Event queue is full")


class EventBusHandlerError(EventBusError):
    """Raised when an event handler fails during event dispatch.

    Attributes:
        event_name: The name of the event type being dispatched.
        handler_name: The name of the handler that failed.
        cause: The original exception raised by the handler.
    """

    def __init__(self, event_name: str, handler_name: str, cause: Exception):
        super().__init__(f"Handler {handler_name} failed for event {event_name}: {cause.__class__.__name__}: {cause}")
        self.event_name = event_name
        self.handler_name = handler_name
        self.cause = cause
