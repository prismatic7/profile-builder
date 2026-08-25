"""Hermes profile-builder plugin package.

Registers the /profile-build command and profile_build_* tools with the
Hermes agent. The plugin orchestrates native Hermes CLIs — it never
reimplements profile creation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .commands import (
    handle_command,
    handle_tool_apply,
    handle_tool_build,
    handle_tool_rollback,
    handle_tool_status,
    handle_tool_validate,
)

__all__ = ["register"]


def register(ctx: Any) -> None:
    """Register the builder surface with the Hermes agent."""
    # Bundled workflow skill (namespaced as profile-builder:profile-builder).
    skills_dir = Path(__file__).resolve().parent.parent.parent / "skills"
    skill_md = skills_dir / "profile-builder" / "SKILL.md"
    if skill_md.exists():
        try:
            ctx.register_skill("profile-builder", skill_md)
        except Exception:
            # Skill registration is best-effort; the command/tools are the
            # primary surface.
            pass

    ctx.register_command(
        "profile-build",
        handler=handle_command,
        description=(
            "Reviewed profile creation: new|status|propose|scope|design|"
            "confirm|apply|validate|rollback|list"
        ),
        args_hint="new|status|propose|scope|design|confirm|apply|validate|rollback|list",
    )

    ctx.register_tool(
        name="profile_build",
        toolset="profile-builder",
        schema={
            "type": "object",
            "parameters": {
                "type": "object",
                "properties": {
                    "subcommand": {
                        "type": "string",
                        "description": "new|status|propose|scope|design|confirm|apply|validate|rollback|list",
                    },
                    "name": {"type": "string", "description": "Build/profile name"},
                    "args": {"type": "string", "description": "Extra arguments (scope text, JSON manifest)"},
                },
                "required": ["subcommand"],
            },
        },
        handler=handle_tool_build,
        description="Run a profile-build subcommand (reviewed profile creation workflow).",
    )

    ctx.register_tool(
        name="profile_build_status",
        toolset="profile-builder",
        schema={
            "type": "object",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Build name; omit for all builds"},
                },
            },
        },
        handler=handle_tool_status,
        description="Show profile-build status for one build or all builds.",
    )

    ctx.register_tool(
        name="profile_build_apply",
        toolset="profile-builder",
        schema={
            "type": "object",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Build name"},
                },
                "required": ["name"],
            },
        },
        handler=handle_tool_apply,
        description="Apply a confirmed profile-build manifest (implementation phase).",
    )

    ctx.register_tool(
        name="profile_build_validate",
        toolset="profile-builder",
        schema={
            "type": "object",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Build name"},
                },
                "required": ["name"],
            },
        },
        handler=handle_tool_validate,
        description="Run validation checks for a built profile.",
    )

    ctx.register_tool(
        name="profile_build_rollback",
        toolset="profile-builder",
        schema={
            "type": "object",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Build name"},
                },
                "required": ["name"],
            },
        },
        handler=handle_tool_rollback,
        description="Restore the most recent snapshot for a profile build.",
    )
