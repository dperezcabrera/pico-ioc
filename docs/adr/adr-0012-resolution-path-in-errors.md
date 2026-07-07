# ADR-012: Resolution Path in Dependency Errors

Status: Proposed (scope reduced after validation — see "Reality check")

## Reality check (2026-07-03)

Two experiments against the current container weaken the original premise:

1. **Missing provider deep in the graph** (`A -> B -> C -> unbound D`): caught
   at `init()` by eager binding validation (ADR-006) as
   `InvalidBindingError: C depends on D which is not bound` — the direct
   dependent is already named, before any request is served.
2. **Constructor raising deep in the graph**: caught at `init()` by eager
   singleton resolution as `ComponentCreationError: Failed to create component
   for key: Deep; cause: ValueError: ...` — the failing component and true
   cause are already named.

The 30-minutes-of-debugging scenario therefore does NOT apply to the default
(eager, singleton) path. The path would only add information for **runtime**
resolution: scoped components (`request`/`session`/`transaction`), `lazy=True`
components, and dynamic factory/qualifier lookups. That is a much smaller
audience than originally claimed, and the failing key is still named even
there — only the *route* is missing.

## Context

When a deep resolution fails — `OrderController` needs `OrderService`, which
needs `PaymentGateway`, which needs an unregistered `HttpClient` — the error
today reports the leaf: `ProviderNotFoundError` carries `key` (`HttpClient`)
and `origin` (`PaymentGateway`), and `ComponentCreationError` chains the
cause. What the user cannot see without a debugger is the *route* that led
there: which top-level request pulled in `PaymentGateway` at all.

In small apps this does not matter — there is one plausible route. In apps
with hundreds of components (the audience pico-ioc targets), the missing
route regularly turns a 30-second fix into a debugging session. Spring's
`UnsatisfiedDependencyException` prints the full bean chain for exactly this
reason, and it is one of the most-cited reasons its errors are considered
best-in-class.

## Decision (proposed, reduced scope)

Accumulate the path **on the error path only** — no bookkeeping on successful
resolutions:

1. As a resolution error propagates up through nested `provider()` calls
   inside the container, each frame prepends its key to a `path: tuple` on the
   exception (creating it at the failure site). No `ContextVar`, no per-hop
   cost on success — the cost is paid only when something already failed.
2. `ProviderNotFoundError` and `ComponentCreationError` render the path when
   present:

   ```
   ProviderNotFoundError: No provider for HttpClient
     required by: OrderController -> OrderService -> PaymentGateway -> HttpClient
   ```

3. The path is capped (e.g. 20 hops); deeper chains render head and tail with
   an ellipsis.

The original ContextVar design is explicitly discarded: it taxed the hot path
to serve an error case, and async-task context copies made the semantics
subtle. Unwind-time accumulation is simpler and free when nothing fails.

## Consequences

Positive:

- Deep DI failures become self-explanatory; no debugger needed to find the
  route into a missing or broken component.
- The `path` attribute is machine-readable — test helpers and observability
  tooling can assert on it.
- No behavior change for successful resolutions; the stack is push/pop around
  the existing resolve path.

Negative:

- A small constant overhead per resolution (one ContextVar update per hop).
  Must be benchmarked; singleton resolution after warm-up should be
  unaffected because instances are cached.
- The message format becomes part of the de-facto contract — tests that match
  full error strings may need updating once.
- Touches `container.py`, the hottest file in the codebase; needs careful
  review and its own test coverage for sync, async, and scoped resolution.

## Alternatives Considered

- Reconstruct the path from `__cause__` chains at print time: rejected —
  `ComponentCreationError` chains give one level per creation, but the chain
  is lost when providers catch and re-raise, and it is not available as data.
- Log the path instead of putting it in the exception: rejected — the person
  seeing the traceback is not always the person with access to logs.
- Leave as is, rely on `origin`: rejected — `origin` gives one hop, which is
  precisely the part of the route that was already obvious.

## Recommendation

After the reality check: **park it** unless scoped/lazy resolution failures
show up as a real support burden. Eager validation (ADR-006) already delivers
most of the value this ADR chased, at init time, which is strictly better than
a nicer runtime error. If implemented, use the reduced-scope design above —
it is small enough (error-path only) that the cost/benefit works even for the
narrow audience.

## Notes

Proposed as a follow-up to the 2026-07 hardening pass (failure isolation in
actuator, plugin import diagnostics in pico-boot, zero-config defaults in
`@configured`). Not scheduled.
