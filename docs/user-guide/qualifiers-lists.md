# Injecting Collections: Lists, Sets & Dictionaries

In the guides so far, we've mostly assumed a one-to-one relationship: you ask for `Database`, you get one `Database`.

But what about a one-to-many relationship? This is a very common scenario:
* You have one `Sender` interface, but multiple implementations: `EmailSender`, `SmsSender`, and `PushNotificationSender`.
* A `NotificationService` needs to get *all* of them.
* A `CommandBus` needs a *map* of all `CommandHandlers`.

`pico-ioc` handles all of these scenarios automatically by recognizing collection types in your `__init__` constructor.

---

## 1. Automatic List/Collection Injection

If you ask for a list or set of an interface (like `List[Sender]`, `Set[Sender]`, or `Iterable[Sender]`), `pico-ioc` will:
1.  Find all components that implement or inherit from that interface (`Sender`).
2.  Create an instance of each one.
3.  Inject them as a `list` (regardless of whether you asked for a `List`, `Set`, or `Iterable`).

### Step 1: Define Components

Define multiple components that implement the same interface (`IService` in this case).

```python
# app/services.py
from typing import Protocol
from pico_ioc import component

class IService(Protocol):
    def serve(self) -> str: ...

@component
class ServiceA(IService):
    def serve(self) -> str:
        return "A"

@component
class ServiceB(IService):
    def serve(self) -> str:
        return "B"
```

### Step 2: Inject the Collection

Your consumer component simply requests `List[IService]`, `Set[IService]`, or `Iterable[IService]`.

```python
# app/consumer.py
from typing import List, Set, Iterable
from pico_ioc import component
from app.services import IService

@component
class Consumer:
    def __init__(
        self,
        services_list: List[IService],
        services_set: Set[IService]
    ):
        # This will be [ServiceA(), ServiceB()]
        self.services = services_list
        
        # This will ALSO be [ServiceA(), ServiceB()]
        self.services_set_as_list = services_set
        print(f"Loaded {len(self.services)} services.")

# --- main.py ---
from pico_ioc import init
from app.consumer import Consumer

container = init(modules=["app"])
consumer = container.get(Consumer) # Output: Loaded 2 services.
```

-----

## 2\. Automatic Dictionary Injection

This is a powerful feature for patterns like CQRS or strategy maps. `pico-ioc` can build a dictionary of components, using either **strings** or **types** as the dictionary keys.

### `Dict[str, T]` (Keyed by Name)

If you request `Dict[str, IService]`, `pico-ioc` will inject a dictionary where:

  * **Keys** are the component's registered `name` (from `@component(name=...)`).
  * **Values** are the component instances.

<!-- end list -->

```python
# app/services.py
from pico_ioc import component

@component(name="serviceA") # <-- Registered name
class ServiceA(IService):
    ...

@component(name="serviceB") # <-- Registered name
class ServiceB(IService):
    ...

# app/consumer.py
from typing import Dict
from app.services import IService

@component
class DictConsumer:
    def __init__(self, service_map: Dict[str, IService]):
        # service_map will be:
        # {
        #   "serviceA": ServiceA(),
        #   "serviceB": ServiceB()
        # }
        self.service_map = service_map

    def call_a(self):
        return self.service_map["serviceA"].serve()
```

### `Dict[Type, T]` (Keyed by Type)

If you request `Dict[Type, IService]`, `pico-ioc` will inject a dictionary where:

  * **Keys** are the *class types* of the components (e.g., `ServiceA`, `ServiceB`).
  * **Values** are the component instances.

This is extremely useful for building dispatch maps in patterns like CQRS.

```python
# app/consumer.py
from typing import Dict, Type
from app.services import IService, ServiceA, ServiceB

@component
class TypeDictConsumer:
    def __init__(self, service_map: Dict[Type, IService]):
        # service_map will be:
        # {
        #   ServiceA: ServiceA(),
        #   ServiceB: ServiceB()
        # }
        self.service_map = service_map

    def call_a(self):
        return self.service_map[ServiceA].serve()
```

-----

## 3\. Using Qualifiers to Filter Collections

What if you don't want *all* services, just a specific subset? This is where `Qualifiers` are used. Qualifiers act as **filters** for list and dictionary injections.

1.  **Define a Qualifier:**

    ```python
    from pico_ioc import Qualifier

    FAST_SERVICES = Qualifier("fast")
    SLOW_SERVICES = Qualifier("slow")
    ```

2.  **Tag Your Components:**

    ```python
    @component(name="serviceA", qualifiers=[FAST_SERVICES])
    class ServiceA(IService): ...

    @component(name="serviceB", qualifiers=[FAST_SERVICES, SLOW_SERVICES])
    class ServiceB(IService): ...

    @component(name="serviceC", qualifiers=[SLOW_SERVICES])
    class ServiceC(IService): ...
    ```

3.  **Request a Filtered Collection:**
    You use `typing.Annotated` to combine the collection type with the `Qualifier` tag.

    ```python
    from typing import List, Dict, Annotated

    @component
    class FilteredConsumer:
        def __init__(
            self,
            # Gets [ServiceA(), ServiceB()]
            fast_list: Annotated[List[IService], FAST_SERVICES],
            
            # Gets [ServiceB(), ServiceC()]
            slow_list: Annotated[List[IService], SLOW_SERVICES],

            # Gets {"serviceA": ServiceA(), "serviceB": ServiceB()}
            fast_map: Annotated[Dict[str, IService], FAST_SERVICES]
        ):
            ...
    ```

### Summary: Injection Rules

  * `List[T]`: Injects a `list` of all components implementing `T`.
  * `Dict[str, T]`: Injects a `dict` mapping component `name` to the instance.
  * `Dict[Type, T]`: Injects a `dict` mapping component `type` to the instance.
  * `Annotated[List[T], Q("tag")]`: Injects a `list` of all `T` components *filtered* by the "tag".
  * `Annotated[Dict[...], Q("tag")]`: Injects a `dict` of all `T` components *filtered* by the "tag".

-----

## Next Steps

You now know how to register components, configure them, control their lifecycle, and inject specific lists or dictionaries. The final piece of the core user guide is learning how to test your application.

  * Testing Applications: Learn how to use `overrides` and `profiles` to mock dependencies and test your services in isolation. See [Testing Applications](./testing.md).

<!-- end list -->

