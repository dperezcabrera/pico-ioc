# Claude Code Skills

Pico-IoC includes pre-designed skills for [Claude Code](https://claude.ai/claude-code) that enable AI-assisted development following pico-framework patterns and best practices.

## Available Skills

| Skill | Command | Description |
|-------|---------|-------------|
| **Pico Component Creator** | `/pico-component` | Creates components with DI, scopes, factories and interceptors |
| **Pico Test Generator** | `/pico-tests` | Generates tests for pico-framework components |

---

## Pico Component Creator

Creates pico-ioc components with dependency injection, scopes, and factories.

### Patterns

#### Basic Component

```python
from pico_ioc import component

@component
class MyService:
    def __init__(self, dependency: SomeDependency):
        self.dep = dependency
```

#### With Scope

```python
@component(scope="singleton")  # singleton, prototype, request
class ConfigService:
    ...
```

#### Factory Provider

```python
from pico_ioc import factory, provides

@factory
class InfraFactory:
    @provides(Database, scope="singleton")
    def provide_db(self, config: Config) -> Database:
        return Database(config.db_url)
```

#### With Interceptors

```python
from pico_ioc import intercepted_by, MethodInterceptor

@component
class MyService:
    @intercepted_by(LoggingInterceptor)
    def critical_operation(self):
        ...
```

---

## Pico Test Generator

Generates tests for any pico-framework component.

### Test Structure

```python
import pytest
from unittest.mock import MagicMock, patch
from pico_ioc import PicoContainer

@pytest.fixture
def container():
    """Container with mocks for testing."""
    container = PicoContainer()
    return container

@pytest.fixture
def service(container):
    """Instance of the service under test."""
    return container.get(MyService)
```

### Component Tests

```python
class TestMyService:
    def test_get_returns_item(self, service):
        result = service.get(1)
        assert result.id == 1

    def test_get_raises_not_found(self, service):
        with pytest.raises(NotFoundError):
            service.get(999)
```

---

## Installation

```bash
# Project-level (recommended)
mkdir -p .claude/skills/pico-component
# Copy the skill YAML+Markdown to .claude/skills/pico-component/SKILL.md

mkdir -p .claude/skills/pico-tests
# Copy the skill YAML+Markdown to .claude/skills/pico-tests/SKILL.md

# Or user-level (available in all projects)
mkdir -p ~/.claude/skills/pico-component
mkdir -p ~/.claude/skills/pico-tests
```

## Usage

```bash
# Invoke directly in Claude Code
/pico-component UserService
/pico-tests UserService
```

See the full skill templates in the [pico-framework skill catalog](https://github.com/dperezcabrera/pico-ioc).
