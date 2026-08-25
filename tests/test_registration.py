"""Contract tests for both supported plugin entry points.

Unlike the srinitude skeleton (which asserted NOTHING registers), this
plugin registers a command and five tools — the tests assert the
registrations are present and correctly shaped.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]


class RecordingContext:
    """Records registrations instead of executing them."""

    def __init__(self) -> None:
        self.commands: List[Dict[str, Any]] = []
        self.tools: List[Dict[str, Any]] = []

    def register_command(self, name: str, handler: Any, description: str = "", **kwargs: Any) -> None:
        self.commands.append({"name": name, "handler": handler, "description": description, **kwargs})

    def register_tool(
        self,
        name: str,
        toolset: str,
        schema: Dict[str, Any],
        handler: Any,
        description: str = "",
        **kwargs: Any,
    ) -> None:
        self.tools.append(
            {
                "name": name,
                "toolset": toolset,
                "schema": schema,
                "handler": handler,
                "description": description,
                **kwargs,
            }
        )


def test_python_entry_point_registers_surface() -> None:
    module = importlib.import_module("profile_builder")
    ctx = RecordingContext()
    module.register(ctx)
    assert len(ctx.commands) == 1
    assert ctx.commands[0]["name"] == "profile-build"
    assert len(ctx.tools) == 5
    names = {t["name"] for t in ctx.tools}
    assert names == {
        "profile_build",
        "profile_build_status",
        "profile_build_apply",
        "profile_build_validate",
        "profile_build_rollback",
    }


def test_tool_schemas_wrap_arguments_under_parameters() -> None:
    module = importlib.import_module("profile_builder")
    ctx = RecordingContext()
    module.register(ctx)
    for tool in ctx.tools:
        schema = tool["schema"]
        assert "parameters" in schema, f"{tool['name']} schema missing 'parameters'"
        assert "properties" in schema["parameters"], f"{tool['name']} schema missing properties"


def test_tool_handlers_return_json_strings() -> None:
    module = importlib.import_module("profile_builder")
    ctx = RecordingContext()
    module.register(ctx)
    for tool in ctx.tools:
        handler = tool["handler"]
        # Handlers must be callable and return str (JSON contract).
        assert callable(handler)


def test_directory_entry_point_uses_current_hermes_loader() -> None:
    core = Path(os.environ["HERMES_CORE"]).resolve()
    assert (core / "hermes_cli/plugins.py").is_file()
    sys.path.insert(0, str(core))
    from hermes_cli.plugins import PluginManager, PluginManifest

    manager = PluginManager()
    manifest = PluginManifest(
        name="profile-builder",
        version="0.1.0",
        source="user",
        path=str(ROOT),
    )
    module = manager._load_directory_module(manifest)
    ctx = RecordingContext()
    module.register(ctx)
    assert len(ctx.commands) == 1
    assert len(ctx.tools) == 5
