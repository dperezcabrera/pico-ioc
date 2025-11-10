# Cookbook: Pattern: CQRS Command Bus

Goal: Implement a Command Bus pattern, common in CQRS (Command Query Responsibility Segregation) architectures, using pico-ioc. The bus should automatically discover and route commands to their respective handlers without tight coupling.

Key pico-ioc Feature: List Injection (`List[CommandHandler]`) or Dictionary Injection (`Dict[Type, CommandHandler]`).

---

## The Pattern

1.  **Contracts (Protocol):** Define `Command` (a marker) and `CommandHandler` (an interface).
2.  **Commands:** Simple data classes inheriting from `Command` (e.g., `CreateUserCommand`).
3.  **Handlers:** Implement `CommandHandler` for each command. Decorate them with `@component`.
4.  **Command Bus:** A central `@component` that discovers all handlers.
5.  **Bootstrap:** Use `init()` to scan all modules. `pico-ioc` automatically injects all found handlers into the bus.

We will explore two ways to build the `CommandBus`:
* **Pattern 1 (Manual Mapping):** Injects `List[CommandHandler]` and builds the map manually.
* **Pattern 2 (Automatic Mapping):** Injects `Dict[Type, CommandHandler]` directly (requires `pico-ioc` v2.x+).

---

## Full Example (Pattern 1: Manual Mapping)

This pattern works on all versions of `pico-ioc` and is very explicit.

### 1. Contracts (cqrs_app/contracts.py)

Define the common language using `typing.Protocol`.

```python
# cqrs_app/contracts.py
from typing import Protocol, Type, TypeVar

# Marker base class for all commands
class Command:
    pass

C = TypeVar("C", bound=Command, contravariant=True)

# Protocol for all command handlers
class CommandHandler(Protocol[C]):
    @property
    def command_type(self) -> Type[Command]:
        """The specific Command type this handler deals with."""
        ...

    def handle(self, command: C) -> None:
        """Executes the logic for the command."""
        ...
```

### 2\. Commands (cqrs\_app/commands.py)

```python
# cqrs_app/commands.py
from dataclasses import dataclass
from .contracts import Command

@dataclass(frozen=True)
class CreateUserCommand(Command):
    username: str
    email: str
```

### 3\. Handlers (cqrs\_app/handlers.py)

Implement the business logic, decorated with `@component`.

```python
# cqrs_app/handlers.py
from pico_ioc import component
from .contracts import CommandHandler
from .commands import CreateUserCommand

@component # <-- Make it discoverable by pico-ioc
class CreateUserHandler(CommandHandler[CreateUserCommand]):
    @property
    def command_type(self) -> type[CreateUserCommand]:
        return CreateUserCommand

    def handle(self, command: CreateUserCommand) -> None:
        print(
            f"[HANDLER] Creating user '{command.username}' "
            f"with email '{command.email}'..."
        )
        print("[HANDLER] User created successfully.")
```

### 4\. Command Bus (cqrs\_app/bus.py)

This component injects `List[CommandHandler]` automatically.

```python
# cqrs_app/bus.py
from typing import List, Dict, Type
from pico_ioc import component
from .contracts import Command, CommandHandler

@component # <-- The CommandBus is also a component
class CommandBus:
    def __init__(self, handlers: List[CommandHandler]):
        """
        Injects ALL registered components that implement CommandHandler.
        """
        print(f"[BUS] Initializing with {len(handlers)} handlers.")
        
        handler_map: Dict[Type[Command], CommandHandler] = {}
        for h in handlers:
            cmd_type = h.command_type
            if cmd_type in handler_map:
                raise ValueError(f"Duplicate handler for {cmd_type.__name__}")
            handler_map[cmd_type] = h
            
        self._handler_map = handler_map
        print(f"[BUS] Registered handlers for: {', '.join(t.__name__ for t in self._handler_map.keys())}")

    def dispatch(self, command: Command) -> None:
        handler = self._handler_map.get(type(command))
        if not handler:
            raise ValueError(f"No handler for {type(command).__name__}")
        
        print(f"\n[BUS] Dispatching command '{type(command).__name__}'...")
        handler.handle(command)
```

-----

## Pattern 2: Automatic Dictionary Injection

If your project supports dictionary injection, you can simplify the `CommandBus` significantly. This pattern requires handlers to be registered with their `Type` as a key.

*(Note: This requires `CommandHandler` to be a `class`, not a `Protocol`, if you are using generic subclass detection. For this example, we assume `pico-ioc`'s `Dict[Type, T]` injection uses the component's concrete class type as the key).*

### 1\. Contracts & Commands

(Same as Pattern 1)

### 2\. Handlers

The handlers are the same, just ensure they are registered as components.

```python
# cqrs_app/handlers.py
from pico_ioc import component
from .contracts import CommandHandler
from .commands import CreateUserCommand

@component
class CreateUserHandler(CommandHandler[CreateUserCommand]):
    # ... (implementation same as pattern 1) ...
    @property
    def command_type(self) -> type[CreateUserCommand]:
        return CreateUserCommand

    def handle(self, command: CreateUserCommand):
        print(f"[HANDLER] Creating user '{command.username}'...")
```

### 3\. Command Bus (Automatic Map)

The `CommandBus` `__init__` becomes much simpler.

```python
# cqrs_app/bus_auto.py
from typing import Dict, Type
from pico_ioc import component
from .contracts import Command, CommandHandler
from .commands import CreateUserCommand # Import command types
from .handlers import CreateUserHandler # Import handler types

@component
class CommandBusAuto:
    def __init__(
        self,
        # Asks pico-ioc to build a map of {HandlerType: HandlerInstance}
        handler_instances_map: Dict[Type, CommandHandler]
    ):
        """
        Injects a map of {ComponentType: ComponentInstance} for all
        components implementing CommandHandler.
        """
        print(f"[BUS-AUTO] Initializing with {len(handler_instances_map)} handlers.")
        
        # We must invert this map to be {CommandType: HandlerInstance}
        handler_map: Dict[Type[Command], CommandHandler] = {}
        for h_type, h_instance in handler_instances_map.items():
            cmd_type = h_instance.command_type
            if cmd_type in handler_map:
                raise ValueError(f"Duplicate handler for {cmd_type.__name__}")
            handler_map[cmd_type] = h_instance
            
        self._handler_map = handler_map
        print(f"[BUS-AUTO] Registered handlers for: {', '.join(t.__name__ for t in self._handler_map.keys())}")

    def dispatch(self, command: Command) -> None:
        handler = self._handler_map.get(type(command))
        if not handler:
            raise ValueError(f"No handler for {type(command).__name__}")
        
        print(f"\n[BUS-AUTO] Dispatching command '{type(command).__name__}'...")
        handler.handle(command)
```

**Note on Dictionary Injection:** The `Dict[Type, T]` injection provides a map of `{ComponentClass: ComponentInstance}`. We still need the `command_type` property to build the final `dispatch` map, as the key we need is the `Command` type, not the `Handler` type.

-----

## 4\. Main Application (main.py)

```python
# main.py
from pico_ioc import init
from cqrs_app.bus import CommandBus # Using Pattern 1
# from cqrs_app.bus_auto import CommandBusAuto # Using Pattern 2
from cqrs_app.commands import CreateUserCommand

def run_app():
    print("--- Initializing Container ---")
    # Scan the entire package to find all components
    container = init(modules=["cqrs_app"])
    print("--- Container Initialized ---")

    command_bus = container.get(CommandBus)
    
    try:
        command_bus.dispatch(
            CreateUserCommand(username="Alice", email="alice@example.com")
        )
    except ValueError as e:
        print(f"Dispatch Error: {e}")

if __name__ == "__main__":
    run_app()
```

-----

## 5\. Benefits

  * **Decoupled:** The `CommandBus` doesn't know about specific handlers. Handlers don't know about the bus. Adding a new command+handler requires zero changes to existing code.
  * **Simple:** Relies on standard Python features and `pico-ioc`'s core DI mechanism.
  * **Testable:** Handlers can be unit-tested in isolation.

<!-- end list -->
