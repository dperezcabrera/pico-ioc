# Contributing to pico-ioc

## Development Setup

```bash
git clone https://github.com/dperezcabrera/pico-ioc.git
cd pico-ioc
python -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"
```

## Running Tests

```bash
pytest tests/ -v                                          # Quick run
pytest --cov=pico_ioc --cov-report=term-missing tests/    # With coverage
tox                                                       # Full matrix (3.11-3.14)
```

## Linting

```bash
pip install ruff
ruff check src/ tests/
ruff format --check src/ tests/
```

## Making Changes

1. Create a branch from `main`
2. Make your changes
3. Ensure all tests pass and linting is clean
4. Commit with a **single-line commit message**
5. Open a Pull Request against `main`

## Code Style

- Python 3.11+ with `X | Y` union syntax
- Follow existing patterns in the codebase
- See `AGENTS.md` for detailed conventions

## What NOT to Do

- Do not modify `_version.py` (auto-generated)
- Do not add runtime dependencies (zero-dependency is a core promise)
- Do not change `version_scheme` in `pyproject.toml`
