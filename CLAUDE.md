Read and follow ./AGENTS.md for project conventions.

## Pico Ecosystem

pico-ioc is the foundation. Every module below builds on it, is installed with
`pip install <name>`, and — in a pico-boot app — activates by just being
installed (auto-discovery via the `pico_boot.modules` entry point; no code
changes). Without pico-boot, list the module in `init(modules=[...])`.

### Runtime modules

| Package | Use it for | Key API |
|---------|-----------|---------|
| pico-boot | App bootstrap + plugin auto-discovery | `pico_boot.init()`, `PICO_BOOT_AUTO_PLUGINS` |
| pico-fastapi | HTTP controllers on FastAPI | `@controller`, `@get`, `@post`; `container.get(FastAPI)` |
| pico-sqlalchemy | Persistence + transactions | `@repository`, `@query`, `@transactional`, `AppBase` |
| pico-celery | Distributed tasks | `@celery`, `@task`, `@send_task` |
| pico-pydantic | Argument validation AOP | `@validate` |
| pico-resilience | Retry / circuit breaker / timeout AOP | `@retryable`, `@circuit_breaker`, `@timeout` |
| pico-caching | Method result caching | `@cacheable`, `CacheBackend` |
| pico-actuator | Health/info/metrics/refresh endpoints | `HealthIndicator`, `InfoContributor`; config prefix `actuator` |
| pico-otel | OpenTelemetry traces + metrics | `OtelSettings`; config prefix `otel` |
| pico-client-auth | JWT validation + RBAC | `@requires_role`, `@requires_scope`, `@allow_anonymous` |
| pico-server-auth | Embeddable auth server (JWT, wallet login, JWKS) | config prefix `server_auth` |
| pico-agent | LLM agents and tools | `@agent`, `@tool` |

### Tooling and companions

- **pico-initializer** — scaffolds projects/modules (web UI + `node cli.js`); the source of truth for a correct app skeleton.
- **pico-skills** — installable AI coding skills: `curl -sL https://raw.githubusercontent.com/dperezcabrera/pico-skills/main/install.sh | bash`
- **pico-learn** — interactive browser lessons (pyodide): https://dperezcabrera.github.io/pico-learn/
- **pico-auth** — standalone deployable auth server application (not a module; embed pico-server-auth instead if you need auth inside your app).

### Composition rules that matter when using them

- AOP decorators combine on one method; `@retryable` goes on top.
- Interceptors' `invoke` is sync unless truly async (an async `invoke` breaks sync methods).
- pico-actuator and pico-otel meet at the `prometheus_client` default registry: `/actuator/metrics` serves what pico-otel writes.
- pico-client-auth validates tokens that pico-server-auth issues (match `auth_client.issuer` with `server_auth.issuer`).
- Config hot reload: `container.refresh_config()` re-reads tree sources and publishes `ConfigChanged` (pico-ioc >= 2.3.0); `POST /actuator/refresh` triggers it over HTTP.
- Apps use the factory pattern and import-safe `main.py`: `uvicorn --factory pkg.main:create_app`.

## Key Reminders

- **Commit messages: ONE LINE ONLY.** No body, no footer, no `Co-Authored-By` block. If you wrote multiple lines, amend before the user has to ask.
- Internal attributes are `_pico_meta`, `_pico_infra`, `_pico_name`, `_pico_key` (not dunder)
- **NEVER change `version_scheme`** in pyproject.toml. It MUST remain `"post-release"`. Changing it to `"guess-next-dev"` causes `.dev0` versions to leak to PyPI. This was already fixed once — do not revert it.
- requires-python >= 3.11 (no 3.10)
