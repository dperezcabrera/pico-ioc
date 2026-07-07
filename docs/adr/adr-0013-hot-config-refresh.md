# ADR-013: Hot Configuration Refresh

Status: Accepted

## Context

Tree configuration is resolved once by `ConfigResolver` and cached; `@configured`
components are built from that snapshot at container init. Applications that
want to pick up config changes at runtime (edited YAML, a remote source, a
Spring-Cloud-style admin) had no supported path short of rebuilding the
container.

Two designs were considered:

1. **Watchable sources**: extend `TreeSource` with change-notification
   machinery (callbacks, watch threads) that every primitive implements.
2. **Resolver-level refresh**: keep sources pull-based (`get_tree()` is already
   stateless — file sources re-read on every call) and put the refresh where
   the staleness actually lives: the resolver's cached merged tree.

## Decision

Resolver-level refresh (option 2):

1. `ConfigResolver.refresh()` re-runs load → merge → interpolate, diffs the old
   and new trees per top-level prefix using the existing `canonicalize()`
   fingerprint, swaps the cached tree, and returns the changed prefixes as a
   `frozenset`.
2. `PicoContainer.refresh_config()` delegates to the `ConfigurationManager`
   (attached by the `Registrar` at wiring time) and, when something changed and
   an `EventBus` is registered, publishes `ConfigChanged(prefixes=...)`
   (ADR-007).
3. Triggers live outside the core: a file watcher, an HTTP endpoint (e.g. a
   future `/actuator/refresh`), or a poller simply calls
   `container.refresh_config()`. Push-style sources need no new contract.

Propagation semantics are explicit and minimal:

- Already-created components keep the values they were built with; components
  that need live values subscribe to `ConfigChanged` and re-read their subtree.
- New resolutions (components created after the refresh) see the new tree.
- Flat sources (`EnvSource`, `FlatDictSource`) are read live at build time and
  have no diffable snapshot; they do not participate in the diff.
- The diff baseline is the last observed tree: resolution is lazy, so a
  `refresh()` before any read establishes the baseline instead of reporting
  changes.

## Alternatives rejected

- **Watchable `TreeSource`**: forces watching machinery (threads, inotify,
  callbacks) into every source implementation and couples the source contract
  to a delivery mechanism. Pull sources compose; watchers do not.
- **Mutating built config objects in place**: `@configured` instances are
  plain (often frozen) dataclasses; mutating them behind consumers' backs is
  unsafe and unobservable.
- **Refresh scope (Spring `@RefreshScope`-style re-creation)**: deferred, not
  rejected. Event-driven re-read covers current needs; a scope that re-creates
  `@configured` components on next access can be layered on top later without
  changing this design.

## Consequences

Positive:
- Hot reload with zero new abstractions: reuses `canonicalize()`, the
  `EventBus`, and the pull-based source contract.
- Sources stay trivial to implement; remote sources (HTTP, git) work today.
- Deterministic, testable semantics (changed-prefix set as the API).

Negative:
- Consumers must opt in via `ConfigChanged`; nothing updates automatically.
- Per-prefix granularity: a change anywhere under `db` reports `db`, not
  `db.pool.size`.
- A `version()`/etag hint on `TreeSource` (to skip refetching unchanged remote
  sources) was considered and left out until a real remote source needs it.

Regression tests: `tests/test_config_refresh.py`.
