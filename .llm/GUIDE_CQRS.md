### \#\# Implementing a CQRS Command Bus with Pico-IoC

Are you a fan of clean architectural patterns like CQRS? This guide demonstrates how `pico-ioc` makes building a powerful and fully decoupled Command Bus not just possible, but incredibly simple. By leveraging features like **collection injection**, you can create a system where command handlers are automatically discovered and wired up, allowing you to focus on your business logic instead of boilerplate.


### \#\#\# Step 1: Define the Contracts

First, we define the core interfaces for our commands and handlers using Python's `Protocol`. This ensures all our components speak the same language. The `CommandHandler` protocol specifies that each handler must declare which `command_type` it is responsible for.

```python
from typing import Protocol, Type

class Command:
    pass

class CommandHandler(Protocol):
    @property
    def command_type(self) -> Type[Command]:
        ...

    def handle(self, command: Command) -> None:
        ...
```

-----

### \#\#\# Step 2: Create Concrete Handlers

Now, we create our business logic. We'll define two simple commands, `CreateUser` and `DeactivateUser`, and their corresponding handlers. Each handler is a standard class decorated with `@component` so `pico-ioc` can discover and manage it.

```python
from pico_ioc import component
from contracts import Command, CommandHandler

class CreateUser(Command):
    def __init__(self, name: str, email: str):
        self.name = name
        self.email = email

class DeactivateUser(Command):
    def __init__(self, user_id: int):
        self.user_id = user_id

@component
class CreateUserHandler(CommandHandler):
    command_type = CreateUser

    def handle(self, command: CreateUser) -> None:
        print(f"HANDLER: Creating user '{command.name}' with email '{command.email}'...")
        print("HANDLER: User created successfully.")

@component
class DeactivateUserHandler(CommandHandler):
    command_type = DeactivateUser

    def handle(self, command: DeactivateUser) -> None:
        print(f"HANDLER: Deactivating user with ID '{command.user_id}'...")
        print("HANDLER: User deactivated.")
```

-----

### \#\#\# Step 3: Build the Command Bus

This is where the power of `pico-ioc` becomes evident. The `CommandBus` constructor asks for a `list[CommandHandler]`. **This is the magic**: `pico-ioc` will automatically find **all** registered components that match the `CommandHandler` protocol and inject them as a list.

This makes the Bus completely decoupled. To add new functionality, you just create a new handler class; you never need to modify the Bus.

```python
from typing import List
from pico_ioc import component
from contracts import Command, CommandHandler

@component
class CommandBus:
    def __init__(self, handlers: List[CommandHandler]):
        print(f"BUS: Initializing with {len(handlers)} handlers.")
        self._handlers = {h.command_type: h for h in handlers}

    def dispatch(self, command: Command) -> None:
        handler = self._handlers.get(type(command))
        if not handler:
            raise ValueError(f"No handler registered for command {type(command).__name__}")
        
        print(f"\nBUS: Dispatching command '{type(command).__name__}'...")
        handler.handle(command)
```

-----

### \#\#\# Step 4: Put It All Together

Finally, we bootstrap our application. We initialize the container, which scans for all our components. Then we retrieve the fully configured `CommandBus` and start using it. Notice we don't need to manually register each handler with the bus; `pico-ioc` does it for us.

```python
import sys
from pico_ioc import init
from bus import CommandBus
from handlers import CreateUser, DeactivateUser

def main():
    container = init(sys.modules[__name__])
    command_bus = container.get(CommandBus)

    command_bus.dispatch(CreateUser(name="Alice", email="alice@example.com"))
    command_bus.dispatch(DeactivateUser(user_id=123))

if __name__ == "__main__":
    main()
```
