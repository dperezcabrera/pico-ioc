# Qualifiers & List Injection

In the guides so far, we've assumed a simple, one-to-one relationship: you ask for `Database`, you get one `Database`.

But what about a one-to-many relationship? This is a very common scenario:

* You have one `Sender` interface, but multiple implementations: `EmailSender`, `SmsSender`, and `PushNotificationSender`.
* You have one `PaymentProvider` protocol, but two implementations: `StripeProvider` and `PayPalProvider`.

This creates two problems:
1.  If a component just asks for `Sender`, how does the container know *which one* to inject? (This is solved by [`primary=True`](./conditional-binding.md)).
2.  What if a component (like a `NotificationService`) needs *all* `Sender` implementations?

This guide solves the second problem using **Qualifiers**. Qualifiers are "tags" you attach to your components, allowing you to inject specific *lists* of implementations.

---

## 1. The Concept: Tag and Request

The pattern is simple:

1.  **Define a Tag:** You create a `Qualifier` instance. This is your tag.
    ```python
    from pico_ioc import Qualifier

    NOTIFICATION = Qualifier("notification")
    PAYMENT = Qualifier("payment")
    ```
2.  **Tag Your Components:** You use the `qualifiers=[...]` parameter within the `@component` or `@provides` decorators to apply one or more tags to your components.
    ```python
    from pico_ioc import component
    # Assume NOTIFICATION and PAYMENT are Qualifier instances

    @component(qualifiers=[NOTIFICATION]) # <-- Pass qualifiers as a list/tuple
    class EmailSender(Sender): ...

    @component(qualifiers=[NOTIFICATION])
    class SmsSender(Sender): ...

    @component(qualifiers=[PAYMENT])
    class StripeProvider(PaymentProvider): ...
    ```
    *(Note: Previously, a `@qualifier` decorator was used, but this was replaced by the `qualifiers` parameter for a unified API, as described in ADR-009).*
3.  **Request a Tagged List:** In your service, you use `typing.Annotated` to request a `List` of all components that match a specific `Qualifier`.
    ```python
    from typing import List, Annotated

    @component
    class NotificationService:
        def __init__(
            self,
            senders: Annotated[List[Sender], NOTIFICATION]
        ):
            # self.senders will be [EmailSender(), SmsSender()]
            self.senders = senders
    ```

---

## 2. Step-by-Step Example

Let's build a complete example. We'll create a `PaymentService` that needs to process a payment with *all* available payment providers.

### Step 1: Define the Interface (Protocol)

First, we define the common interface. A `Protocol` is perfect for this.

```python
# providers.py
from typing import Protocol

class PaymentProvider(Protocol):
    """The common interface for all payment providers."""
    def process_payment(self, amount: float) -> str: ...
````

### Step 2: Define the Qualifiers

We'll create a `Qualifier` to tag all our payment providers.

```python
# providers.py
from pico_ioc import Qualifier

PAYMENT = Qualifier("payment")
```

### Step 3: Tag the Implementations

Now, we create our concrete classes. We decorate them with `@component` as usual, but we also add the `qualifiers=[PAYMENT]` parameter.

```python
# providers.py
from pico_ioc import component

@component(qualifiers=[PAYMENT]) # <-- Pass the qualifier here
class StripeProvider(PaymentProvider):
    def process_payment(self, amount: float) -> str:
        print(f"Processing ${amount} with Stripe...")
        return "stripe_tx_123"

@component(qualifiers=[PAYMENT]) # <-- Pass the qualifier here
class PayPalProvider(PaymentProvider):
    def process_payment(self, amount: float) -> str:
        print(f"Processing ${amount} with PayPal...")
        return "paypal_tx_abc"

@component
class SomeOtherComponent:
    """This component is NOT a payment provider and won't be injected."""
    pass
```

### Step 4: Inject the Tagged List

Finally, we create our `PaymentService`. Its constructor asks for a `List[PaymentProvider]` that is `Annotated` with our `PAYMENT` tag.

```python
# services.py
from typing import List, Annotated
from pico_ioc import component
from .providers import PaymentProvider, PAYMENT

@component
class PaymentService:
    def __init__(
        self,
        providers: Annotated[List[PaymentProvider], PAYMENT]
    ):
        # pico-ioc injects a list of all components
        # tagged with qualifiers=[PAYMENT]
        self.providers = providers
        print(f"PaymentService loaded with {len(self.providers)} providers.")

    def charge(self, amount: float):
        for provider in self.providers:
            provider.process_payment(amount)
```

### Step 5: Run It

When we initialize the container and get the `PaymentService`, it will automatically have the correct list injected.

```python
# main.py
from pico_ioc import init
from services import PaymentService

# We must tell init() to scan both modules
container = init(modules=["providers", "services"])

service = container.get(PaymentService)
service.charge(100.00)

# Output:
# PaymentService loaded with 2 providers.
# Processing $100.00 with Stripe...
# Processing $100.00 with PayPal...
```

The list `service.providers` contains instances of `StripeProvider` and `PayPalProvider`, but *not* `SomeOtherComponent`.

-----

## Summary

Qualifiers are the standard way to manage one-to-many dependencies in `pico-ioc`.

  * **`Qualifier("name")`** creates a unique tag instance (e.g., `PAYMENT = Qualifier("payment")`).
  * **`@component(qualifiers=[TAG, ...])`** (or `@provides`) applies tags to a component.
  * **`Annotated[List[Interface], TAG]`** requests a list of all components that have been tagged with `TAG`.

-----

## Next Steps

You now know how to register components, configure them, control their lifecycle, and inject specific lists. The final piece of the core user guide is learning how to test your application.

  * **[Testing Applications](./testing.md)**: Learn how to use `overrides` and `profiles` to mock dependencies and test your services in isolation.

