# Cookbook: Pattern: CLI Applications

**Goal:** Build a robust command-line (CLI) application using a library like `Typer` or `Click`, but keep the core logic testable and decoupled using `pico-ioc`.

**Problem:** It's common to put all your application logic directly inside your CLI command functions. This makes your logic hard-coded, impossible to unit-test without simulating a CLI-call, and difficult to configure.

```python
# The "bad" way - logic is trapped in the CLI
import typer
import os # Added for example

# Assume ApiClient exists
class ApiClient:
    def __init__(self, key): self.key = key
    def create(self, username): print(f"API: Creating {username} with key {self.key[:4]}...")

app = typer.Typer()

@app.command()
def create_user(username: str):
    """
    Creates a user.
    """
    # Problem: Logic is hard-coded
    api_key = os.environ.get("API_KEY")
    client = ApiClient(api_key)
    
    try:
        client.create(username)
        print(f"Success! User '{username}' created.")
    except Exception as e:
        print(f"Error: {e}")
```

**Solution:** The CLI command should only be a thin "wrapper." The *real* work should be done by a `pico-ioc`-managed service.

1.  **`main()`:** The `main` entrypoint of your CLI app is responsible for `init()`ing the `pico-ioc` container, providing configuration via the `configuration(...)` builder.
2.  **Configuration:** Your settings (like `API_KEY`) are loaded into a `@configured` dataclass (using `mapping="flat"` or `"auto"`).
3.  **Services:** Your core logic (like `UserService`) is a `@component` that injects the configuration.
4.  **CLI Command:** The `@app.command()` function just `get`s the service from the container and calls its method.

-----

## Requirements

This pattern works best with a dedicated CLI library. `typer` is a great, modern choice.

```bash
pip install typer
```

-----

## Full, Runnable Example

This example builds a CLI tool that can create a user, with its API key managed by `pico-ioc`.

### 1\. Project Structure

```
.
├── app/
│   ├── __init__.py
│   ├── config.py    <-- Configuration dataclass (@configured)
│   └── services.py  <-- Business logic
└── cli.py           <-- Typer app
```

### 2\. The Configuration (`app/config.py`)

We define a `dataclass` to hold our settings, loaded from environment variables using `@configured` with a flat mapping.

```python
# app/config.py
from dataclasses import dataclass
# Use @configured instead of @configuration
from pico_ioc import configured

# Use @configured, likely with mapping="auto" or "flat"
@configured(prefix="MYAPP_", mapping="auto") # mapping="auto" should detect flat
@dataclass
class AppConfig:
    API_KEY: str
    API_URL: str = "[https://api.example.com](https://api.example.com)" # Corrected URL string
```

### 3\. The Service (`app/services.py`)

This is our real business logic. It's a standard `@component` that's completely decoupled from the CLI.

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
        
    def create_user(self, username: str):
        if not username:
            raise ValueError("Username cannot be empty")
            
        print(
            f"Calling '{self.api_url}/users' "
            f"with key '{self.api_key[:4]}...' "
            f"to create user '{username}'"
        )
        # ... real api call logic ...
        print("...Success!")
```

### 4\. The CLI (`cli.py`)

This file ties everything together. It creates the `typer` app, initializes `pico-ioc` with the configuration context, and the command function `get`s the service.

```python
# cli.py
import typer
import os # For setting env vars in example run
# Import new configuration tools
from pico_ioc import init, PicoContainer, configuration, EnvSource
# Import service from app package
from app.services import UserService

# 1. Create the Typer app
app = typer.Typer()

# 2. Define configuration context
# Use the configuration builder
config_context = configuration(
    EnvSource(prefix="") # Load flat env vars (MYAPP_API_KEY, etc.)
)

# 3. Initialize the container
# Pass the config_context via the 'config' argument
container: PicoContainer = init(
    modules=["app.config", "app.services"],
    config=config_context
)

# 4. Define the CLI command
@app.command()
def create_user(
    username: str = typer.Argument(..., help="The username to create"),
    force: bool = typer.Option(False, "--force", help="Force creation")
):
    """
    Creates a new user in the system.
    """
    print(f"CLI: Received create_user command for '{username}'")
    
    try:
        # 5. Get the service from the container
        # The CLI function's *only* job is to
        # parse inputs and call the service.
        user_service = container.get(UserService)
        
        # 6. Call the business logic
        user_service.create_user(username)
        
        print(f"CLI: Successfully created user '{username}'.")
        
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

@app.command()
def another_command():
    """Another command that can also use the container."""
    typer.echo("Running another command...")
    # Example: Accessing config directly if needed (though usually via services)
    # from app.config import AppConfig
    # config = container.get(AppConfig)
    # typer.echo(f"API URL from config: {config.API_URL}")
    pass

if __name__ == "__main__":
    # --- Example setup for running ---
    # In a real scenario, these would be set in the shell environment
    print("--- Setting environment variables for example ---")
    os.environ['MYAPP_API_KEY'] = 'my-secret-key-123'
    # os.environ['MYAPP_API_URL'] = '[https://api.dev.local](https://api.dev.local)' # Optional override
    print(f"MYAPP_API_KEY set: {os.environ.get('MYAPP_API_KEY')}")
    print(f"MYAPP_API_URL set: {os.environ.get('MYAPP_API_URL')}") # Will be None if not set
    print("--- Running Typer App ---")
    # --- End Example setup ---
    
    app()

    # --- Cleanup after example run ---
    # del os.environ['MYAPP_API_KEY']
    # if 'MYAPP_API_URL' in os.environ: del os.environ['MYAPP_API_URL']
    # --- End Cleanup ---
```

-----

## 5\. How to Use It

1.  Set the required environment variables:
    ```bash
    export MYAPP_API_KEY="my-secret-key-123"
    # export MYAPP_API_URL="[https://api.prod.com](https://api.prod.com)" # Optional, defaults in dataclass
    ```
2.  Run the CLI:
    ```bash
    $ python cli.py create-user "alice"

    # Example Output (assuming MYAPP_API_URL was not set, using default):
    # --- Setting environment variables for example ---
    # MYAPP_API_KEY set: my-secret-key-123
    # MYAPP_API_URL set: None
    # --- Running Typer App ---
    # UserService initialized, using API at [https://api.example.com](https://api.example.com)
    # CLI: Received create_user command for 'alice'
    # Calling '[https://api.example.com/users](https://api.example.com/users)' with key 'my-s...' to create user 'alice'
    # ...Success!
    # CLI: Successfully created user 'alice'.
    ```

## 6\. Benefits

  * **Testable:** You can unit-test `UserService` in complete isolation by just injecting a mock `AppConfig`. You don't need to run a CLI subprocess.
  * **Configurable:** Your logic is configured by `pico-ioc`'s unified system, not hard-coded with `os.environ.get()`. You can easily add file sources or other sources via the `configuration(...)` builder.
  * **Flexible:** Your `UserService` component could be reused in a web application *without changing a single line of code*.

-----

## Next Steps

This concludes the "Cookbook" section. You now have a set of complete, high-level patterns for building robust applications.

The final section, **Architecture**, dives into the "Why" and "How" of `pico-ioc`'s internal design, for those who want to contribute or understand the framework at the deepest level.

  * **[Architecture Overview](../architecture/README.md)**: An introduction to the design principles and internal components of `pico-ioc`.

