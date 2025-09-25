# FEATURE-2025-0007: Infrastructure Binding + Policy Layer (with `@role` and Minimal `Select`)

* **Date:** 2025-09-18
* **Status:** Draft
* **Priority:** high
* **Related:** FEATURE-2025-0006 (Infrastructure + Around Interceptors), FEATURE-2025-0008 (Extended `Select` DSL), FEATURE-2025-0009 (Unified `@role`)

---

## 1) Summary

Elevate `@infra` classes (declared via `@role("infra")` or `@infra`) into a **policy layer** that runs at bootstrap and can:

* Register **interceptors** (which are just components), attached via a minimal **Select DSL**: `C` (components) + `M` (methods).
* Perform **binding operations** on the container model before freeze:

  * `bind.instance`, `bind.factory`, `bind.cls`
  * `bind.replace`, `bind.wrap`, `bind.alias`
* Apply **safe mutations** to provider/component metadata (tags/qualifiers/keys).

**Profiles only gate what is scanned/registered**; they are not part of selection predicates.

---

## 2) Goals

* Provide a single, deterministic **bootstrap policy** entrypoint.
* Support **IoC-first** design: interceptors, factories, infra, plugins are **components** and can be injected.
* Keep selection **minimal/clear** with `C` and `M` only; provider methods are recognized by `@provides`.
* Guarantee **determinism and auditability** (fingerprint of binds/mutations/interceptor plans).

---

## 3) Non-Goals

* Runtime mutation after freeze.
* Using profiles in the selection DSL.
* Reintroducing a provider selection domain (`K`) or `M.is_provider()`.

---

## 4) User Impact / Stories

* *As a developer*, I can **replace** a provider with a fake in `dev` without touching component code.
* *As a platform engineer*, I can **wrap** a provider with a timeout/retry policy via `infra`.
* *As a team*, we can **attach interceptors** to specific component methods via a clean DSL.

---

## 5) Scope & Acceptance Criteria

* [ ] Infra can register binds: **instance**, **factory**, **class**, **alias**, **replace**, **wrap**.
* [ ] Bind/replace guardrails: explicit `override=True`; `require_exists` default behavior documented.
* [ ] `Select` exposes **only** `from_components(C.*)` and optional `select_methods(M.*)` (default = public).
* [ ] Provider methods are matched via **`M.has_annotation("provides")`**.
* [ ] Interceptors are **components** and injectable into infra.
* [ ] All operations (binds/mutations/interceptors) are recorded in the **container fingerprint**.
* [ ] Profiles gate at scan; infra runs on the gated model.

---

## 6) Public API / UX Contract

### Decorators (from FEATURE-0009)

```python
from pico_ioc import role, provides
component = role("component")
factory   = role("factory")    # legacy "factory_component" accepted → normalized
infra     = role("infra")
plugin    = role("plugin")
```

### Infrastructure façade

```python
class Infra:
    @property
    def bind(self) -> "InfraBind": ...
    @property
    def intercept(self) -> "InfraIntercept": ...
    @property
    def mutate(self) -> "InfraMutate": ...
    @property
    def query(self) -> "InfraQuery": ...
    @property
    def context(self) -> "InfraContext": ...  # e.g., active_profiles (read-only)
```

#### Binding helpers

```python
class InfraBind:
    def instance(self, *, key, value, tags=(), qualifiers=(), override=False): ...
    def factory(self, *, key, fn, tags=(), qualifiers=(), override=False): ...
    def cls(self, *, key, cls, lazy=True, tags=(), qualifiers=(), override=False): ...
    def alias(self, *, src, dst): ...
    def replace(self, *, key, with_, override=True, require_exists=True): ...
    def wrap(self, *, key, around): ...
```

#### Interception

```python
class InfraIntercept:
    def add(self, *, interceptor, where: "Select") -> None: ...
    def limit_per_method(self, max_n: int) -> None: ...
```

> **Interceptors are components** (annotated with `@component` / `@role("component")`), DI-injected into infra.

#### Mutation

```python
class InfraMutate:
    def add_tags(self, component, tags: set[str]): ...
    def set_qualifiers(self, provider_or_component, qualifiers): ...
    def rename_key(self, *, old, new): ...
```

#### Query (read-only model access)

```python
class InfraQuery:
    def components(self, where: "Select" = None, *, limit=None) -> list: ...
    def methods(self, where: "Select" = None, *, limit=None) -> list: ...
    def providers(self, where: "Select" = None, *, limit=None) -> list: ...  # methods annotated with @provides
    def has_key(self, key) -> bool: ...
    def get(self, key): ...  # provider model for key (if any)
```

### Select DSL (minimal)

```python
from pico_ioc.infra import Select, C, M

Select()
  .from_components(C. … )       # required
  .select_methods(M. … )        # optional; default = public methods
# boolean ops for predicates: & | ~
```

**Component predicates `C`**
`has_tag`, `has_qualifier`, `is_subclass_of`, `name_in`, `name_glob`,
`has_annotation(name)`, `has_annotation_value(name, key, value)`,
`has_meta(key)`, `meta_equals(path, val)`, `meta_in(path, vals)`, `meta_matches(path, regex)`,
`attr_equals(attr, val)`, `where(fn)`.

**Method predicates `M`**
`name_matches`, `name_in`, `name_glob`, `is_public`,
`has_annotation("provides")`, `has_annotation_value("provides", "key", val)`,
`has_meta`, `meta_equals`, `meta_in`, `meta_matches`, `attr_equals`, `where`.

---

## 7) Examples

### A) Register and target interceptors (as DI components)

```python
@component
class HttpMetrics:
    def invoke(self, ctx, call_next): return call_next(ctx)

@infra
class MetricsInfra:
    def __init__(self, http_metrics: HttpMetrics):
        self.http_metrics = http_metrics

    def configure(self, infra):
        sel = Select().from_components(C.has_tag("service"))
        infra.intercept.add(interceptor=self.http_metrics, where=sel)
```

### B) Time only **provider executions** across factories

```python
@component
class FactoryTimer:
    def invoke(self, ctx, call_next): return call_next(ctx)

@infra
class ProviderTimingInfra:
    def __init__(self, timer: FactoryTimer):
        self.timer = timer

    def configure(self, infra):
        sel = (
            Select()
            .from_components(C.has_annotation("factory"))
            .select_methods(M.has_annotation("provides"))
        )
        infra.intercept.add(interceptor=self.timer, where=sel)
```

### C) Binding: add, replace, alias, wrap

```python
@infra
class WiringInfra:
    def configure(self, infra):
        # Add ad-hoc instance
        infra.bind.instance(key="now", value=lambda: datetime.utcnow())

        # Replace existing provider (explicit override)
        infra.bind.replace(key="db", with_=FakeDb(), override=True)

        # Alias legacy name to new key
        infra.bind.alias(src="legacy_db", dst="db")

        # Wrap provider creation with a policy (timeouts/retries)
        infra.bind.wrap(key="http_client", around=lambda factory: lambda: with_retry(factory))
```

### D) Produced beans as components

```python
@factory
class RepoFactory:
    @provides("order_repo", tags={"sql"}, qualifiers={"rw"})
    def provide_repo(self): ...

@component
class RepoRuntimeChecks:
    def invoke(self, ctx, call_next): return call_next(ctx)

@infra
class RepoInfra:
    def __init__(self, checks: RepoRuntimeChecks):
        self.checks = checks

    def configure(self, infra):
        # Target produced beans by merged metadata
        sel = Select().from_components(C.has_tag("sql") & C.has_qualifier("rw"))
        infra.intercept.add(interceptor=self.checks, where=sel)
```

---

## 8) Guardrails & Determinism

* **Phase**: all binds/mutations/interceptors must occur in `infra.configure()` **before freeze**.
* **Overrides**: require `override=True`; replacing non-existing providers requires `require_exists=False` or fails.
* **Chain limit**: cap (e.g., 16) interceptors per method; bootstrap error if exceeded.
* **Ordering**: chains ordered by `(infra.order, interceptor.order, stable_tiebreaker)`.
* **Fingerprint**: include binds, aliases, wraps, replaces, and final interception plan.

---

## 9) Profiles

* Evaluated **during scan** to include/exclude components/providers.
* Infra runs on the **already gated** model.
* The DSL **never** uses profiles.

---

## 10) Test Strategy

**Unit**

* Each bind helper (`instance`, `factory`, `cls`, `alias`, `replace`, `wrap`) with edge cases.
* Predicate composition for `C`/`M`.
* Annotation-value lookups (including provider metadata).

**Integration**

* Deterministic plan with multiple infra classes and interceptors.
* Replacement/aliasing effects visible via `query` and at resolution time.
* Produced beans inherit/merge metadata and match `C` predicates.

**Negative**

* Replace without `override=True`.
* Conflicting binds for same key.
* Exceeding interceptor cap.
* Attempting to mutate post-freeze.

---

## 11) Migration

* If you used a provider-specific selection domain previously, replace it with `M.has_annotation("provides")`.
* Move ad-hoc wiring from app code into **infra** using `bind.*`.
* Ensure interceptors are **declared as components** and **DI-injected** into infra.

---

## 12) Documentation Impact

* Update `GUIDE-INFRASTRUCTURE.md`: Binding, Mutation, Interception with `Select` (C/M).
* Update `GUIDE.md`: Using `@role` aliases and provider methods with `@provides`.
* Update `DECISIONS.md`: profiles = gating; no provider domain; interceptors as DI components.

---

## 13) Open Questions

* Do we expose `bind.scope(...)` for non-singleton lifecycles now or later?
* Should `wrap` be chainable (multiple wraps) with an explicit order?
* Provide `infra.query.providers(where=Select(...).select_methods(M.has_annotation("provides")))` sugar, or keep `methods(...)`?

---

**TL;DR**: Infra is your **policy engine** at bootstrap: it binds, mutates, and attaches interceptors using a minimal, annotation-first DSL. Interceptors are components; providers are just annotated methods; beans are components; profiles only gate the scan. Deterministic, auditable, clean.

