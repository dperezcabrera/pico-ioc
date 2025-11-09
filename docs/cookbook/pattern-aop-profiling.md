# Cookbook: Pattern: Method Profiling with AOP

Goal: Automatically measure the execution time of specific service methods and log warnings or metrics if they exceed a certain threshold.

Key pico-ioc Features: AOP (MethodInterceptor, @intercepted_by), Reading custom decorator metadata.

Overview:
- Attach optional profiling metadata to methods (for thresholds).
- Use an AOP interceptor to time execution and log the duration.
- Apply a simple alias decorator to enable profiling on classes or methods.
- Keep business logic untouched and profiling declarative.

The Pattern

1) Metadata decorator (@profiled):
- Optional. Adds metadata such as warn_threshold_ms to a method.
- The interceptor reads this metadata, if present, to decide when to warn.

2) Profiling interceptor (ProfilingInterceptor):
- A @component implementing MethodInterceptor.
- Uses time.perf_counter() before/after call_next(ctx).
- Calculates duration in milliseconds.
- Logs duration (DEBUG/INFO).
- If duration exceeds warn_threshold_ms, logs WARNING (or emits a metric).

3) Alias (@profile_execution):
- A convenience alias produced by intercepted_by(ProfilingInterceptor).
- Apply it at class or method level to enable profiling.

4) Application:
- Decorate classes or methods with @profile_execution and optionally @profiled to set thresholds.


Example Implementation

Decorator (profiling_lib/decorator.py)
```python
import functools

PROFILED_META = "_pico_profiled_meta"

def profiled(*, warn_threshold_ms: int = 500):
    """
    Optional decorator to attach profiling metadata to a method.
    warn_threshold_ms: If the execution exceeds this threshold, a WARNING is logged.
    """
    def decorator(func):
        metadata = {"warn_threshold_ms": warn_threshold_ms}

        # Preserve function identity and copy metadata to both original and wrapper.
        setattr(func, PROFILED_META, metadata)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        setattr(wrapper, PROFILED_META, metadata)
        return wrapper
    return decorator
```

Interceptor (profiling_lib/interceptor.py)
```python
import time
import logging
from pico_ioc import component, MethodInterceptor, MethodCtx, intercepted_by
from .decorator import PROFILED_META

log = logging.getLogger("Profiler")

@component
class ProfilingInterceptor(MethodInterceptor):
    def invoke(self, ctx: MethodCtx, call_next):
        """
        Measures time around the intercepted call.
        ctx: MethodCtx with information about target/class, method name, arguments, etc.
        call_next: Function to call the next interceptor/actual method.
        """
        start_time = time.perf_counter()
        try:
            return call_next(ctx)
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Default threshold
            threshold = 500

            # Read metadata if @profiled decorator was used
            try:
                original_func = getattr(ctx.cls, ctx.name)
                profile_meta = getattr(original_func, PROFILED_META, None)
                if profile_meta:
                    threshold = profile_meta.get("warn_threshold_ms", threshold)
            except AttributeError:
                # If method/function not accessible as attribute, ignore metadata
                pass

            msg = f"Execution time for {ctx.cls.__name__}.{ctx.name}: {duration_ms:.2f} ms"

            if duration_ms > threshold:
                log.warning(f"{msg} [EXCEEDED THRESHOLD of {threshold} ms]")
            else:
                log.debug(msg)

# Alias to apply the interceptor
profile_execution = intercepted_by(ProfilingInterceptor)
```

Usage Example (service code)
```python
# app/services/report_service.py
from profiling_lib.decorator import profiled
from profiling_lib.interceptor import profile_execution

class ReportService:
    @profile_execution
    @profiled(warn_threshold_ms=250)
    def generate_report(self, filters):
        # Business logic ...
        data = self._load_data(filters)
        return self._format(data)

    @profile_execution
    def _load_data(self, filters):
        # Simulate IO or computations
        # ...
        return {"items": []}

    def _format(self, data):
        # Not profiled; only business logic
        return {"count": len(data["items"])}
```

Package Layout (example)
- profiling_lib/
  - __init__.py
  - decorator.py
  - interceptor.py
- app/
  - services/
    - report_service.py
- main.py

Minimal bootstrap (main.py)
```python
import logging

# Configure logging for visibility
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

# Instantiate and use the service via pico-ioc as you normally would.
# If you directly instantiate, interceptor behavior depends on how pico-ioc applies proxies.
# In many setups, interceptors engage when instances are created/resolved by the container.

from app.services.report_service import ReportService

svc = ReportService()
svc.generate_report({"range": "last_24h"})
```

Notes and Tips
- Where to apply: You can annotate entire classes with @profile_execution to profile all methods, or individual methods for finer control.
- Decorator order: Either order works in most cases. If in doubt, place @profile_execution closest to the method (topmost) and @profiled below it.
- Threshold defaults: If @profiled is omitted, ProfilingInterceptor uses its default threshold (500 ms in the example).
- Logging level: Adjust logging configuration to see DEBUG messages. WARNING is emitted when thresholds are exceeded.
- Metadata fallback: The interceptor gracefully handles cases where metadata is not present or the method is not directly accessible as a class attribute.
- Extending to metrics: Replace the WARNING log with emission to your metrics system (e.g., statsd, Prometheus client) based on the same threshold logic.
- Async methods: If your services have async methods, ensure your interceptor and container configuration support timing async call paths. If call_next returns an awaitable, wrap timing around the awaited call accordingly.
