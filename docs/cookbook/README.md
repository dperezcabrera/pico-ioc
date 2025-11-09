# Cookbook (Patterns) 🧑‍🍳

The Cookbook provides complete, end-to-end architectural patterns that show how pico-ioc’s features compose in real-world systems.

---

## 📖 Patterns Overview

| Pattern | Description | File |
|--------|-------------|------|
| **Multi-Tenant Applications** | Isolate tenants across configuration, scoped containers, and runtime boundaries. | [`pattern-multi-tenant.md`](pattern-multi-tenant.md) |
| **Hot Reload (Dev Server)** | Dev-time module replacement with deterministic container rebuilds and safe teardown. | [`pattern-hot-reload.md`](pattern-hot-reload.md) |
| **CLI Applications** | Command registration, DI per invocation, and structured output. | [`pattern-cli-app.md`](pattern-cli-app.md) |
| **CQRS Command Bus** | Segregated read/write models, command handlers, and middleware pipelines with AOP. | [`pattern-cqrs.md`](pattern-cqrs.md) |
| **Feature Toggles (AOP)** | Cross-cutting feature flags via decorators and runtime config. | [`pattern-aop-feature-toggle.md`](pattern-aop-feature-toggle.md) |
| **Structured Logging (AOP)** | Enforced log context, correlation IDs, and function-level structured logs. | [`pattern-aop-structured-logging.md`](pattern-aop-structured-logging.md) |
| **Security Checks (AOP)** | Permission/role gates, pre/post conditions, auditing hooks. | [`pattern-aop-security.md`](pattern-aop-security.md) |
| **Method Profiling (AOP)** | Execution timing and performance insights for critical call paths. | [`pattern-aop-profiling.md`](pattern-aop-profiling.md) |
| **Configuration Overrides** | Environment-driven overrides and deterministic container setup. | [`pattern-config-overrides.md`](pattern-config-overrides.md) |

---

## 🔧 How to Use

1. Pick a pattern that fits your scenario.
2. Copy the module layout and minimal container scaffolding.
3. Apply overrides / AOP / config depending on your environment.
4. Combine patterns:
   - The AOP patterns stack.
   - Overrides apply everywhere.
   - CQRS works well with profiling + structured logging.

---


## 🧩 Pattern Categories


**Application Architecture**
- [Multi-Tenant Applications](pattern-multi-tenant.md)
- [CQRS Command Bus](pattern-cqrs.md)

**Developer Experience**
- [Hot Reload](pattern-hot-reload.md)
- [Configuration Overrides & Deterministic Setup](pattern-config-overrides.md)

**Interfaces**
- [CLI Applications](pattern-cli-app.md)

**Cross-Cutting Concerns (AOP)**
- [Feature Toggles](pattern-aop-feature-toggle.md)
- [Structured Logging](pattern-aop-structured-logging.md)
- [Security Checks (@secured)](pattern-aop-security.md)
- [Method Profiling](pattern-aop-profiling.md)

**AI / LLM Integration**
- [Dynamic LangChain Model / Prompt Selection & Caching](pattern-aop-structured-logging.md)

---

## 🤝 Contributing

- Propose a new pattern or improvement by keeping:
  - Clear problem definition
  - Reproducible steps and code snippets
  - Dependency boundaries and lifecycle considerations
  - Testing and observability guidance
- Aim for composability: demonstrate how the pattern integrates with existing patterns when relevant.

