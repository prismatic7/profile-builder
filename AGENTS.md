# Profile Builder plugin

## Scope
- This repository owns the `profile-builder` Hermes plugin: reviewed, explicit
  profile creation with scoping, design, interview, implementation, and
  validation phases.
- The plugin orchestrates **native Hermes CLIs** (`hermes profile`, `hermes
  config`, `hermes plugins`, `hermes skills`, `hermes skin`, `hermes memory`,
  `hermes gateway`). It does NOT reimplement profile creation.
- Profile runtime behaviour (execution reviews, routines, delivery state)
  belongs in a separate plugin, not here.

## Development
- Support Python 3.11 and newer.
- Write a failing test before implementation changes.
- Keep production source files under 200 lines and functions under 30 lines.
- Keep dependencies declared in `pyproject.toml` and locked in `uv.lock`.
- Run `mise run ci` before treating a change as ready.

## Hermes contract
- The repository root is a directory-installable Hermes plugin.
- `plugin.yaml` and root `__init__.py` are required by the current Hermes
  plugin loader.
- The Python distribution entry point is `profile_builder` under
  `hermes_agent.plugins`.
- Never override a built-in Hermes tool.
- Use explicit profile selectors and fail closed on ambiguous profile state.

## Safety
- Don't read, log, persist, or commit secrets.
- Store only redacted discovery records.
- Keep protected-path mutations behind reviewed, expiring confirmation
  records.
- Preserve rollback evidence for every approved apply action.
- Profile deletion, `.env` writes, and mass config edits require explicit
  user confirmation.

## Git
- GitHub owner: `prismatic7` (personal code tooling — NOT research tooling;
  do not apply research framing to this repo).
- Don't add AI co-author credit or generated commit trailers.
- Commit, push, and remote changes only in an explicitly approved plan task.
