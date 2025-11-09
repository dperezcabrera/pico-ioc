## ADR-005: AOP Implementation via Method Interception

Status: Accepted

### Context

Applications often require cross-cutting concerns (logging, tracing, caching, security, transactions) applied across multiple methods. Manually adding this logic pollutes business code and violates the DRY (Don't Repeat Yourself) principle. We needed a non-intrusive way to add behavior around method calls.

### Decision

We implemented Aspect-Oriented Programming (AOP) using method interception:

1. MethodInterceptor Protocol: Defined an interface with an invoke(ctx: MethodCtx, call_next) method. Implementations of this protocol contain the cross-cutting logic.
2. @intercepted_by(InterceptorType, ...) Decorator: Applied to component methods to specify which interceptors should wrap them. Interceptors themselves must be registered components.
3. UnifiedComponentProxy: An internal dynamic proxy. When a component with intercepted methods is resolved, it's wrapped in this proxy.
4. __getattr__ Hook: The proxy's __getattr__ intercepts calls to decorated methods. It resolves the required interceptor instances from the container and builds an execution chain (dispatch_method) that calls each interceptor's invoke method around the original method call.
5. Async Awareness: The proxy and dispatch_method were designed to correctly handle await for async def intercepted methods and async def invoke methods.

### Consequences

Positive:
- Cleanly separates cross-cutting concerns from business logic.
- Interceptors are reusable and testable components.
- The @intercepted_by decorator is explicit and declarative.
- Supports both sync and async methods seamlessly.
- Avoids complex bytecode manipulation, relying only on standard Python features (proxies, decorators).

Negative:
- Adds a layer of indirection (the proxy), which can slightly complicate debugging if not understood.
- Minor performance overhead due to proxying and interceptor chain execution on each call to an intercepted method (though caching of the wrapped method helps).
- Relies on dynamic proxying, which might interact unexpectedly with tools that do heavy introspection.

### Alternatives Considered

- Metaclass-based weaving: Rejected to avoid metaclass constraints and complexity when combining with existing class hierarchies.
- Bytecode weaving/instrumentation: Rejected due to fragility, tooling complexity, and reduced debuggability.
- Manual decorators per concern: Rejected as it spreads concern-specific code across many call sites and becomes error-prone.
- Monkey-patching at runtime: Rejected due to maintenance risks and lack of type-safety and clarity.

### Notes

- Interceptor execution order follows the order declared in @intercepted_by.
- Interceptors must be registered/resolvable in the container to be applied.
- Wrapped methods are cached per instance to reduce repeated proxy-chain construction overhead.
