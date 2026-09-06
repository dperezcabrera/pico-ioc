# ADR-014: API Stability and Deprecation Policy

Status: Proposed

Date: 2026-09-06

Scope: every `pico-*` package. ADRs live only in `pico-ioc`, so this one is
the ecosystem's policy; each module's `docs/architecture.md` points here.

## Context

The ecosystem is 18 published packages: `pico-ioc` at 2.x and 17 integration
modules at 0.x, released independently but validated together as a
`pico-bom` release train. A 1.0 graduation is planned (`plan-1.0.md`), and
1.0 is a promise, not a badge: after it, a breaking change costs a major
release. That promise is only worth making if three things are written down
first: what exactly is the public API, how a version number maps to what may
change, and how something gets removed.

The own history argues for care: `pico-ioc` published 1.0.0 three weeks after
0.1.0 and needed 2.0.0 two months later. Users who pinned `>=1,<2` got a
promise that did not hold.

Today the contract is implicit. Modules re-export their API in `__init__.py`
(now pinned by `__all__` and a `tests/test_exports.py` in every package),
`docs/reference.md` documents behaviour with named regression tests, and
`pico-initializer` pins generated projects with `~=0.X.Y` because a 0.x
minor may break. Nothing states a deprecation window, and nothing says whether
a configuration key or a default value is API.

## Decision

### 1. What is public

The public API of a package is exactly:

- The names listed in the package's top-level `__all__`.
- The configuration keys under the package's prefix (the fields of its
  `*Settings` class) and their default values.
- Entry points and CLI commands documented in `docs/reference.md`.
- Behaviour documented in `docs/reference.md` and pinned by a named
  regression test.

Everything else is internal and may change in any release: submodule paths
(`pico_x.registrar`), underscore-prefixed names, method signatures of classes
not in `__all__`, log messages, and the shape of exceptions' messages.
A package must not import an internal name of another `pico-*` package;
`tests/test_exports.py` guards its own surface and `fleet-graduation.sh`
reports cross-package leaks.

### 2. What a version number promises

Semantic versioning, read strictly:

| Change | Before 1.0 | From 1.0 |
|---|---|---|
| Breaking change to a public name, key, default or documented behaviour | minor | major |
| Additive change (new name, new optional key, new behaviour behind a default that keeps the old one) | minor | minor |
| Bug fix, docs, internal refactor, dependency floor bump within the same major | patch | patch |
| Deprecation (warning added, nothing removed) | minor | minor |
| Removal of a deprecated name | minor | major |
| Dropping a Python version that has reached end of life | minor | minor |
| Dropping a supported Python version before its end of life | minor | major |
| Raising the `pico-ioc` floor within the same `pico-ioc` major | patch | patch |
| Requiring a new `pico-ioc` major | minor | major |

Changing a default value is a breaking change: a user who never set the key
gets different behaviour. Ship the new behaviour behind a new key or a new
default that preserves the old result, or bump major.

### 3. How something is removed

1. Add the replacement first, in the same or an earlier release.
2. Emit `DeprecationWarning` from the old path with `warnings.warn(message,
   DeprecationWarning, stacklevel=2)`. The message names the replacement and
   the earliest version that may remove the old path.
3. Record it under a `Deprecated` heading in `CHANGELOG.md` and in
   `docs/reference.md`, and pin it with a test that asserts both the warning
   and that the replacement produces the same result.
4. Keep the old path for at least one minor release and at least 90 days,
   whichever is longer.
5. Remove it only in a release the table above allows (a minor before 1.0, a
   major from 1.0), listed under `Removed` in `CHANGELOG.md`.

Configuration keys follow the same path: the old key keeps working, maps to
the new one, and warns.

### 4. Compatibility across packages

- Every package declares a floor and a ceiling on `pico-ioc`
  (`>=2.x,<3`), and floors on any other `pico-*` it imports. Every
  `from pico_x import Y` in `src/` must exist in the minimum pinned version.
- The `pico-bom` release train is the ecosystem's compatibility statement:
  the set of versions validated together. A new train is a new file; a
  published train is never edited.
- A new `pico-ioc` major is handled per module: a module that supports both
  majors widens its ceiling in a minor; a module that requires the new major
  bumps its own major.

### 5. Graduating a module to 1.0

A module becomes 1.0.0 when all of the following hold:

1. Ninety days without a minor release (no public API change), patches only.
2. `__all__` declared, `docs/reference.md` covering exactly that surface,
   each claim pinned by a named test.
3. No import of another package's internals.
4. Real usage: a case in `pico-examples` with hermetic tests, and the
   ecosystem flagship passing against real infrastructure.
5. This policy adopted: the module's `docs/architecture.md` links here.
6. `pico-ioc` floor on the current 2.x series.

1.0.0 carries no code change: it is the last 0.x re-tagged, so "no breaking
change" is verifiable as an empty diff of `src/`. Pending changes ship first
as a final 0.x. Modules graduate in waves inside a `pico-bom` train; the core
(`pico-boot`, `pico-fastapi`, `pico-sqlalchemy`, `pico-pydantic`,
`pico-celery`, `pico-testing`) graduates together and that train is the
"pico 1.0" announcement. Peripheral modules may stay 0.x without stigma.

### 6. How downstream pins

- Generated projects (`pico-initializer`) and skills pin `~=0.X.Y` for 0.x
  modules (patches only) and `~=X.Y` for 1.x and later (minors flow, majors
  do not), because from 1.0 a minor is additive by this policy.
- Applications pin a `pico-bom` train with `-c`.

## Consequences

Positive:

- A user can read a version number and know what may have changed, and can
  read `__all__` and know what will not silently break.
- Deprecations are discoverable at runtime (`-W error::DeprecationWarning`
  in CI turns them into failures) and testable.
- Graduation is a checklist, not a feeling; `fleet-graduation.sh` prints it.

Negative:

- Additive-only minors after 1.0 make some cleanups expensive: a wrong
  default lives until the next major. The mitigation is to graduate late and
  to prefer new keys over changed defaults.
- Every removal takes two releases and a test. That is the cost of the
  promise.
- Eighteen independent majors would be a matrix; the train keeps it one file,
  and the core moving together keeps the matrix small.

## Alternatives rejected

- **Calendar versioning**: says when, not what. The train already carries
  the date; the package number must carry the promise.
- **Big-bang 1.0 of every module in one train**: ten modules are two months
  old and three had no usage outside their own tests until this week.
  Repeating the `pico-ioc` 1.0-then-2.0 sequence eighteen times is the
  realistic outcome.
- **No promises until every module is 1.0**: leaves `pico-pydantic` and
  `pico-celery`, unchanged since 2025-11, signalling instability they do not
  have.
- **Treating configuration as internal**: keys and defaults are what users
  write in YAML; a rename or a changed default breaks a deployment exactly
  like a renamed class.

## References

- `plan-1.0.md` (monorepo): waves, dates, per-module state.
- `fleet-scripts/fleet-graduation.sh`: criteria 1 to 4 as a table.
- ADR-013: an example of an additive change (new method, new event) that
  needed no deprecation.
- Semantic Versioning 2.0.0; PEP 440 compatible release (`~=`) semantics.
