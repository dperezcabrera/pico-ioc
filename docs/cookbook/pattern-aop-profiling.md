# Cookbook: Pattern: Method Profiling with AOP

**Goal:** Automatically measure the execution time of specific service methods and log warnings or metrics if they exceed a certain threshold.

**Key `pico-ioc` Features:** AOP (`MethodInterceptor`, `@intercepted_by`), Reading Custom Decorator Metadata.

## The Pattern

1.  **Metadata Decorator (`@profiled`):** (Optional) A decorator to attach metadata, like a `warn_threshold_ms`, to methods.
2.  **Profiling Interceptor (`ProfilingInterceptor`):** A `@component` implementing `MethodInterceptor`. It:
    * Uses `time.perf_counter()` before and after `call_next(ctx)`.
    * Calculates the duration.
    * Logs the duration (e.g., at DEBUG level).
    * (Optional) Reads the threshold from `@profiled` metadata. If duration exceeds it, logs a WARNING or sends a metric.
3.  **Alias (`profile_execution`):** An alias for `@intercepted_by(ProfilingInterceptor)`.
4.  **Application:** Classes or methods to be profiled are decorated with `@profile_execution` (and optionally `@profiled`).

## Example Implementation (Conceptual)

#### Decorator (`profiling_lib/decorator.py`)
```python
import functools
PROFILED_META = "_pico_profiled_meta"

def profiled(*, warn_threshold_ms: int = 500):
    def decorator(func):
        metadata = {"warn_threshold_ms": warn_threshold_ms}
        setattr(func, PROFILED_META, metadata)
        @functools.wraps(func)
        def wrapper(*args, **kwargs): return func(*args, **kwargs)
        setattr(wrapper, PROFILED_META, metadata)
        return wrapper
    return decorator
```

#### Interceptor (`profiling_lib/interceptor.py`)

```python
import time
import logging
from pico_ioc import component, MethodInterceptor, MethodCtx, intercepted_by
from .decorator import PROFILED_META

log = logging.getLogger("Profiler")

@component
class ProfilingInterceptor(MethodInterceptor):
    def invoke(self, ctx: MethodCtx, call_next):
        start_time = time.perf_counter()
        try:
            result = call_next(ctx)
            return result
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            # Read metadata if decorator was used
            threshold = 500 # Default threshold
            try:
                original_func = getattr(ctx.cls, ctx.name)
                profile_meta = getattr(original_func, PROFILED_META, None)
                if profile_meta:
                    threshold = profile_meta.get("warn_threshold_ms", threshold)
            except AttributeError:
                pass

            msg = f"Execution time for {ctx.cls.__name__}.{ctx.name}: {duration_ms:.2f} ms"
            
            if duration_ms > threshold:
                log.warning(f"{msg} [EXCEEDED THRESHOLD of {threshold} ms]")
            else:
                log.debug(msg) # Or INFO

profile_execution = intercepted_by(ProfilingInterceptor)
```

*(The rest of the setup - `__init__.py`, application code, `main.py` - would follow the same structure as the Logging example).*

## Benefits

  * **Performance Insight:** Automatically measures critical code paths.
  * **Declarative:** Clearly mark methods for profiling.
  * **Non-Intrusive:** Business logic remains untouched.
