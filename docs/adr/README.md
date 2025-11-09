# Architecture Decision Records (ADRs)

This index lists all significant architecture decisions for the `pico-ioc` project. Keep it sorted by ADR number.

ADR Index:
- ADR-001: Native Asyncio Support — Accepted — ./adr-0001-async-native.md
- ADR-002: Tree-Based Configuration — Accepted (Partially Superseded by ADR-010) — ./adr-0002-tree-based-configuration.md
- ADR-003: Context-Aware Scopes — Accepted — ./adr-0003-context-aware-scopes.md
- ADR-004: Observability Features — Accepted — ./adr-0004-observability.md
- ADR-005: Aspect-Oriented Programming (AOP) — Accepted — ./adr-0005-aop.md
- ADR-006: Eager Validation — Accepted — ./adr-0006-eager-validation.md
- ADR-007: Built-in Asynchronous Event Bus — Accepted — ./adr-0007-event_bus.md
- ADR-008: Explicit Handling of Circular Dependencies — Accepted — ./adr-0008-circular-dependencies.md
- ADR-009: Flexible @provides for Static and Module-level Functions — Accepted — ./adr-0009-flexible-provides.md
- ADR-010: Unified Configuration via @configured and ContextConfig — Accepted — ./adr-0010-unified-configuration.md

Status legend:
- Proposed: Under discussion, not yet binding.
- Accepted: Approved and implemented or scheduled for implementation.
- Superseded: Replaced by a newer ADR (referenced in both ADRs).
- Partially Superseded: Some aspects are replaced by a newer ADR.
- Deprecated: No longer recommended, kept for historical context.
- Rejected: Explicitly not adopted.

Contributing a new ADR:
- Use sequential numbering with 4 digits: adr-XXXX-slug.md (e.g., adr-0011-new-feature.md).
- Place the file in this directory: ws/docs/adr/.
- Keep the slug lowercase, words separated by hyphens.
- Start with status Proposed; update to Accepted after approval.
- If an ADR supersedes or deprecates another, clearly mark the relationship in both documents.
- Update this README index with the new ADR, keeping the list sorted by number.

Recommended ADR content (minimal):
- Title
- Status
- Date
- Context
- Decision
- Consequences
- References (optional)
