# FEATURE-2025-0008: Extended `Select` DSL — Unified Components with `@role`

* **Date:** 2025-09-18
* **Status:** Draft
* **Priority:** high
* **Related:** FEATURE-2025-0006 (Infrastructure + Around Interceptors), FEATURE-2025-0007 (Infrastructure Binding), **FEATURE-2025-0009 (Unified `@role`)**

---

## 1) Summary

Extend the `Select` DSL so infrastructure can precisely target:

* **Components** (declared classes **and** beans produced by providers),
* **Methods** on those components (including **provider methods**).

The model is **unified**: *everything that participates is a component*, and its base role is declared with `@role("component" | "factory" | "infra" | "plugin")` (or the sugar `@component`, `@factory`, `@infra`, `@plugin`).
Provider methods are identified via the **annotation** `@provides(...)`; **no separate provider domain (`K`)** and **no `M.is_provider()`** are needed.

**Profiles are gating only** (scan-time inclusion/exclusion). The DSL never uses profiles as predicates.

---

## 2) Design Principles

1. **Unified graph**

   * Declared classes, factory classes, infrastructure, plugins, and provider-produced beans are all **components** (with base role via `@role`).
2. **Minimal DSL**

   * Two predicate namespaces only:

     * `C` → component predicates
     * `M` → method predicates
   * Provider methods are matched by `M.has_annotation("provides")`.
3. **Annotation-first**

   * Selection by **annotation presence and values** (including custom domain decorators that wrap `@role`).
4. **Determinism**

   * Selection resolved at bootstrap produces a stable, ordered plan.

---

## 3) Public UX / Client API

### Decorators (from FEATURE-2025-0009)

```python
from pico_ioc import role, provides

# sugar
component = role("component")
factory   = role("factory")       # "factory_component" accepted and normalized to "factory"
infra     = role("infra")
plugin    = role("plugin")
```

### Select DSL surface

```python
from pico_ioc.infra import Select, C, M

# Selector
Select()
  .from_components(C. … )       # required
  .select_methods(M. … )        # optional; default = public methods
# Boolean composition on predicates: & | ~
```

#### Component predicates `C`

* `C.has_tag(tag: str)`
* `C.has_qualifier(q: str)` *(or KV variant if supported)*
* `C.is_subclass_of(base: type)`
* `C.name_in(*names: str)` / `C.name_glob(*globs: str)`
* `C.has_annotation(name: str)`
  *(e.g., "component", "factory", "infra", "plugin", or a domain decorator name like "interceptor", "database\_provider")*
* `C.has_annotation_value(name: str, key: str, value: object)`
* `C.has_meta(key: str)` / `C.meta_equals(path: str, value)` / `C.meta_in(path, values)` / `C.meta_matches(path, regex)`
* `C.attr_equals(attr: str, value)` / `C.attr_where(fn)`
* `C.where(fn: Callable[[type], bool])` *(escape hatch)*

#### Method predicates `M`

* `M.name_matches(regex)` / `M.name_in(*names)` / `M.name_glob(*globs)`
* `M.is_public()` *(default if none specified)*
* `M.has_annotation("provides")`
* `M.has_annotation_value("provides", "key", <name|type>)` *(and other provider metadata fields)*
* `M.has_meta(key)` / `M.meta_equals(path, value)` / `M.meta_in(path, values)` / `M.meta_matches(path, regex)`
* `M.attr_equals(attr, value)` / `M.where(fn)`

---

## 4) Semantics

* **Produced beans are components**: after registration, beans participate in `C.*` exactly like declared components.
* **Providers are methods**: provider selection uses `M.has_annotation("provides")` and value predicates on its metadata.
* **Default methods**: if `.select_methods(...)` isn’t called, only **public methods** are targeted.
* **Single-domain rule**: a rule targets **component methods**; there is no special “providers domain”.

---

## 5) Code Examples

### A) Intercept all public methods of **service** components (declared + produced beans)

```python
@infra
class MetricsInfra:
    def configure(self, infra):
        sel = Select().from_components(C.has_tag("service"))
        infra.intercept.add(interceptor=self._http_metrics, where=sel)
```

### B) Time **provider execution** across all factories

```python
@infra
class ProviderTimingInfra:
    def __init__(self, timer):  # injected component
        self.timer = timer

    def configure(self, infra):
        sel = (
            Select()
            .from_components(C.has_annotation("factory"))
            .select_methods(M.has_annotation("provides"))
        )
        infra.intercept.add(interceptor=self.timer, where=sel)
```

### C) Target produced beans (components) with **SQL/RW** metadata

```python
@infra
class RepoRuntimeInfra:
    def __init__(self, checks):
        self.checks = checks

    def configure(self, infra):
        sel = Select().from_components(C.has_tag("sql") & C.has_qualifier("rw"))
        infra.intercept.add(interceptor=self.checks, where=sel)
```

### D) Filter by **base role** and **domain decorator**

```python
# domain decorator that wraps @role("component") and adds metadata
def interceptor(**meta):
    def wrap(cls):
        cls = component(cls)
        m = getattr(cls, "__meta__", {})
        m.setdefault("annotations", set()).add("interceptor")
        m.setdefault("capabilities", set()).add("method_interceptor")
        setattr(cls, "__meta__", m)
        return cls
    return wrap

@infra
class SecurityInfra:
    def configure(self, infra):
        # Any component annotated with @interceptor(...)
        sel = Select().from_components(C.has_annotation("interceptor"))
        infra.intercept.add(interceptor=self._authz, where=sel)
```

### E) Provider key/value matching via annotation metadata

```python
@infra
class KeyRulesInfra:
    def configure(self, infra):
        sel = (
            Select()
            .from_components(C.has_annotation("factory"))
            .select_methods(
                M.has_annotation("provides") &
                M.has_annotation_value("provides", "key", "order_repo")
            )
        )
        infra.intercept.add(interceptor=self._repo_policy, where=sel)
```

### F) Escape hatch with docstring and legacy tag

```python
@infra
class LegacyInfra:
    def configure(self, infra):
        comp_is_legacy = C.where(lambda c: "legacy" in getattr(c, "__meta__", {}).get("tags", set()))
        method_is_important = M.where(lambda m: "important" in (m.__doc__ or "").lower())
        sel = Select().from_components(comp_is_legacy).select_methods(method_is_important)
        infra.intercept.add(interceptor=self._legacy_guard, where=sel)
```

---

## 6) Metadata Contract (`__meta__`)

* Classes decorated with `@role("<base>")` have:

  * `__meta__["role"] = "component" | "factory" | "infra" | "plugin"`
  * `__meta__["annotations"]` includes the base role token (e.g., `"factory"`).
  * Optional: `tags`, `qualifiers`, `order`, `capabilities`, etc.
* Provider methods decorated with `@provides(...)` have:

  * `__meta__["annotations"]` includes `"provides"`
  * `__meta__["provides"] = {"key": <name|type>, "tags": set[str], "qualifiers": …}`

**Bean metadata merge** (core-defined and documented):

* `tags`: bean.tags |= provider.tags
* `qualifiers`: merged per your set/dict policy
* `annotations`: bean.annotations |= provider.annotations; ensure `"component"` present

---

## 7) Acceptance Criteria

* [ ] `Select` exposes `from_components(C.*)` and optional `select_methods(M.*)`; default methods = public.
* [ ] `C`/`M` include **annotation-aware** predicates (`has_annotation`, `has_annotation_value`) and generic `meta_*`.
* [ ] No `K` domain; no `M.is_provider()`; provider methods matched via `M.has_annotation("provides")`.
* [ ] Produced beans are selectable by `C.*`.
* [ ] Profiles gate scan only; DSL never references profiles.
* [ ] Rule planning is deterministic and precompiled.

---

## 8) Test Strategy

**Unit**

* Predicates: each `C.*` and `M.*` (including boolean composition).
* Annotation value access (both direct and dotted `meta_equals("provides.key", "order_repo")` if supported).

**Integration**

* Factories discovered via `@role("factory")`; provider methods carry `"provides"`.
* Beans produced inherit/merge metadata and match `C.has_tag` / `C.has_qualifier`.
* Interceptor registration with mixed rules (methods vs providers) yields expected targets.
* Default method selection excludes private names.

**Negative**

* Empty `from_components(...)` (error on bootstrap if rule would be a no-op, configurable).
* Mis-specified annotation keys / non-existing metadata paths.
* Conflicting base roles on the same class (handled in FEATURE-0009).

---

## 9) Risks & Mitigations

* **Risk:** Users expect a provider domain.
  **Mitigation:** Documentation and examples emphasizing `M.has_annotation("provides")`.

* **Risk:** Metadata conflicts on bean merge.
  **Mitigation:** Document strict merge policy; provide warnings or strict mode.

* **Risk:** Domain decorators with inconsistent metadata.
  **Mitigation:** Lints + bootstrap checks on reserved keys (`role`, `profiles`, etc.).

---

## 10) Documentation Impact

* Update `GUIDE-INFRASTRUCTURE.md`: sections “Select DSL”, “Annotations & Metadata”, “Provider methods via `@provides`”.
* Update `GUIDE.md`: unify around `@role` aliases; examples using only `C` and `M`.
* Update `DECISIONS.md`: “Profiles = gating; Selection = annotations/tags/qualifiers only”.

---

## 11) Reference Stubs (illustrative)

```python
# decorators
def role(base: str): ...
def provides(key, *, tags=(), qualifiers=()): ...

# DSL
class Select:
    def from_components(self, pred): ...
    def select_methods(self, pred): ...
class C:
    def has_tag(tag): ...
    def has_qualifier(q): ...
    def is_subclass_of(t): ...
    def name_in(*names): ...
    def name_glob(*globs): ...
    def has_annotation(name): ...
    def has_annotation_value(name, key, value): ...
    def has_meta(key): ...
    def meta_equals(path, value): ...
    def meta_in(path, values): ...
    def meta_matches(path, regex): ...
    def attr_equals(attr, value): ...
    def where(fn): ...
class M:
    def name_matches(regex): ...
    def name_in(*names): ...
    def name_glob(*globs): ...
    def is_public(): ...
    def has_annotation(name): ...
    def has_annotation_value(name, key, value): ...
    def has_meta(key): ...
    def meta_equals(path, value): ...
    def meta_in(path, values): ...
    def meta_matches(path, regex): ...
    def attr_equals(attr, value): ...
    def where(fn): ...
```

---

**TL;DR**
`Select` is now clean and powerful with just `C` and `M`, driven by annotations/metadata.
`@role` (and aliases) unify base roles; `@provides` marks provider methods.
Beans produced are components; profiles are gating only.

