# Cookbook: Pattern: Hot Reload (Dev Server)

**Goal:** Create a development server that automatically detects code changes (e.g., when you save a `.py` file) and reloads the `pico-ioc` container, all without stopping the main server process.

This is much faster than a full server restart (like `uvicorn --reload`) because you're only reloading your application's *logic*, not the server itself.

**Problem:** When you change a service's code (e.g., `services.py`), the running application is still using the *old* version of that service, which was loaded and cached by `pico-ioc` at startup.

**Solution:** We will use a file-watching library (like `watchdog`) to monitor our source code directory.
1.  When a `.py` file is changed, the watcher will trigger an event.
2.  The event handler will:
    a.  Call `container.shutdown()` on the **old container** to clean up its resources and remove it from the global registry.
    b.  Call `init()` again to build a **new container** from the *new* source code.
    c.  Atomically replace the global `container` variable with the new one.
3.  All subsequent requests will use the new, reloaded container.

---

## Requirements

This pattern requires an external library for file watching. `watchdog` is a popular and robust choice.

```bash
pip install watchdog
````

-----

## Full, Runnable Example

This example creates a simple Flask server and a `watchdog` observer that reloads the `pico-ioc` container whenever a file in the `app/` directory changes.

### 1\. Project Structure

```
.
├── app/
│   ├── __init__.py
│   └── services.py  <-- We will edit this file
└── dev_server.py    <-- We will run this file
```

### 2\. The Application (`app/services.py`)

This is our simple service. We'll manually edit the `GREETING` string while the server is running.

```python
# app/services.py
from pico_ioc import component

@component
class MyService:
    # --- EDIT THIS LINE WHILE THE SERVER IS RUNNING ---
    GREETING = "Hello, Version 1!"
    # --------------------------------------------------
    
    def __init__(self):
        print(f"MyService instance CREATED (Version: {self.GREETING})")
    
    def greet(self) -> str:
        return self.GREETING
```

### 3\. The Hot-Reload Server (`dev_server.py`)

This file contains all the logic. It runs Flask and the `watchdog` observer in separate threads.

```python
# dev_server.py
import sys
import time
import threading
from flask import Flask
from pico_ioc import init, PicoContainer
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# --- 1. Global Container Setup ---

# We need a lock to safely swap the container
# from another thread (the watchdog thread).
_container_lock = threading.Lock()

# The global container variable that all threads will share.
# We initialize it once at the start.
container: PicoContainer = init(modules=["app.services"])


def get_current_container() -> PicoContainer:
    """Safely get the current container."""
    with _container_lock:
        return container

def reload_container():
    """
    The core hot-reload logic.
    This is called by the file watcher.
    """
    global container
    print("\n--- [RELOAD] Code change detected! ---")
    
    # We must clear Python's import cache, otherwise
    # it will just re-import the old, cached module.
    # This is a simple way to force a re-import.
    for module_name in list(sys.modules.keys()):
        if module_name.startswith("app."):
            print(f"[RELOAD] Clearing module cache for: {module_name}")
            del sys.modules[module_name]

    try:
        # Build the new container *before* shutting
        # down the old one, to ensure a valid config.
        new_container = init(modules=["app.services"])
        
        # Safely swap the containers
        with _container_lock:
            old_container = container
            container = new_container
            
        print("[RELOAD] New container is active.")
        
        # Shut down the old one *after* the swap
        old_container.shutdown()
        print("[RELOAD] Old container shut down.")
        
    except Exception as e:
        print(f"\n[RELOAD] FAILED to reload container: {e}\n")
        # Keep the old container active if reload fails
        
    print("--- [RELOAD] Ready ---\n")

# --- 2. File Watcher (watchdog) Setup ---

class ReloadHandler(FileSystemEventHandler):
    """Watches for .py file changes."""
    def on_modified(self, event):
        if event.src_path.endswith(".py"):
            reload_container()

def start_file_watcher():
    """Starts the watchdog observer in a background thread."""
    path = "./app" # Watch the 'app' directory
    event_handler = ReloadHandler()
    observer = Observer()
    observer.schedule(event_handler, path, recursive=True)
    observer.start()
    print(f"--- Watchdog monitoring directory: {path} ---")
    return observer

# --- 3. Flask Server Setup ---

app = Flask(__name__)

@app.route("/")
def home():
    """
    This Flask view gets the container on *every request*.
    It will automatically get the new one after a reload.
    """
    current_container = get_current_container()
    
    # Get the service (it will be created and cached
    # by the *current* container instance).
    service = current_container.get("app.services.MyService")
    
    return f"<h1>{service.greet()}</h1>"

# --- 4. Main Entry Point ---

if __name__ == "__main__":
    print("--- Starting dev server with hot-reload ---")
    
    # Start the file watcher in the background
    watcher = start_file_watcher()
    
    # Start the Flask app in the foreground
    # (use_reloader=False is crucial!)
    try:
        app.run(port=5000, debug=True, use_reloader=False)
    finally:
        watcher.stop()
        watcher.join()
        print("--- Server and watcher stopped ---")

```

-----

## 4\. How to Use It

1.  Run the server:

    ```bash
    $ python dev_server.py
    --- Starting dev server with hot-reload ---
    MyService instance CREATED (Version: Hello, Version 1!)
    --- Watchdog monitoring directory: ./app ---
     * Running on [http://127.0.0.1:5000](http://127.0.0.1:5000)
    ```

2.  Open `http://127.0.0.1:5000` in your browser. You will see:
    **Hello, Version 1\!**

3.  Now, **without stopping the server**, open `app/services.py` in your editor and change the `GREETING` string:

    ```python
    # app/services.py
    GREETING = "This is Version 2!"
    ```

4.  Save the file. You will see the following in your `dev_server.py` console:

    ```bash
    --- [RELOAD] Code change detected! ---
    [RELOAD] Clearing module cache for: app.services
    MyService instance CREATED (Version: This is Version 2!)
    [RELOAD] New container is active.
    [RELOAD] Old container shut down.
    --- [RELOAD] Ready ---
    ```

5.  Refresh your browser. You will instantly see:
    **This is Version 2\!**

This pattern combines `container.shutdown()` and `init()` to give you a powerful and fast development loop.

-----

## Next Steps

This pattern is great for web servers. Let's look at a different structure for building applications that don't run forever.

  * **[Pattern: CLI Applications](./pattern-cli-app.md)**: Learn a clean pattern for structuring command-line tools with `pico-ioc`.

