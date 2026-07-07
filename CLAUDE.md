Read and follow ./AGENTS.md for project conventions.

## Pico Ecosystem Context

pico-ioc is the **foundation** of the pico ecosystem. The full catalog of
modules, companions, and composition rules lives in AGENTS.md ("Pico
Ecosystem") — read it there; do not duplicate it here.

## Key Reminders

- **Commit messages: ONE LINE ONLY.** No body, no footer, no `Co-Authored-By` block. If you wrote multiple lines, amend before the user has to ask.
- Internal attributes are `_pico_meta`, `_pico_infra`, `_pico_name`, `_pico_key` (not dunder)
- **NEVER change `version_scheme`** in pyproject.toml. It MUST remain `"post-release"`. Changing it to `"guess-next-dev"` causes `.dev0` versions to leak to PyPI. This was already fixed once — do not revert it.
- requires-python >= 3.11 (no 3.10)
