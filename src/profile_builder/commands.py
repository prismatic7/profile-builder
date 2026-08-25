"""Command and tool handlers for profile-builder.

Exposes:
  /profile-build <subcommand> [name]   — interactive build workflow
  profile_build                        — tool: run a build subcommand
  profile_build_status                 — tool: show build status
  profile_build_apply                 — tool: apply confirmed manifest
  profile_build_validate              — tool: run validation
  profile_build_rollback             — tool: restore last snapshot

All handlers return JSON strings (tool contract) or plain text (command).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

from .apply import apply_manifest
from .rollback import rollback
from .state import Build, BuildError, BuildStore
from .validate import summarize, validate

PLUGIN_NAME = "profile-builder"


def _data_dir() -> Path:
    base = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))
    return base / "plugins" / PLUGIN_NAME


def _store() -> BuildStore:
    return BuildStore(_data_dir())


def _ok(payload: Dict[str, Any]) -> str:
    return json.dumps({"success": True, **payload})


def _err(message: str) -> str:
    return json.dumps({"success": False, "error": message})


def _build_summary(b: Build) -> Dict[str, Any]:
    return {
        "name": b.name,
        "phase": b.phase,
        "scope": b.scope[:200],
        "design": b.design[:200],
        "confirmed": b.confirmed,
        "approvals": len(b.approvals),
        "snapshots": len(b.snapshots),
    }


def _manifest_items(build: Build) -> List[str]:
    """Every confirmable item: profile creation + each manifest key.

    Dedupe: the manifest may itself contain a `create` key, which would
    otherwise list the item twice.
    """
    seen: List[str] = []
    for it in ["create", *build.manifest.keys()]:
        if it not in seen:
            seen.append(it)
    return seen


def _unconfirmed_items(build: Build) -> List[str]:
    return [it for it in _manifest_items(build) if it not in build.confirmed]


def _item_detail(build: Build, item: str) -> str:
    """One-line description of what confirming *item* will apply."""
    spec = build.manifest.get(item)
    if item == "create":
        return f"create profile {build.name}"
    if item == "config":
        return "; ".join(f"{kv['key']}={kv['value']}" for kv in spec)
    if item in ("plugins", "skills"):
        return ", ".join(str(x) for x in spec)
    if item == "skin":
        return f"use skin {spec}"
    if item == "memory":
        return f"memory provider {spec}"
    if item == "soul":
        return "write SOUL.md + sync system_prompt"
    if item == "gateway":
        return f"gateway platform {spec}"
    if item == "env":
        # Never log secret values — show keys only.
        return "; ".join(f"{kv['key']}=***" for kv in spec)
    if item == "mcp":
        return "; ".join(f"{s['name']} ({s['command']})" for s in spec)
    if item == "link":
        return "; ".join(f"{l['source']} -> {l['target']}" for l in spec)
    return str(spec)[:100]


# ---------------------------------------------------------------------------
# Subcommand implementations
# ---------------------------------------------------------------------------


def cmd_new(args: List[str]) -> str:
    if not args:
        return _err("usage: /profile-build new <name> [description]")
    name = args[0]
    store = _store()
    try:
        build = store.create(name)
        if len(args) > 1:
            build.scope = " ".join(args[1:])
            store.save(build)
        return _ok(
            {
                "message": f"build {name!r} started (phase: scoping)",
                "build": _build_summary(build),
            }
        )
    except BuildError as exc:
        return _err(str(exc))


def cmd_status(args: List[str]) -> str:
    store = _store()
    if not args:
        builds = store.list()
        if not builds:
            return _ok({"message": "no builds yet — /profile-build new <name>", "builds": []})
        return _ok({"builds": [_build_summary(b) for b in builds]})
    try:
        build = store.load(args[0])
        return _ok({"build": _build_summary(build)})
    except BuildError as exc:
        return _err(str(exc))


def cmd_propose(args: List[str]) -> str:
    if not args:
        return _err("usage: /profile-build propose <name>")
    store = _store()
    try:
        build = store.load(args[0])
    except BuildError as exc:
        return _err(str(exc))
    phase = build.phase
    if phase == "scoping":
        return _ok(
            {
                "phase": "scoping",
                "proposal": (
                    "Define the scope: purpose, domain, what it must NOT do. "
                    "Set it with /profile-build scope <name> <text>, then "
                    "/profile-build confirm <name> to approve."
                ),
            }
        )
    if phase == "design":
        return _ok(
            {
                "phase": "design",
                "proposal": (
                    "Map scope to a manifest: model/provider, toolsets, guardrails, "
                    "plugins, platforms, skills, skin, memory, SOUL.md outline. "
                    "Set it with /profile-build design <name> <json>, then confirm."
                ),
            }
        )
    if phase == "interview":
        # Real interview: present each unconfirmed item with its detail.
        items = _unconfirmed_items(build)
        if not items:
            return _ok(
                {
                    "phase": "interview",
                    "proposal": (
                        "All manifest items are confirmed. Run "
                        "/profile-build apply <name> to implement."
                    ),
                    "items": [],
                }
            )
        return _ok(
            {
                "phase": "interview",
                "proposal": (
                    "Review each manifest item. Confirm individually with "
                    "/profile-build confirm <name> <item> — nothing is applied "
                    "silently. Unconfirmed items: "
                    + ", ".join(items)
                ),
                "items": [
                    {
                        "item": it,
                        "detail": _item_detail(build, it),
                        "confirmed": it in build.confirmed,
                    }
                    for it in _manifest_items(build)
                ],
            }
        )
    if phase == "implementation":
        return _ok(
            {
                "phase": "implementation",
                "proposal": "Run /profile-build apply <name> to execute the confirmed manifest.",
            }
        )
    if phase == "validation":
        return _ok(
            {
                "phase": "validation",
                "proposal": "Run /profile-build validate <name> to verify the built profile.",
            }
        )
    return _err(f"unknown phase {phase!r}")


def cmd_scope(args: List[str]) -> str:
    if len(args) < 2:
        return _err("usage: /profile-build scope <name> <scope text>")
    store = _store()
    try:
        build = store.load(args[0])
        build.require_phase("scoping")
        build.scope = " ".join(args[1:])
        store.save(build)
        return _ok({"message": "scope set", "build": _build_summary(build)})
    except BuildError as exc:
        return _err(str(exc))


def cmd_design(args: List[str]) -> str:
    if len(args) < 2:
        return _err("usage: /profile-build design <name> <json manifest>")
    store = _store()
    try:
        build = store.load(args[0])
        build.require_phase("design")
        manifest = json.loads(" ".join(args[1:]))
        if not isinstance(manifest, dict):
            raise BuildError("manifest must be a JSON object")
        build.manifest = manifest
        store.save(build)
        return _ok({"message": "design set", "build": _build_summary(build)})
    except (BuildError, json.JSONDecodeError) as exc:
        return _err(str(exc))


def cmd_confirm(args: List[str]) -> str:
    if not args:
        return _err("usage: /profile-build confirm <name> [item]")
    store = _store()
    try:
        build = store.load(args[0])
    except BuildError as exc:
        return _err(str(exc))
    item = args[1] if len(args) > 1 else None
    if item:
        # Per-item confirmation is only valid during the interview phase.
        build.require_phase("interview")
        if item not in build.manifest and item != "create":
            return _err(f"item {item!r} not in manifest")
        build.add_approval(item, f"confirm {item}")
        if item not in build.confirmed:
            build.confirmed.append(item)
        store.save(build)
        return _ok({"message": f"confirmed {item}", "build": _build_summary(build)})
    # No item: advance one phase gate at a time. In the interview phase
    # there is NO bulk confirm — every manifest item must be confirmed
    # individually so nothing is applied silently.
    if build.phase == "scoping":
        build.advance("design")
        store.save(build)
        return _ok({"message": "scope approved — now design the manifest", "build": _build_summary(build)})
    if build.phase == "design":
        build.advance("interview")
        store.save(build)
        return _ok({"message": "design reviewed — now confirm each manifest item", "build": _build_summary(build)})
    if build.phase == "interview":
        missing = _unconfirmed_items(build)
        if missing:
            return _err(
                "interview not complete — confirm each item individually: "
                + ", ".join(missing)
                + " (e.g. /profile-build confirm <name> <item>)"
            )
        build.advance("implementation")
        store.save(build)
        return _ok({"message": "all items confirmed — ready to apply", "build": _build_summary(build)})
    return _err(f"nothing to confirm in phase {build.phase!r}")


def cmd_apply(args: List[str]) -> str:
    if not args:
        return _err("usage: /profile-build apply <name>")
    store = _store()
    try:
        build = store.load(args[0])
        results = apply_manifest(build, store, args[0])
        return _ok({"message": "implementation complete", "results": results, "build": _build_summary(build)})
    except BuildError as exc:
        return _err(str(exc))


def cmd_validate(args: List[str]) -> str:
    if not args:
        return _err("usage: /profile-build validate <name>")
    store = _store()
    try:
        build = store.load(args[0])
        checks = validate(build, args[0])
        return _ok({"report": summarize(checks), "checks": checks})
    except BuildError as exc:
        return _err(str(exc))


def cmd_rollback(args: List[str]) -> str:
    if not args:
        return _err("usage: /profile-build rollback <name>")
    store = _store()
    try:
        build = store.load(args[0])
        message = rollback(build, store, args[0])
        return _ok({"message": message, "build": _build_summary(build)})
    except BuildError as exc:
        return _err(str(exc))


def cmd_list(args: List[str]) -> str:
    store = _store()
    builds = store.list()
    if not builds:
        return _ok({"message": "no builds yet", "builds": []})
    return _ok({"builds": [_build_summary(b) for b in builds]})


SUBCOMMANDS: Dict[str, Any] = {
    "new": cmd_new,
    "status": cmd_status,
    "propose": cmd_propose,
    "scope": cmd_scope,
    "design": cmd_design,
    "confirm": cmd_confirm,
    "apply": cmd_apply,
    "validate": cmd_validate,
    "rollback": cmd_rollback,
    "list": cmd_list,
}


def handle_command(raw_args: str, **kwargs: Any) -> str:
    """/profile-build <subcommand> [args...]"""
    parts = raw_args.strip().split()
    if not parts:
        return (
            "Usage: /profile-build <new|status|propose|scope|design|confirm|"
            "apply|validate|rollback|list> [name] [args...]"
        )
    sub = parts[0]
    handler = SUBCOMMANDS.get(sub)
    if handler is None:
        return _err(f"unknown subcommand {sub!r}")
    try:
        return handler(parts[1:])
    except Exception as exc:  # never raise — tool contract
        return _err(f"{sub} failed: {exc}")


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------


def handle_tool_build(args: Dict[str, Any], **kwargs: Any) -> str:
    """Run a profile-build subcommand programmatically."""
    sub = str(args.get("subcommand", ""))
    name = str(args.get("name", ""))
    extra = args.get("args", "")
    parts = [sub, name] if name else [sub]
    if extra:
        parts.append(str(extra))
    return handle_command(" ".join(parts))


def handle_tool_status(args: Dict[str, Any], **kwargs: Any) -> str:
    """Show build status for one build or all builds."""
    name = str(args.get("name", ""))
    return cmd_status([name] if name else [])


def handle_tool_apply(args: Dict[str, Any], **kwargs: Any) -> str:
    """Apply a confirmed manifest for a build."""
    name = str(args.get("name", ""))
    if not name:
        return _err("name required")
    return cmd_apply([name])


def handle_tool_validate(args: Dict[str, Any], **kwargs: Any) -> str:
    """Run validation checks for a build."""
    name = str(args.get("name", ""))
    if not name:
        return _err("name required")
    return cmd_validate([name])


def handle_tool_rollback(args: Dict[str, Any], **kwargs: Any) -> str:
    """Restore the most recent snapshot for a build."""
    name = str(args.get("name", ""))
    if not name:
        return _err("name required")
    return cmd_rollback([name])
