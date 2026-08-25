# Hermes Profile Builder

`profile-builder` is a standalone Hermes plugin for creating narrow profiles
through a **reviewed, explicit** workflow: scoping → design → interview →
implementation → validation, with rollback evidence at every apply step.

It orchestrates the native Hermes CLIs (`hermes profile`, `hermes config`,
`hermes plugins`, `hermes skills`, `hermes skin`, `hermes memory`,
`hermes gateway`) — it does not reimplement profile creation.

## Phases

| Phase | What happens | Gate |
|---|---|---|
| 0. Scoping | Purpose, domain, what it must NOT do | Scope approved |
| 1. Design | Scope → concrete manifest (model, toolsets, guardrails, plugins, platforms, skills, skin, memory, SOUL.md outline) | Design reviewed |
| 2. Interview | Per-item proposal → explicit confirm. Nothing applied silently | All items confirmed |
| 3. Implementation | Execute manifest via native CLIs. Snapshot first (rollback evidence) | Steps complete |
| 4. Validation | Boot check, model, plugins, skills, skin, memory, SOUL sync. Smoke test | Report passes |

## Usage

```
/profile-build new <name>            # start a build (phase 0)
/profile-build status [<name>]       # current phase + confirmed items
/profile-build propose <name>        # emit next phase's proposals
/profile-build confirm <name>        # confirm pending proposals
/profile-build apply <name>          # run implementation (phase 3)
/profile-build validate <name>       # run validation (phase 4)
/profile-build rollback <name>       # restore last snapshot
/profile-build list                  # all builds + phases
```

## Requirements

- Python 3.11 or newer
- A local Hermes Agent checkout (the plugin shells out to `hermes`)

## Local verification

```sh
HERMES_CORE=/path/to/hermes-agent mise run ci
```

`mise run ci` performs the locked setup, format check, lint, type check,
focused and full tests, plugin contract checks, and security checks.

## Installation contract

Hermes directory installs load `plugin.yaml` and the repository-root
`__init__.py`. Python package installs use the `profile_builder` entry point
in `pyproject.toml`. Both surfaces expose the same `register(ctx)` function.

The plugin doesn't override built-in Hermes tools.
