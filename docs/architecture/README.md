# Architecture

Welcome to the Architecture section.

This section focuses on the "Why" and the "How" of pico-ioc—intended for contributors and architects who need a deep understanding of the framework's core mechanics and design philosophy.

## Audience and Goals

- Who should read this: contributors, maintainers, and architects working on pico-ioc.
- Goals:
  - Explain the rationale behind key design decisions.
  - Document internal components and their interactions.
  - Provide a consistent reference for future changes via ADRs (Architecture Decision Records).

## Scope and Non-goals

- In scope:
  - Design principles and trade-offs.
  - Internal architecture and lifecycle.
  - Comparison with related libraries to clarify positioning.
  - Decision records that capture significant architectural changes.
- Out of scope:
  - End-user tutorials and API guides (see user- or developer-facing documentation elsewhere in the repository).
  - Project management processes not directly impacting architecture.

## Table of Contents

- 1. Design Principles (The "Why"): ./design-principles.md
- 2. Comparison to Other Libraries: ./comparison.md
- 3. Internals Deep-Dive (The "How"): ./internals.md
- 4. Architecture Decision Records (ADR Index): ./adr/README.md

## Conventions Used in This Section

- Terminology:
  - "Architecture" refers to core components, their responsibilities, and interactions.
  - "Internals" refers to non-public mechanisms subject to change.
  - "ADR" documents authoritative decisions and their context.
- Diagrams and examples are illustrative; consult source code to confirm exact behavior.
- Paths in links are relative to this directory.

## Stability and Change Management

- Internal details may evolve; prefer ADRs for context and rationale behind changes.
- Public-facing APIs should be documented separately and may have different stability guarantees than internals.
- When proposing changes affecting architecture:
  - Open an ADR (see ./adr/README.md for workflow).
  - Reference impacted sections in design-principles.md and internals.md.

## How to Use This Section

- Start with design-principles.md to understand motivations and constraints.
- Use comparison.md to position pico-ioc among similar solutions.
- Consult internals.md for deep technical details and implementation notes.
- Review adr/README.md to trace decisions over time and understand historical context.

## Feedback and Contributions

- If you find inconsistencies or gaps:
  - Propose edits via pull request.
  - Link changes to relevant ADRs where applicable.
- Keep examples and references accurate:
  - Update function/class names and file paths when refactoring.
  - Ensure cross-links remain valid after structural changes.
