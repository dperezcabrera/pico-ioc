# FEATURE-2025-0006: Infrastructure Component (`@infrastructure`) + Around Interceptors

- **Date:** 2025-09-17  
- **Status:** Ready  
- **Priority:** high  
- **Related:** [FEATURE-2025-0003-interceptor-auto-registration]

---

## 1. Summary

Introduce a new `@infrastructure` annotation for **bootstrap-time configuration**.  
Infrastructure classes can **query** the discovered model and **mutate** it safely: add interceptors, wrap/replace providers, adjust tags/qualifiers, rename keys.  
At the same time, remove the legacy `@interceptor` API and replace it with clean **around-style interceptors** for methods and container lifecycle.

---

## 2. Goals

- Provide a single entrypoint for container customization.  
- Enable deterministic, precompiled interceptor chains.  
- Allow policy (where interceptors apply) to live in infrastructure, not in interceptor classes.  
- Support sync and async interceptors uniformly.

---

## 3. Non-Goals

- Runtime mutation after freeze.  
- Maintaining backward compatibility with the old `@interceptor` or `before/after/error` style.  

---

## 4. User Impact / Stories

- *As a developer*, I can add an HTTP logging interceptor only to classes tagged `http` in the `prod` profile.  
- *As a platform engineer*, I can enforce qualifiers (`db=primary`) across all `DbClient` providers.  
- *As a team*, we can replace or wrap providers without touching component code.  

---

## 5. Scope & Acceptance Criteria

- [ ] `@infrastructure` decorator discovered by scanner.  
- [ ] `Infra` façade exposes `query`, `intercept`, and `mutate`.  
- [ ] Selectors (`Select`) support filtering by module/class/method/tag/qualifier/profile.  
- [ ] MethodInterceptor API with `invoke(ctx, call_next)` works for sync/async.  
- [ ] ContainerInterceptor API with `around_resolve` and `around_create`.  
- [ ] Interceptors must be registered via infrastructure (`infra.intercept.add(..., where=...)`).  
- [ ] Legacy `@interceptor` annotation removed.  
- [ ] Bootstrap validation for empty selectors and interceptor caps.  

---

## 6. API / UX Contract

### Public API Example
```python
from pico_ioc import infrastructure
from pico_ioc.infra import Infra, Select, MethodInterceptor, ContainerInterceptor

@infrastructure(order=50)
class MetricsInfra:
    def configure(self, infra: Infra) -> None:
        sel = Select().has_tag("http").profile_in("prod")
        infra.intercept.add(
            interceptor=HttpMetrics(order=120),
            where=sel
        )
````

### Interceptor interfaces

```python
class MethodInterceptor(Protocol):
    order: int
    def invoke(self, ctx: MethodCtx, call_next: Callable[[MethodCtx], object]) -> object: ...

class ContainerInterceptor(Protocol):
    order: int
    def around_resolve(self, ctx: ResolveCtx, call_next): ...
    def around_create(self, ctx: CreateCtx, call_next): ...
```

### Compatibility Notes

* Old `@interceptor` removed.
* Interceptors must be reimplemented using `invoke` / `around_*`.

---

## 7. Rollout & Guardrails

* Feature enabled by default; no flags.
* Migration: rewrite interceptors to new `invoke/around_*` contracts, move policy to infra.
* Guardrails:

  * Interceptor must call `call_next` at most once.
  * Default cap of 16 interceptors per method.
  * Bootstrap error on empty `where`.

---

## 8. Telemetry

* Log number of infrastructures executed and matched selectors.
* Metrics:

  * `pico.infra.interceptors.count` (per method/key).
  * `pico.infra.rules.unmatched` (selectors matching zero targets).
* Traces for `around_resolve` / `around_create`.

---

## 9. Risks & Open Questions

* **Risk:** overly complex `Select` DSL.
  *Mitigation:* start minimal, extend as needed.
* **Open:** do we need removal operations in `InfraMutate` (e.g., remove tags)? Decision by v1.
* **Open:** expose `Select.explain()` for debugging index usage?

---

## 10. Test Strategy

* **Unit Tests**: every `Select` predicate and boolean composition.
* **Integration Tests**:

  * Method interceptors chain order, sync + async.
  * Container interceptors around resolve/create.
  * Mutations: wrap/replace/qualifiers/tags.
* **Negative Tests**: empty `where`, cap exceeded, duplicate replace.

---

## 11. Milestones

* **M1 Ready:** Spec written (2025-09-17).
* **M2 Planned:** Implementation in `interceptors.py` + `infra.py`, refactor builder.
* **M3 Shipped:** Released in v1.x with migration notes.

---

## 12. Documentation Impact

* Update `GUIDE.md`: remove `@interceptor`, add infra examples.
* Add new `GUIDE-INFRASTRUCTURE.md` with queries, mutations, and interception policy.
* Update `DECISIONS.md`: note removal of legacy interceptor.
* Release notes with migration examples.

---

## 13. Appendices (optional)

### Appendix A — Full API Stubs

```python
# --- Contexts for method interception ---
class MethodCtx:
    instance: object
    cls: type
    method: Callable
    name: str
    args: tuple
    kwargs: dict
    container: "PicoContainer"
    tags: set[str]
    qualifiers: dict[str, object]
    request_key: object
    local: dict[str, object]   # per-call scratchpad

class MethodInterceptor(Protocol):
    order: int
    def invoke(self, ctx: MethodCtx, call_next: Callable[[MethodCtx], object]) -> object: ...


# --- Contexts for container interception ---
class ResolveCtx:
    key: object
    qualifiers: dict[str, object]
    requested_by: object | None
    profiles: set[str]
    local: dict[str, object]

class CreateCtx:
    key: object
    component: type
    provider: Callable[[], object]  # raw factory
    profiles: set[str]
    local: dict[str, object]

class ContainerInterceptor(Protocol):
    order: int
    def around_resolve(self, ctx: ResolveCtx, call_next: Callable[[ResolveCtx], object]) -> object: ...
    def around_create(self,  ctx: CreateCtx,  call_next: Callable[[CreateCtx],  object]) -> object: ...


# --- Infrastructure façade ---
class Infra:
    @property
    def query(self) -> "InfraQuery": ...
    @property
    def intercept(self) -> "InfraIntercept": ...
    @property
    def mutate(self) -> "InfraMutate": ...

class InfraQuery:
    def components(self, where: "Select" = None, *, order_by=None, limit: int | None = None) -> list["ComponentModel"]: ...
    def providers(self, where: "Select" = None, *, order_by=None, limit: int | None = None) -> list["ProviderModel"]: ...
    def methods(self,    where: "Select" = None, *, order_by=None, limit: int | None = None) -> list["MethodModel"]: ...
    def interceptors(self, where: "Select" = None, *, order_by=None, limit: int | None = None) -> list["InterceptorBinding"]: ...
    def has_key(self, key: "Bind") -> bool: ...
    def get(self, key: "Bind") -> "ProviderModel | None": ...
    def count(self, where: "Select", *, domain: Literal["components","providers","methods","interceptors"]="providers") -> int: ...

class InfraIntercept:
    def add(self, *, interceptor: MethodInterceptor | ContainerInterceptor, where: "Select") -> None: ...
    def limit_per_method(self, max_n: int) -> None: ...

class InfraMutate:
    def add_tags(self, component: "ComponentModel", tags: list[str]) -> None: ...
    def set_qualifiers(self, provider: "ProviderModel", qualifiers: dict[str, object]) -> None: ...
    def replace_provider(self, *, key: "Bind", with_factory: Callable[[], object]) -> None: ...
    def wrap_provider(self,  *, key: "Bind", around: Callable[[Callable[[], object]], Callable[[], object]]) -> None: ...
    def rename_key(self,     *, old: "Bind",   new: "Bind") -> None: ...


# --- Selector DSL ---
class Select:
    def in_modules(self, *globs: str): ...
    def class_name(self, regex: str): ...
    def method_name(self, regex: str): ...
    def has_tag(self, *tags: str): ...
    def has_annotation(self, *names: str): ...
    def by_key_type(self, t: type): ...
    def by_key_name(self, name: str): ...
    def has_qualifier(self, key: str, value: object): ...
    def provided_type(self, t: type): ...
    def profile_in(self, *profiles: str): ...
    def lifecycle(self, kind: Literal["singleton","prototype"]): ...
    def interceptor_kind(self, kind: Literal["method","container"]): ...
    def interceptor_order_between(self, low: int, high: int): ...
    def was_replaced(self, flag: bool): ...
    def was_wrapped(self,  flag: bool): ...
    # boolean ops: & | ~

class Bind:
    @staticmethod
    def by_type(t: type) -> "Bind": ...
    @staticmethod
    def by_name(name: str) -> "Bind": ...
    @staticmethod
    def by_type_with_qualifiers(t: type, q: dict[str, object]) -> "Bind": ...
```

