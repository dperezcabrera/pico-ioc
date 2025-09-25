# Observability: Observers & Metrics

`pico-ioc` provides two levels of insight into your container's performance:

1.  **Built-in Metrics (`container.stats()`)**: A simple method that returns a dictionary of key performance indicators (KPIs) like cache hit rate and component count.
2.  **Observers (`ContainerObserver`)**: An advanced protocol you can implement to receive low-level events (like `"on_resolve"`) for real-time integration with tracing tools like OpenTelemetry.

---

## 1. Built-in Metrics: `container.stats()`

This is the quickest way to get a snapshot of your container's health and performance.

The `container.stats()` method returns a dictionary containing useful runtime information.

```python
from pico_ioc import init, component

@component
class MyService: ...

container = init(modules=[__name__], profiles=("prod",))

# --- Simulate some activity ---
service = container.get(MyService) # This is a "resolve"
service = container.get(MyService) # This is a "cache hit"

# --- Get the stats ---
stats_report = container.stats()

import json
print(json.dumps(stats_report, indent=2))
````

**Example Output:**

```json
{
  "container_id": "c68a1f...",
  "profiles": [
    "prod"
  ],
  "uptime_seconds": 0.00312,
  "total_resolves": 1,
  "cache_hits": 1,
  "cache_hit_rate": 0.5,
  "registered_components": 1
}
```

This dictionary is lightweight and can be easily exposed via a `/stats` endpoint or fed into a metrics-gathering system like Prometheus.

  * **`total_resolves`**: The number of times the container had to *create* a new component. (Lower is often better).
  * **`cache_hits`**: The number of times `get()` was called for a component that was already in the cache.
  * **`cache_hit_rate`**: The ratio of hits to total requests. A high cache hit rate is a sign of a healthy singleton-based application.

-----

## 2\. Advanced: `ContainerObserver` Protocol

For deep, real-time tracing, you can implement the `ContainerObserver` protocol.

An observer is a class that "listens" to the container's internal events. You can pass a list of observers to `init()`, and the container will notify them when key events happen.

This is the perfect integration point for tools like **OpenTelemetry**, allowing you to create a "span" for every component resolution.

### Step 1: Define Your Observer

Implement the `ContainerObserver` protocol. You only need to implement the methods you care about.

```python
# tracing.py
import time
from pico_ioc import ContainerObserver, KeyT

# A simple observer that just logs events
class MyTracer(ContainerObserver):
    
    def on_resolve(self, key: KeyT, took_ms: float):
        """
        Called *after* a component is successfully created.
        """
        print(f"[TRACE] RESOLVED: {key} (took {took_ms:.2f} ms)")

    def on_cache_hit(self, key: KeyT):
        """
        Called when a component is retrieved from the cache.
        """
        print(f"[TRACE] CACHE HIT: {key}")

# Here is what a real OpenTelemetry observer might look like:
#
# from opentelemetry import trace
# tracer = trace.get_tracer(__name__)
#
# class OpenTelemetryObserver(ContainerObserver):
#     def on_resolve(self, key: KeyT, took_ms: float):
#         # Create a span for the resolution
#         with tracer.start_as_current_span("pico.resolve") as span:
#             span.set_attribute("pico.key", str(key))
#             span.set_attribute("pico.resolve_time_ms", took_ms)
#
#     def on_cache_hit(self, key: KeyT):
#         # Just add an event to the current span
#         span = trace.get_current_span()
#         span.add_event("pico.cache_hit", {"pico.key": str(key)})
```

### Step 2: Register Your Observer

`ContainerObserver` is **not** a component. You cannot register it with `@component`.

Instead, you must instantiate it yourself and pass it to the `init()` function.

```python
# main.py
from pico_ioc import init, component
from tracing import MyTracer

@component
class ServiceA:
    def __init__(self):
        # Simulate work
        time.sleep(0.01)

@component
class ServiceB:
    def __init__(self, a: ServiceA):
        pass

# 1. Instantiate your observer
tracer = MyTracer()

# 2. Pass it to init()
container = init(
    modules=[__name__],
    observers=[tracer] # <-- Register it here
)

print("--- First call (resolving) ---")
b = container.get(ServiceB)

print("\n--- Second call (cached) ---")
b_cached = container.get(ServiceB)
```

**Example Output:**

```
--- First call (resolving) ---
[TRACE] RESOLVED: <class '__main__.ServiceA'> (took 10.05 ms)
[TRACE] RESOLVED: <class '__main__.ServiceB'> (took 10.12 ms)

--- Second call (cached) ---
[TRACE] CACHE HIT: <class '__main__.ServiceB'>
```

This gives you a powerful, low-level hook to monitor the container's behavior and performance in real-time.

-----

## Next Steps

Now that you can get metrics and trace events, what if the problem isn't performance, but the *structure* of your application?

  * **[Exporting the Dependency Graph](./exporting-graph.md)**: Learn how to generate a visual diagram of your entire application's dependency graph to hunt down bugs or simplify your architecture.

