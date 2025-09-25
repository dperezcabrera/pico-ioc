# Cookbook: Pattern: CQRS Command Bus

**Goal:** Implement a Command Bus pattern, common in CQRS (Command Query Responsibility Segregation) architectures, using `pico-ioc`. The bus should automatically discover and route commands to their respective handlers without tight coupling.

**Key `pico-ioc` Feature:** **List Injection by Type.** The `CommandBus` will simply request `List[CommandHandler]` in its constructor, and `pico-ioc` will automatically inject *all* registered components that implement the `CommandHandler` protocol.

---

## The Pattern

1.  **Contracts (`Protocol`):** Define `Command` (a marker) and `CommandHandler` (an interface specifying `command_type` and `handle` method).
2.  **Commands:** Simple data classes inheriting from `Command` (e.g., `CreateUserCommand`).
3.  **Handlers:** Implement `CommandHandler` for each command. Decorate them with `@component` so `pico-ioc` finds them.
4.  **Command Bus:** A central `@component` that:
    * Injects `List[CommandHandler]` (the magic part ✨).
    * Creates a dictionary mapping command types to handlers in its `__init__`.
    * Provides a `dispatch(command)` method that looks up the correct handler and executes it.
5.  **Bootstrap:** Use `init()` to scan all modules containing commands, handlers, and the bus. `get()` the `CommandBus` and use it.

---

## Full, Runnable Example

### 1. Project Structure

```

.
├── cqrs\_app/
│   ├── **init**.py
│   ├── bus.py           \<-- The CommandBus component
│   ├── commands.py      \<-- Command definitions
│   ├── contracts.py     \<-- Protocol definitions
│   └── handlers.py      \<-- CommandHandler implementations
└── main.py              \<-- Application entrypoint

````

### 2. Contracts (`cqrs_app/contracts.py`)

Define the common language using `typing.Protocol`.

```python
# cqrs_app/contracts.py
from typing import Protocol, Type, TypeVar

# Marker base class for all commands
class Command:
    pass

C = TypeVar("C", bound=Command)

# Protocol for all command handlers
class CommandHandler(Protocol[C]):
    @property
    def command_type(self) -> Type[C]:
        """The specific Command type this handler deals with."""
        ...

    def handle(self, command: C) -> None:
        """Executes the logic for the command."""
        ...
````

### 3\. Commands (`cqrs_app/commands.py`)

Define simple data classes for commands.

```python
# cqrs_app/commands.py
from dataclasses import dataclass
from .contracts import Command

@dataclass(frozen=True)
class CreateUserCommand(Command):
    username: str
    email: str

@dataclass(frozen=True)
class DeactivateUserCommand(Command):
    user_id: int
```

### 4\. Handlers (`cqrs_app/handlers.py`)

Implement the business logic for each command. Crucially, decorate each handler with `@component`.

```python
# cqrs_app/handlers.py
from pico_ioc import component
from .contracts import CommandHandler
from .commands import CreateUserCommand, DeactivateUserCommand

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
        # ... actual database logic would go here ...
        print("[HANDLER] User created successfully.")

@component # <-- Make it discoverable by pico-ioc
class DeactivateUserHandler(CommandHandler[DeactivateUserCommand]):
    @property
    def command_type(self) -> type[DeactivateUserCommand]:
        return DeactivateUserCommand

    def handle(self, command: DeactivateUserCommand) -> None:
        print(f"[HANDLER] Deactivating user with ID '{command.user_id}'...")
        # ... actual database logic would go here ...
        print("[HANDLER] User deactivated.")

# Add more handlers here by just creating new @component classes!
```

### 5\. Command Bus (`cqrs_app/bus.py`)

This component injects *all* known handlers automatically.

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
        This is the core of the pattern's decoupling.
        """
        print(f"[BUS] Initializing with {len(handlers)} handlers.")
        self._handler_map: Dict[Type[Command], CommandHandler] = {
            h.command_type: h for h in handlers
        }
        print(f"[BUS] Registered handlers for: {list(self._handler_map.keys())}")


    def dispatch(self, command: Command) -> None:
        """Finds the appropriate handler and executes it."""
        handler = self._handler_map.get(type(command))
        if not handler:
            raise ValueError(
                f"No handler registered for command type: {type(command).__name__}"
            )

        print(f"\n[BUS] Dispatching command '{type(command).__name__}'...")
        try:
            handler.handle(command)
            print(f"[BUS] Command '{type(command).__name__}' handled successfully.")
        except Exception as e:
            print(f"[BUS] Error handling command '{type(command).__name__}': {e}")
            # Add proper error handling/logging here
            raise
```

### 6\. Main Application (`main.py`)

Initialize the container and run the application.

```python
# main.py
from pico_ioc import init
from cqrs_app.bus import CommandBus
from cqrs_app.commands import CreateUserCommand, DeactivateUserCommand

def run_app():
    print("--- Initializing Container ---")
    # Scan the entire package to find all components
    container = init(modules=["cqrs_app"])
    print("--- Container Initialized ---")

    # Get the fully wired CommandBus
    command_bus = container.get(CommandBus)

    # Dispatch commands
    try:
        command_bus.dispatch(
            CreateUserCommand(username="Alice", email="alice@example.com")
        )
        command_bus.dispatch(DeactivateUserCommand(user_id=123))
        # Add a new command just by creating a new handler!
        # command_bus.dispatch(SomeOtherCommand(...))
    except ValueError as e:
        print(f"Dispatch Error: {e}")

if __name__ == "__main__":
    run_app()
```

-----

## 7\. Benefits

  * **Decoupled:** The `CommandBus` doesn't know about specific handlers. Handlers don't know about the bus or each other. Adding a new command+handler requires *zero changes* to existing code.
  * **Simple:** Relies on standard Python features (`Protocol`, `List`) and `pico-ioc`'s core DI mechanism.
  * **Testable:** Handlers can be unit-tested in isolation. The `CommandBus` itself has minimal logic.
  * **Explicit:** The flow is clear: `dispatch` -\> find handler -\> `handle`.

This pattern shows how `pico-ioc`'s list injection elegantly supports common architectural patterns like CQRS Command Buses.

