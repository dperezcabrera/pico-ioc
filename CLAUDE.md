Read and follow ./AGENTS.md for project conventions.

## Pico Ecosystem Context

pico-ioc is the **foundation** of the pico-framework ecosystem. All other packages depend on it:

- pico-boot: orchestration & plugin discovery
- pico-fastapi: FastAPI integration
- pico-sqlalchemy: SQLAlchemy + transactions
- pico-celery: Celery task integration
- pico-pydantic: Pydantic validation AOP
- pico-agent: LLM agent framework

## Key Reminders

- Internal attributes are `_pico_meta`, `_pico_infra`, `_pico_name`, `_pico_key` (not dunder)
- `version_scheme = "post-release"` in pyproject.toml
- requires-python >= 3.11 (no 3.10)
- Commit messages: one line only
