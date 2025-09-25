# Getting Started: 5-Minute Tutorial

Welcome to `pico-ioc`! 🚀

This guide will get you installed and running your first dependency-injected application in less than 5 minutes. We'll go from an empty file to a fully-wired application.

By the end of this tutorial, you will understand the three most fundamental APIs in `pico-ioc`:

1.  **`@component`**: The decorator that registers your classes with the container.
2.  **`init()`**: The function that scans your project and builds the container.
3.  **`container.get()`**: The method you use to ask the container for your final, fully-wired object.

---

## 1. Installation

`pico-ioc` requires **Python 3.10** or newer.

You can install it directly from PyPI using `pip`:

```bash
pip install pico-ioc
````

This core package includes all the necessary logic. For advanced, tree-based configuration from YAML files (covered in the User Guide), you can install the optional dependency:

```bash
pip install pico-ioc[yaml]
```

-----

## 2\. The 5-Minute Tutorial

Let's build a simple "Hello, World\!" application.

### Step 1: Define Your Components

First, create a file named `app.py`. We'll define two classes:

1.  `GreeterService`: A simple service with one job: providing a greeting.
2.  `App`: Our main application class, which *depends on* the `GreeterService`.

The `@component` decorator is the core of `pico-ioc`. It's a marker that tells the container: "Find this class, scan its dependencies, and make it available for injection."

```python
# app.py
from pico_ioc import component

@component
class GreeterService:
    """A service that provides a greeting."""
    def greet(self) -> str:
        return "Hello, pico-ioc!"

@component
class App:
    """Our main application class."""
    
    # pico-ioc will see this and inject GreeterService
    def __init__(self, greeter: GreeterService):
        self.greeter = greeter
        
    def run(self):
        # Use the injected service
        print(self.greeter.greet())
```

#### **What's happening here?**

  * `@component` on `GreeterService` tells `pico-ioc` to register this class. It has no dependencies.
  * `@component` on `App` also registers it.
  * `def __init__(self, greeter: GreeterService):` This is the magic. `pico-ioc` reads your constructor's type hints. It sees that `App` requires an instance of `GreeterService` and understands that it must provide one when building an `App`.

-----

### Step 2: Initialize the Container

Now, at the bottom of your `app.py`, we need to tell `pico-ioc` to find these components. We do this by calling `init()`.

`init()` is the function that builds the container. Its most important argument is `modules`, which tells it where to look for `@component` decorators.

```python
# app.py
from pico_ioc import component, init

# ... (GreeterService and App classes from above) ...

if __name__ == "__main__":
    # Scan the current module (this file)
    # and find all @component decorators
    container = init(modules=[__name__])
```

#### **What's happening here?**

  * `if __name__ == "__main__":` ensures this code only runs when the script is executed directly.
  * `container = init(modules=[__name__])`: This line does all the work:
    1.  It scans the module specified (in this case, `__name__` refers to the current file, `app.py`).
    2.  It finds `GreeterService` and `App`.
    3.  It validates their dependencies (sees that `App` needs `GreeterService` and that `GreeterService` is available).
    4.  It returns a `PicoContainer` instance, which is now a fully-configured *factory* ready to build your components.

-----

### Step 3: Get Your Component and Run

The `container` object now knows how to build `App` and its entire dependency tree. We can ask for the final `App` instance using `container.get()` and then call its `run()` method.

```python
# app.py
from pico_ioc import component, init

# ... (GreeterService and App classes from above) ...

if __name__ == "__main__":
    container = init(modules=[__name__])
    
    # Ask the container for the 'App' instance
    app = container.get(App)
    
    # Run the application
    app.run()
```

#### **What's happening here?**

When you call `container.get(App)`, `pico-ioc` performs a "depth-first" resolution:

1.  It sees you want an `App`.
2.  It checks `App`'s dependencies and sees it needs a `GreeterService`.
3.  It checks `GreeterService`'s dependencies (it has none).
4.  It creates the `GreeterService` instance (and caches it for future use).
5.  It creates the `App` instance, injecting the `GreeterService` instance into its constructor.
6.  It returns the fully-wired `App` instance to you.

-----

## 3\. Putting It All Together

Here is the complete, runnable `app.py` file.

```python
# app.py
from pico_ioc import component, init

# 1. Define components
@component
class GreeterService:
    """A service that provides a greeting."""
    def greet(self) -> str:
        return "Hello, pico-ioc!"

@component
class App:
    """Our main application class."""
    
    # 2. Define dependencies via type hints
    def __init__(self, greeter: GreeterService):
        self.greeter = greeter
        
    def run(self):
        # Use the injected service
        print(self.greeter.greet())

# 3. Initialize and run
if __name__ == "__main__":
    # Scans this module and finds App/GreeterService
    container = init(modules=[__name__])
    
    # Resolves App and its GreeterService dependency
    app = container.get(App)
    
    app.run()
```

Run it from your terminal:

```bash
$ python app.py
Hello, pico-ioc!
```

-----

## 4\. Next Steps

Congratulations\! You've successfully built your first `pico-ioc` application.

You've learned the three core APIs: `@component` to register classes, `init()` to build the container, and `container.get()` to resolve components.

Now you're ready to explore the core features in the **[User Guide](./user-guide/README.md)**.

```

