# Cookbook (Patterns) 🧑‍🍳

The Cookbook provides complete, end-to-end architectural patterns—solutions to high-level design problems, showing how all of pico-ioc's features come together to build a robust, production-grade application.

Each pattern is self-contained and demonstrates composition, lifecycle management, AOP, configuration, and module boundaries in realistic scenarios.

---

## 📖 Table of Contents

- 1. Pattern: Multi-Tenant Applications
  - How to isolate tenants across configuration, scoped containers, and runtime boundaries.
  - File: ./pattern-multi-tenant.md
- 2. Pattern: Hot Reload (Dev Server)
  - Dev-time module replacement with deterministic container rebuilds and safe teardown.
  - File: ./pattern-hot-reload.md
- 3. Pattern: CLI Applications
  - Command registration, dependency injection per invocation, and structured command output.
  - File: ./pattern-cli-app.md
- 4. Pattern: CQRS Command Bus
  - Segregated read/write models, command handlers, and middleware pipelines with AOP.
  - File: ./pattern-cqrs.md
- 5. Pattern: Feature Toggles with AOP
  - Cross-cutting feature flags via decorators and runtime evaluation.
  - File: ./pattern-aop-feature-toggle.md
- 6. Pattern: Structured Logging with AOP
  - Enforced log context, correlation IDs, and method-level structured logs.
  - File: ./pattern-aop-structured-logging.md
- 7. Pattern: Security Checks with AOP (@secured)
  - Role/permission gates, pre/post-conditions, and audit hooks.
  - File: ./pattern-aop-security.md
- 8. Pattern: Method Profiling with AOP
  - Execution timing, thresholds, and performance insights for critical paths.
  - File: ./pattern-aop-profiling.md
- 9. Pattern: Configuration Overrides & Deterministic Setup
  - Environment-driven overrides, test-time overrides, and reproducible container builds.
  - File: ./pattern-config-overrides.md

---

## 🔧 How to Use This Cookbook

- Pick a pattern based on your use case. Each document includes:
  - Problem statement and context
  - Architecture diagram or outline
  - Step-by-step implementation with pico-ioc
  - Gotchas, trade-offs, and testing notes
- Start small: copy the minimal skeleton from the pattern and adapt to your modules and services.
- Combine patterns thoughtfully:
  - AOP patterns (5–8) can be layered on top of application-level patterns (1–4, 9–10).
  - Configuration Overrides (10) are useful across all patterns for environments and tests.

---

## 🧩 Pattern Categories

- Application Architecture
  - Multi-Tenant Applications (1)
  - CQRS Command Bus (4)
- Developer Experience
  - Hot Reload (2)
  - Configuration Overrides & Deterministic Setup (10)
- Interfaces
  - CLI Applications (3)
- Cross-Cutting Concerns (AOP)
  - Feature Toggles (5)
  - Structured Logging (6)
  - Security Checks (@secured) (7)
  - Method Profiling (8)
- AI/LLM Integration
  - Dynamic LangChain Model/Prompt Selection & Caching (9)

---

## 🤝 Contributing

- Propose a new pattern or improvement by keeping:
  - Clear problem definition
  - Reproducible steps and code snippets
  - Dependency boundaries and lifecycle considerations
  - Testing and observability guidance
- Aim for composability: demonstrate how the pattern integrates with existing patterns when relevant.

---
