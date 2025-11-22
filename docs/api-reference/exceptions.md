# Exceptions

This page documents the custom exception types defined by pico_ioc. These exceptions provide clear, structured error reporting across provider lookup, component creation, configuration and validation, scope management, async resolution, and the event bus.

Use these exceptions to:
- Understand what went wrong and where (e.g., no provider found vs. component failed to build).
- Catch and handle errors precisely in your application code.
- Raise informative errors from custom providers, factories, and event handlers.

All exceptions inherit from the common base class `PicoError`, allowing you to catch all pico_ioc-specific failures with a single handler when appropriate.

## Overview

- Base
  - PicoError

- Provider and component resolution
  - ProviderNotFoundError(key, origin)
  - ComponentCreationError(key, cause)
  - ScopeError(msg)
  - AsyncResolutionError(key)

- Configuration, serialization, and validation
  - ConfigurationError(msg)
  - SerializationError(msg)
  - ValidationError(msg)
  - InvalidBindingError(errors)

- Event bus
  - EventBusError(msg)
  - EventBusClosedError()
  - EventBusQueueFullError()
  - EventBusHandlerError(event_name, handler_name, cause)

Typical import path:
```python
from pico_ioc.exceptions import (
    PicoError,
    ProviderNotFoundError,
    ComponentCreationError,
    ScopeError,
    ConfigurationError,
    SerializationError,
    ValidationError,
    InvalidBindingError,
    AsyncResolutionError,
    EventBusError,
    EventBusClosedError,
    EventBusQueueFullError,
    EventBusHandlerError,
)
```

## Exception details

### PicoError
- Description: Base class for all pico_ioc exceptions. Catch this to handle any library-specific error.
- Init: N/A

### ProviderNotFoundError(key, origin)
- Description: Raised when resolving a dependency but no provider is registered for the requested key.
- Parameters:
  - key: The dependency key (e.g., interface, token, or type) that could not be resolved.
  - origin: The component or context that attempted the resolution.

### ComponentCreationError(key, cause)
- Description: A provider was found but creating the component failed (e.g., constructor error, factory failure).
- Parameters:
  - key: The dependency key for the component that failed to be created.
  - cause: The original exception that caused the failure (preserve it for debugging).

### ScopeError(msg)
- Description: Raised for scoping violations (e.g., using a scoped provider outside an active scope, or missing scope).
- Parameters:
  - msg: Description of the scope issue.

### ConfigurationError(msg)
- Description: Raised for invalid or inconsistent configuration detected at setup time or runtime.
- Parameters:
  - msg: Description of the configuration problem.

### SerializationError(msg)
- Description: Raised when serializing or deserializing configuration, definitions, or state fails.
- Parameters:
  - msg: Description of the serialization issue.

### ValidationError(msg)
- Description: Raised for general validation failures (e.g., incompatible types, missing required fields).
- Parameters:
  - msg: Description of the validation issue.

### InvalidBindingError(errors)
- Description: Raised when attempting to register an invalid binding (e.g., target incompatible with key).
- Parameters:
  - errors: One or more validation errors collected during binding analysis.

### AsyncResolutionError(key)
- Description: Raised when attempting to resolve a dependency that requires asynchronous construction using a synchronous resolution path.
- Parameters:
  - key: The dependency key that requires async resolution.

### EventBusError(msg)
- Description: Base class for event-bus-related errors.
- Parameters:
  - msg: Description of the event bus issue.

### EventBusClosedError()
- Description: Raised when publishing or subscribing after the event bus has been closed.

### EventBusQueueFullError()
- Description: Raised when the event bus cannot accept more events due to a full queue/back-pressure.

### EventBusHandlerError(event_name, handler_name, cause)
- Description: Raised when an event handler fails while processing an event.
- Parameters:
  - event_name: The name/type of the event being processed.
  - handler_name: Identifier of the handler that failed.
  - cause: The original exception thrown by the handler.

## How to use these exceptions

### Catching resolution errors
Use targeted exception handling to differentiate "missing provider" from "provider exists but creation failed":

```python
from pico_ioc.exceptions import ProviderNotFoundError, ComponentCreationError, ScopeError

def build_service(container):
    try:
        return container.resolve("service_key")  # or a type/interface token
    except ProviderNotFoundError as e:
        # No provider registered for this key
        logger.error("Provider not found: %s (origin: %s)", getattr(e, "key", None), getattr(e, "origin", None))
        raise
    except ComponentCreationError as e:
        # A provider exists, but instantiation failed
        logger.exception("Failed to create component for key: %s", getattr(e, "key", None))
        raise
    except ScopeError as e:
        # Resolve attempted outside an active scope or wrong scope usage
        logger.warning("Scope error: %s", e)
        raise
```

Tip: When you do not need fine-grained handling, catch `PicoError` to handle any pico_ioc-specific failure.

```python
from pico_ioc.exceptions import PicoError

try:
    service = container.resolve(Service)
except PicoError as e:
    logger.error("pico_ioc error: %s", e)
    raise
```

### Async resolution
If a dependency requires asynchronous construction, resolve it via an async API; otherwise, `AsyncResolutionError` may be raised.

```python
from pico_ioc.exceptions import AsyncResolutionError

# Wrong (sync for async dependency)
try:
    repo = container.resolve("async_repo")
except AsyncResolutionError:
    # Switch to the async path
    repo = await container.aresolve("async_repo")  # or container.resolve_async(...)

# Right (pure async flow)
repo = await container.aresolve("async_repo")
```

### Binding and configuration validation
Invalid bindings and configuration issues should be caught explicitly during setup.

```python
from pico_ioc.exceptions import InvalidBindingError, ConfigurationError, ValidationError

def configure(container):
    try:
        # Examples:
        # - Wrong type bound to an interface
        # - Missing required configuration
        container.bind("IFoo", to="not_a_valid_impl")
        container.configure({"unknown_option": True})
    except InvalidBindingError as e:
        logger.error("Invalid binding: %s", e)
        raise
    except (ConfigurationError, ValidationError) as e:
        logger.error("Configuration/validation error: %s", e)
        raise
```

If you validate or transform configuration data, convert low-level parsing failures into `SerializationError` or `ValidationError` as appropriate:

```python
from pico_ioc.exceptions import SerializationError, ValidationError

def load_config(raw: str):
    try:
        return json.loads(raw)
    except json.JSONDecodeError as cause:
        raise SerializationError(f"Invalid JSON: {cause}")  # carry the detail message

def validate_config(cfg: dict):
    if "endpoint" not in cfg:
        raise ValidationError("Missing 'endpoint' in configuration")
```

### Scope management
Open and close scopes correctly; misuse raises `ScopeError`.

```python
from pico_ioc.exceptions import ScopeError

try:
    # e.g., resolve a request-scoped dependency without an active request scope
    handler = container.resolve("request_handler")
except ScopeError as e:
    logger.warning("Attempted scoped resolve without scope: %s", e)
    raise
```

### Event bus error handling
Handle bus state (closed, back-pressure) and handler failures.

```python
from pico_ioc.exceptions import (
    EventBusError,
    EventBusClosedError,
    EventBusQueueFullError,
    EventBusHandlerError,
)

async def publish_user_created(bus, user):
    try:
        await bus.publish("user.created", {"id": user.id})
    except EventBusClosedError:
        logger.warning("Event bus is closed; dropping event")
    except EventBusQueueFullError:
        logger.warning("Event bus queue full; back-pressure encountered")
    except EventBusError as e:
        logger.error("Event bus error: %s", e)
        raise

async def handle_events(bus):
    async for event in bus.events():  # example consumption
        try:
            await bus.dispatch(event)
        except EventBusHandlerError as e:
            # Inspect metadata as available; message contains event and handler info
            logger.exception("Handler failure while processing event: %s", e)
```

## Raising these exceptions in your own code

When implementing custom providers, factories, modules, or event handlers, raise the most specific pico_ioc exception you can:

- Missing provider at runtime: raise ProviderNotFoundError(key, origin)
- Construction failure: raise ComponentCreationError(key, cause)
- Scope misuse: raise ScopeError("...details...")
- Async misuse: raise AsyncResolutionError(key)
- Binding issues discovered during registration: raise InvalidBindingError(errors)
- Configuration problems: raise ConfigurationError("...") or ValidationError("...")
- Serialization failures: raise SerializationError("...")
- Event handler failure wrapping: raise EventBusHandlerError(event_name, handler_name, cause)

This consistency helps calling code provide better diagnostics and fallback behavior.