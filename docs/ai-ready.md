# Built for the AI Era

Most frameworks were designed to be maintained and consumed by humans reading
tutorials. The pico ecosystem is additionally designed to be **read, extended
and maintained by AI coding assistants** — and ships the artifacts that make
that work in practice, not as marketing.

## What that means, concretely

**Every repo carries its own machine-readable playbook.** Each pico-* module
ships an `AGENTS.md` (project structure, commands, key concepts, code style,
boundaries) and a `CLAUDE.md` (ecosystem context and critical invariants).
An AI assistant — or a new human contributor — opens the repo already knowing
where things go, how to run the tests, and which lines must never change.

**Conventions are uniform across the ecosystem.** Same layout, same
`pyproject.toml` shape, same test and docs structure in every module, enforced
by a shared checklist. For an AI maintainer this is the difference between
reasoning once and reasoning fifteen times: a fix learned in one module
applies mechanically to the rest.

**Decisions are written down, with their rejected alternatives.**
The [ADRs](adr/README.md) record not just what was decided but what was
considered and why it lost — exactly the context an assistant needs to avoid
re-proposing a rejected design or breaking a deliberate trade-off.

**High branch coverage as a safety harness.** >95% coverage with eager
container validation means an AI-generated change that breaks a contract
fails fast and loudly — at test time or at `init()`, not in production.

## Tooling that closes the loop

- **[pico-skills](https://github.com/dperezcabrera/pico-skills)** — installable
  skills for [Claude Code](https://code.claude.com) and OpenAI Codex:
  `/add-component`, `/add-controller`, `/add-repository`, `/add-actuator`, and
  the `pico-conventions` background skill that teaches the assistant the whole
  ecosystem's API surface. One command:

  ```bash
  curl -sL https://raw.githubusercontent.com/dperezcabrera/pico-skills/main/install.sh | bash
  ```

- **[pico-initializer](https://dperezcabrera.github.io/pico-initializer/)** —
  scaffolds a ready-to-run project (web UI or CLI) that includes a tailored
  `CLAUDE.md` and an `install-skills.sh`, so a generated project is
  AI-maintainable from its first commit.

- **Zero-config plugins** — modules like
  [pico-actuator](https://github.com/dperezcabrera/pico-actuator) wire
  themselves through entry points and build from defaults when unconfigured.
  Less integration code means less code an assistant (or you) has to reason
  about to make a safe change.

## Why it matters

The scarce resource in AI-assisted development is not writing code — it is
**verification and context**. This ecosystem invests exactly there: contracts
validated eagerly at startup, invariants written where assistants read them,
uniform structure that makes review mechanical, and tests dense enough to
catch a wrong change before a human ever sees it.

If you maintain your projects with an AI assistant, a pico app is built to be
one of the easiest codebases it will ever work on.
