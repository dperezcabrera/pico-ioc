# FEATURE-2025-0009: Unified `@role` Decorator (component | factory | infra | plugin)

* **Date:** 2025-09-18
* **Status:** Draft
* **Priority:** high
* **Related:** FEATURE-2025-0006 (Infrastructure + Around Interceptors), FEATURE-2025-0008 (Extended `Select` DSL)

---

## 1) Summary

Introduce a single, minimal decorator `@role("<base>")` to declare the **base role** of any class that participates in the container:

* `component` — runtime components (including provider-produced beans)
* `factory` — factory classes that expose `@provides` methods
* `infra` — infrastructure classes executed at bootstrap to register policies (interceptors/binds, etc.)
* `plugin` — optional extension points discovered at scan time

This replaces multiple base-role decorators with one **uniform entrypoint**, while still exposing convenient aliases (`@component`, `@factory`, `@infra`, `@plugin`).
Providers remain method-level via `@provides(...)`. Produced beans are registered as **components** and participate uniformly in the **Select DSL** (`C.*` and `M.*`).
**Profiles are gating only** (scan-time inclusion/exclusion), never a selection filter.

---

## 2) Goals

* **Unify** role declaration with one decorator: `@role(...)`.
* Keep the DSL minimal: only `C` (components) and `M` (methods); identify providers via `M.has_annotation("provides")`.
* Ensure **deterministic metadata** (`__meta__`) for selection and tooling.
* Maintain **IoC/DI purity**: interceptors, factories, infra, plugins are all injectable components.

---

## 3) Non-Goals

* Changing provider semantics (`@provides` stays method-scoped).
* Runtime re-binding after freeze.
* Using profiles inside the DSL.

---

## 4) User Impact / Stories

* *As a developer*, I tag a class with `@role("factory")` and its `@provides` methods are discoverable without extra tags.
* *As a platform engineer*, I can intercept **provider methods** across all factories using `M.has_annotation("provides")`.
* *As a team*, I can define domain decorators (e.g., `@interceptor`) that internally call `@role("component")` and add metadata—no extra tags needed.

---

## 5) Scope & Acceptance Criteria

* [ ] Provide `role(base: Literal["component","factory","infra","plugin"|"factory_component"])`.
* [ ] Applying different base roles to the same class raises a **bootstrap error**.
* [ ] Expose aliases: `component = role("component")`, `factory = role("factory")`, `infra = role("infra")`, `plugin = role("plugin")`.
* [ ] Accept legacy `"factory_component"` and normalize to `"factory"` (optional warning).
* [ ] `@provides` annotates methods with `__meta__["provides"]` and `"provides"` in `annotations`.
* [ ] Produced beans are registered as **components** with merged metadata.
* [ ] `Select` operates with only `C` and `M`; providers targeted via `M.has_annotation("provides")`.
* [ ] Profiles gate registration before infra; DSL never depends on profiles.

---

## 6) Public API / UX

### Decorators

```python
from pico_ioc import role, provides

# Preferred aliases
component = role("component")
factory   = role("factory")
infra     = role("infra")
plugin    = role("plugin")
```

### Examples

```python
@component
class OrderService:
    def create_order(self, user, items): ...

@factory
class RepoFactory:
    @provides("order_repo", tags={"sql"}, qualifiers={"rw"})
    def provide_order_repo(self): ...

@infra
class MetricsInfra:
    def configure(self, infra): ...  # register interceptors/binds

@plugin
class OtelExporter: ...
```

### Select DSL usage (no provider domain, no profile filters)

```python
from pico_ioc.infra import Select, C, M

# Intercept all public methods on components tagged 'service'
Select().from_components(C.has_tag("service"))

# Time only provider executions on factories
Select().from_components(C.has_annotation("factory")).select_methods(M.has_annotation("provides"))

# Target produced beans (components) with SQL/RW metadata
Select().from_components(C.has_tag("sql") & C.has_qualifier("rw"))
```

---

## 7) Metadata Contract (`__meta__`)

* `__meta__["role"] = "component" | "factory" | "infra" | "plugin"`
* `__meta__["annotations"]` contains the base role string as an annotation token (e.g., `"factory"`, `"component"`).
* Optional: additional metadata (e.g., `order`, `capabilities`) can be attached by domain decorators that wrap `@role`.

**Merge policy for produced beans** (documented in core):

* `tags`: union of provider tags + bean tags
* `qualifiers`: union/merge (define set vs dict rules)
* `annotations`: union; always include `"component"`

---

## 8) Migration

* Replace `@component`, `@factory_component`, `@infrastructure`, `@plugin` with:

  * `@component`, `@factory`, `@infra`, `@plugin` (aliases) **or** `@role("<base>")`.
* Replace any provider-domain selectors with `M.has_annotation("provides")`.
* Ensure decorators populate `__meta__` consistently for `C/M.has_annotation*` to work.

---

## 9) Test Strategy

**Unit**

* `@role` sets/normalizes `__meta__["role"]` and updates `annotations`.
* Conflicting roles raise error.
* `"factory_component"` → normalized to `"factory"`.

**Integration**

* Factories scan correctly; provider methods have `"provides"` annotation metadata.
* Produced beans are selectable via `C.*`.
* DSL examples above match expected targets, default method predicate = public.

**Negative**

* Applying two different roles to one class.
* Missing `@role` on infra class referenced by builder → clear error.

---

## 10) Reference Stubs (illustrative)

```python
# core.py
_VALID = {"component","factory","infra","plugin","factory_component"}

def _ensure_meta(obj):
    m = getattr(obj, "__meta__", None)
    if m is None:
        m = {}
        setattr(obj, "__meta__", m)
    return m

def role(base: str):
    if base not in _VALID:
        raise ValueError(f"Unknown role: {base}")
    norm = "factory" if base == "factory_component" else base

    def deco(cls):
        meta = _ensure_meta(cls)
        existing = meta.get("role")
        if existing and existing != norm:
            raise ValueError(f"Conflicting roles on {cls.__name__}: {existing} vs {norm}")
        meta["role"] = norm
        anns = set(meta.get("annotations", set()))
        anns.add(norm)
        meta["annotations"] = anns
        return cls
    return deco

# Aliases
component = role("component")
factory   = role("factory")
infra     = role("infra")
plugin    = role("plugin")

def provides(key, *, tags=(), qualifiers=()):
    def deco(fn):
        meta = _ensure_meta(fn)
        meta["provides"] = {"key": key, "tags": set(tags), "qualifiers": set(qualifiers)}
        anns = set(meta.get("annotations", set()))
        anns.add("provides")
        meta["annotations"] = anns
        return fn
    return deco
```

---

## 11) Risks & Mitigations

* **Risk:** teams invent many domain decorators with conflicting metadata.
  **Mitigation:** enforce single base role; provide strict merge rules + lints.
* **Risk:** legacy `factory_component` confusion.
  **Mitigation:** normalize to `"factory"` and emit a one-time warning.

---

## 12) Documentation Impact

* Update `GUIDE.md` and `GUIDE-INFRASTRUCTURE.md` to use `@role` (plus aliases).
* Add a “Domain decorators” section showing how to compose custom decorators that wrap `@role` and add metadata.
* Clarify profiles = gating; selection = `C/M` + annotations/metadata.

---

**Decision on naming:** expose `@factory` to users (short and clear); accept `"factory_component"` as a legacy synonym internally normalized to `"factory"`.

