# FEATURE-2025-0010: Dynamic Container — Lifecycle Events, Scopes & Hot-Reload

  * **Date:** 2025-09-18
  * **Status:** Draft
  * **Priority:** High
  * **Related:** FEATURE-2025-0007 (Infrastructure Binding), FEATURE-2025-0009 (Unified `@role`)

---

## 1\) Summary

Evolve the `pico-ioc` container from a static, bootstrap-time configuration engine to a **dynamic, context-aware runtime**. This is achieved by introducing three core pillars:

1.  A **Lifecycle Event Bus** that allows components to react to container and application events.
2.  **Dynamic Scopes** like `@RequestScoped`, to manage the lifecycle of components tied to short-lived contexts (e.g., an HTTP request).
3.  **Hot-Reload** capabilities, allowing the application to adapt to external configuration changes without requiring a restart.

---

## 2\) Goals

  * Provide robust and clean state management for web and event-driven applications.
  * Enable zero-downtime updates for application configuration (e.g., feature flags, endpoints).
  * Create an extensible ecosystem where components can react to lifecycle events in a decoupled manner.
  * Improve the testability of components that depend on contextual state (e.g., a request's user).

---

## 3\) Non-Goals

  * Implementing a distributed messaging system. The event bus is synchronous and in-process.
  * Supporting hot-swapping of a class's *code* (replacing method logic on the fly). Reconfiguration focuses on re-creating instances with *new configuration*.
  * Managing scope persistence (e.g., `@SessionScoped` would require an external storage backend, which is out of the initial scope).

---

## 4\) User Impact / Stories

  * *As a backend developer*, I can inject a `@RequestScoped UserContext` into my services to safely access user information without passing it as a parameter through every layer.
  * *As an SRE/DevOps engineer*, I can change a value in our central configuration server, and the application will update its behavior (e.g., switch payment providers) without a redeployment.
  * *As a software architect*, I can design components that clear caches or perform other reactive actions by listening to lifecycle events, such as `ConfigurationChangedEvent`.

---

## 5\) Scope & Acceptance Criteria

  * \[ ] Implement a synchronous, in-process `LifecycleEventBus`.
  * \[ ] Introduce the `@Observes(EventType)` decorator for component methods to subscribe to events.
  * \[ ] Implement the `@RequestScoped` scope decorator.
  * \[ ] Provide a context manager (`with container.request_scope(): ...`) so that web frameworks (or tests) can delineate the request lifecycle.
  * \[ ] The container core must listen for `ConfigurationChangedEvent` and be able to invalidate and re-create affected components.
  * \[ ] The `Infra` façade must expose a way to publish custom events (`infra.events.publish(...)`) and control the runtime (`infra.runtime.reload(...)`).

---

## 6\) Public API / UX Contract

### New Decorators

```python
from pico_ioc import RequestScoped, SessionScoped, Observes

@RequestScoped
class UserContext: ...

@component
class CacheManager:
    @Observes(ComponentUpdatedEvent)
    def invalidate_cache(self, event: ComponentUpdatedEvent):
        # Logic to invalidate the cache when a component is updated
        ...
```

### `Infra` Façade API (extended)

```python
class Infra:
    # ... (bind, intercept, mutate, query)
    @property
    def events(self) -> "InfraEvents": ...
    @property
    def runtime(self) -> "InfraRuntime": ...

class InfraEvents:
    def publish(self, event: object) -> None: ...

class InfraRuntime:
    def reload(self, *component_keys: Any) -> None: ...
```

### Event Classes

```python
class PicoEvent: ... # Base class

class ConfigurationChangedEvent(PicoEvent):
    def __init__(self, key: str, old_value: Any, new_value: Any): ...
```

---

## 7\) Examples

### A) Per-Request State Management (Web API)

```python
@RequestScoped
class RequestContext:
    def __init__(self, request: HttpRequest): # The framework would inject the request
        self.trace_id = request.headers.get("X-Trace-ID")

@component
class MyService:
    def __init__(self, db: Database, context: RequestContext):
        self.db = db
        self.trace_id = context.trace_id # Easy and safe access to the trace_id

    def do_work(self):
        self.db.execute("...", trace_id=self.trace_id)
```

### B) Reacting to Events to Invalidate a Cache

```python
@component
class MyCache: ...

@component
class CacheInvalidator:
    def __init__(self, cache: MyCache):
        self.cache = cache

    @Observes(ConfigurationChangedEvent)
    def on_config_change(self, event: ConfigurationChangedEvent):
        if "cache.ttl" in event.key:
            print("Cache TTL configuration changed. Clearing cache...")
            self.cache.clear_all()
```

### C) Hot-Reloading a Component on a Feature Flag Change

```python
# A factory that depends on an injected configuration
@factory
class PaymentGatewayFactory:
    def __init__(self, config: AppConfig):
        self.config = config

    @provides
    def get_gateway(self) -> PaymentGateway:
        if self.config.get("payment.provider") == "stripe":
            return StripeGateway()
        else:
            return PaypalGateway()

# Infrastructure that manages the hot-reload
@infra
class DynamicConfigInfra:
    @Observes(ConfigurationChangedEvent)
    def handle_config_change(self, event: ConfigurationChangedEvent, infra: Infra):
        if event.key == "payment.provider":
            print(f"Payment provider changed to '{event.new_value}'. Reloading affected components...")
            # We tell the container to reload the factory and, therefore, the gateway
            infra.runtime.reload(PaymentGatewayFactory, PaymentGateway)
```

---

## 8\) Risks & Mitigations

  * **Risk:** Scope management can introduce memory leaks if contexts are not properly closed.
    **Mitigation:** The implementation must be robust (using `contextvars`), and the documentation must be very clear about the need to use the context manager (`with container.request_scope()`).
  * **Risk:** The event system can add complexity and make the application flow harder to follow.
    **Mitigation:** Keep the event bus synchronous and in-process initially. Provide diagnostic tools to trace the event chain.
  * **Risk:** Hot-Reload can leave the application in an inconsistent state if not managed carefully.
    **Mitigation:** The `reload` process must be transactional and well-defined. The documentation should warn about side effects in stateful components.

---

## 9\) Documentation Impact

  * Create a new guide: `GUIDE-LIFECYCLE.md` to explain the event bus and observers.
  * Create a new guide: `GUIDE-SCOPES.md` to detail the use of `@RequestScoped` and other scopes.
  * Update the infrastructure guide to include the new `infra.events` and `infra.runtime` APIs.

---

**TL;DR**: The container evolves to be dynamic. It introduces a lifecycle event bus, new scopes like `@RequestScoped` for managing short-lived state, and the ability to hot-reload components when external configuration changes, all without requiring an application restart.
