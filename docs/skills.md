# AI Coding Skills

[Claude Code](https://code.claude.com) and [OpenAI Codex](https://openai.com/index/introducing-codex/) skills for AI-assisted development with pico-ioc.

## Installation

```bash
curl -sL https://raw.githubusercontent.com/dperezcabrera/pico-skills/main/install.sh | bash -s -- ioc
```

Or install all pico-framework skills:

```bash
curl -sL https://raw.githubusercontent.com/dperezcabrera/pico-skills/main/install.sh | bash
```

### Platform-specific

```bash
# Claude Code only
curl -sL https://raw.githubusercontent.com/dperezcabrera/pico-skills/main/install.sh | bash -s -- --claude ioc

# OpenAI Codex only
curl -sL https://raw.githubusercontent.com/dperezcabrera/pico-skills/main/install.sh | bash -s -- --codex ioc
```

## Available Commands

### `/add-component`

Creates a new pico-ioc component with dependency injection. Use when you need to add services, factories, AOP interceptors, event subscribers, or `@configured` settings to a pico-framework project.

**Component types:** service (`@component`), factory (`@factory` + `@provides`), interceptor (`MethodInterceptor`), event subscriber (`@subscribe`), configured settings (`@configured`).

```
/add-component UserService
/add-component RedisFactory --type factory
/add-component LogInterceptor --type interceptor
/add-component AppSettings --type settings
```

### `/add-tests`

Generates tests for existing pico-framework components. Creates unit tests with mocks, integration tests with container setup, and proper assertions.

```
/add-tests UserService
/add-tests UserRepository --integration
```

## More Information

See [pico-skills](https://github.com/dperezcabrera/pico-skills) for the full list of skills, selective installation, and details.
