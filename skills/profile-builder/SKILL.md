---
name: profile-builder
version: 1.0.0
category: sysadmin
description: "Reviewed, explicit Hermes profile creation — scoping, design, interview, implementation, validation, rollback."
tags: [hermes, profile, config, workflow, safety]
---

# Profile Builder Workflow

Reviewed, explicit creation of narrow Hermes profiles. The plugin
(`/profile-build`) enforces the phase machine and approval records; this
skill is the workflow guidance for running a build well.

## When to Activate

- Chris wants a new Hermes profile (a new "room" in the rehearsal-room
  architecture)
- A profile needs significant reconfiguration (guardrails, plugins,
  platforms, skills, skin, memory, SOUL.md)
- Reviewing or validating an existing profile build

## The Five Phases

| Phase | What happens | Gate |
|---|---|---|
| 0. Scoping | Purpose, domain, what it must NOT do | Scope approved |
| 1. Design | Scope → concrete manifest | Design reviewed |
| 2. Interview | Per-item proposal → explicit confirm | All items confirmed |
| 3. Implementation | Execute manifest via native CLIs, snapshot first | Steps complete |
| 4. Validation | Boot check, model, plugins, skills, skin, memory, SOUL sync | Report passes |

## Workflow

### Phase 0: Scoping

**Steps:**
1. Ask: what is this profile FOR? (one sentence)
2. Ask: what domain does it live in? (research, sysadmin, teaching, creative…)
3. Ask: what must it NOT do? (write to other profiles, run destructive ops, etc.)
4. Record via `/profile-build scope <name> <text>`
5. Confirm: `/profile-build confirm <name>`

**Checks before moving on:**
- [ ] Scope is one or two sentences, not a paragraph
- [ ] The "must NOT do" list is explicit
- [ ] Name is lowercase alphanumeric with hyphens/underscores

### Phase 1: Design

**Steps:**
1. Map scope → manifest items. The manifest is a JSON object with any of:
   - `create`: `{"description": "..."}`
   - `config`: `[{"key": "model.default", "value": "..."}, ...]`
   - `plugins`: `["owner/repo", ...]`
   - `skills`: `["skill-name", ...]`
   - `skin`: `"skin-name"`
   - `memory`: `"provider-name"`
   - `soul`: `"full SOUL.md text"`
   - `gateway`: `"platform-name"`
   - `env`: `[{"key": "VAR", "value": "..."}]` (HIGH RISK)
   - `mcp`: `[{"name": "server", "command": "npx", "args": ["-y", "pkg", "path"]}, ...]`
   - `link`: `[{"source": "~/.hermes/plugins/unslop", "target": "unslop"}, ...]` (local plugins)
2. Record via `/profile-build design <name> '<json>'`
3. Review the design with Chris before confirming.

**Checks before moving on:**
- [ ] Every manifest item maps to a native Hermes CLI
- [ ] Model block is explicit (profiles don't inherit model config)
- [ ] No secrets in the manifest (env values go in .env, not the manifest)

### Phase 2: Interview

**Steps:**
1. Run `/profile-build propose <name>` — it lists every manifest item with
   its detail and which are still unconfirmed.
2. Walk through each item with Chris: what it does, why it's needed, what
   it costs (plugins = surface, skills = context, gateway = delivery).
3. Confirm EACH item individually: `/profile-build confirm <name> <item>`.
4. There is NO bulk confirm. `confirm <name>` with no item only advances
   phase gates (scoping → design → interview); in the interview phase it
   errors until every item is individually confirmed.
5. When all items are confirmed, `confirm <name>` advances to implementation.

**Checks before moving on:**
- [ ] Every manifest item has an explicit confirmation record
- [ ] `env` items show keys only (never values) in the interview
- [ ] Chris has seen the full item list via `propose`

### Phase 3: Implementation

**Steps:**
1. `/profile-build apply <name>`
2. The plugin snapshots the profile dir before each step, runs the native
   CLI scoped with `HERMES_PROFILE`, and logs before/after evidence.
3. If a step fails, roll back: `/profile-build rollback <name>`

**Checks before moving on:**
- [ ] All steps completed without error
- [ ] Snapshots exist for every applied step
- [ ] No secrets logged

### Phase 4: Validation

**Steps:**
1. `/profile-build validate <name>`
2. Review the report: profile dir, SOUL.md, config.yaml, model block,
   system_prompt sync, profile listed, plugins, skills, skin, memory, smoke test.
3. Fix failures (usually: missing model block, system_prompt not synced).

**Checks before moving on:**
- [ ] All checks pass (or failures are understood and fixed)
- [ ] Smoke test boots the profile

## Guardrails

- **Fail closed:** if profile state is ambiguous, stop and ask.
- **Approval records expire** (default 7 days). Re-confirm stale approvals.
- **Rollback evidence:** every apply step snapshots first. Never apply
  without a snapshot.
- **Never override built-in Hermes tools.**
- **No secrets in logs, manifests, or state files.** `.env` writes are
  HIGH RISK and always require a fresh confirmation.

## Anti-patterns

- ❌ Reimplementing `hermes profile create` — the plugin drives the CLI
- ❌ Applying without confirmation records
- ❌ Skipping the snapshot step
- ❌ Writing secrets into the manifest JSON
- ❌ Creating a profile without a model block (it won't boot)

## Integration

- `profile-config` skill — profile anatomy, SOUL.md authoring, system_prompt sync
- `hermes-plugins` skill — plugin authoring conventions this plugin follows
- `hermes profile` CLI — the native surface the plugin orchestrates
