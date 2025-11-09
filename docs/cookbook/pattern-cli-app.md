# Cookbook: Pattern: CLI Applications

Goal: Build a robust command-line (CLI) application using a library like Typer or Click, but keep the core logic testable and decoupled using pico-ioc.

Problem: It's common to put all your application logic directly inside your CLI command functions. This makes your logic hard-coded, impossible to unit-test without simulating a CLI call, and difficult to configure.

```python
# The "bad" way - logic is trapped in the CLI
import typer
import os

class ApiClient:
    def __init__(self, key): self.key = key
    def create(self, username): print(f"API: Creating {username} with key {self.key[:4]}...")

app = typer.Typer()

@app.command()
def create_user(username: str):
    """
    Creates a user.
    """
    api_key = os.environ.get("API_KEY")
    client = ApiClient(api_key)
    
    try:
        client.create(username)
        print(f"Success! User '{username}' created.")
    except Exception as e:
        print(f"Error: {e}")
```

Solution: The CLI command should only be a thin wrapper. The real work should be done by a pico-ioc–managed service.

1. main(): The main entrypoint of your CLI app is responsible for init()ing the pico-ioc container, providing configuration via the configuration(...) builder.
2. Configuration: Your settings (like API_KEY) are loaded into a @configured dataclass (using mapping="flat" or "auto").
3. Services: Your core logic (like UserService) is a @component that injects the configuration.
4. CLI Command: The @app.command() function just gets the service from the container and calls its method.

-----

Requirements

This pattern works best with a dedicated CLI library. Typer is a great, modern choice.

- pip install typer
- pip install pico-ioc

-----

Full, Runnable Example

This example builds a CLI tool that can create a user, with its API key managed by pico-ioc.

1. Project Structure

```
.
├── app/
│   ├── __init__.py
│   ├── config.py     <-- Configuration dataclass (@configured)
│   └── services.py   <-- Business logic
└── cli.py            <-- Typer app
```

2. The Configuration (app/config.py)

Define a dataclass to hold settings, loaded from environment variables using @configured with an automatic field-to-variable mapping.

```python
# app/config.py
from dataclasses import dataclass
from pico_ioc import configured

@configured(prefix="MYAPP_", mapping="auto")
@dataclass
class AppConfig:
    API_KEY: str
    API_URL: str = "https://api.example.com"
```

3. The Service (app/services.py)

This is the business logic. It’s a standard @component that is completely decoupled from the CLI.

```python
# app/services.py
from pico_ioc import component
from .config import AppConfig

@component
class UserService:
    def __init__(self, config: AppConfig):
        self.api_key = config.API_KEY
        self.api_url = config.API_URL
        print(f"UserService initialized, using API at {self.api_url}")
        
    def create_user(self, username: str, force: bool = False):
        if not username:
            raise ValueError("Username cannot be empty")
        
        print(
            f"Calling '{self.api_url}/users' "
            f"with key '{self.api_key[:4]}...' "
            f"to create user '{username}'"
        )
        if force:
            print("Force flag enabled; proceeding even if user exists.")
        print("...Success!")
```

4. The CLI (cli.py)

This file ties everything together. It creates the Typer app, initializes pico-ioc with the configuration context, and the command function gets the service.

```python
# cli.py
import typer
from pico_ioc import init, configuration, EnvSource
from app.services import UserService

app = typer.Typer()

# Build configuration context to read environment with the MYAPP_ prefix
config_context = configuration(
    EnvSource(prefix="MYAPP_")
)

# Initialize the container with modules that define configuration and services
container = init(
    modules=["app.config", "app.services"],
    config=config_context
)

@app.command()
def create_user(
    username: str = typer.Argument(..., help="The username to create"),
    force: bool = typer.Option(False, "--force", help="Force creation")
):
    """
    Creates a new user in the system.
    """
    try:
        user_service = container.get(UserService)
        user_service.create_user(username, force=force)
        typer.echo(f"CLI: Successfully created user '{username}'.")
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

@app.command()
def another_command():
    """Another command that can also use the container."""
    typer.echo("Running another command...")

if __name__ == "__main__":
    app()
```

-----

5. How to Use It

- Set the required environment variables:
  - export MYAPP_API_KEY="my-secret-key-123"
  - Optionally, set export MYAPP_API_URL="https://api.example.com"
- Run the CLI:
  - python cli.py create-user alice
- Example output:
  - UserService initialized, using API at https://api.example.com
  - Calling 'https://api.example.com/users' with key 'my-s...' to create user 'alice'
  - ...Success!
  - CLI: Successfully created user 'alice'.

6. Benefits

- Testable: You can unit-test UserService in complete isolation by just injecting a mock AppConfig. You don't need to run a CLI subprocess.
- Configurable: Your logic is configured by pico-ioc’s unified system, not hard-coded with os.environ.get(). You can easily add file sources or other sources via the configuration(...) builder.
- Flexible: Your UserService component could be reused in a web application without changing a single line of code.

-----

Optional: Unit Testing Example

```python
# tests/test_services.py
from app.services import UserService
from app.config import AppConfig

def test_create_user_happy_path(capfd):
    config = AppConfig(API_KEY="abc123", API_URL="https://api.example.com")
    svc = UserService(config)
    svc.create_user("alice")
    out, err = capfd.readouterr()
    assert "create user 'alice'" in out
```

-----

Next Steps

This concludes the "Cookbook" section. You now have a set of complete, high-level patterns for building robust applications.

The final section, Architecture, dives into the "Why" and "How" of pico-ioc’s internal design, for those who want to contribute or understand the framework at the deepest level.

- Architecture Overview (../architecture/README.md): An introduction to the design principles and internal components of pico-ioc.
