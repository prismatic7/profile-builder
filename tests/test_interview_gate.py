"""Interview gate tests — the interview phase must be a real gate.

Regression: the enodios build walked straight through the interview phase
because `confirm <name>` with no item bulk-confirmed every manifest item.
These tests pin the corrected behaviour:

  - `confirm <name>` with no item does NOT bulk-confirm in interview
  - every manifest item must be confirmed individually
  - `propose` lists items with detail and confirmed state
  - `env` items never leak values in the interview
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from profile_builder.commands import handle_command

# Isolate the build store from the real ~/.hermes.
TEST_HOME = Path("/tmp/hpb-interview-test")


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch: pytest.MonkeyPatch) -> None:
    if TEST_HOME.exists():
        shutil.rmtree(TEST_HOME)
    TEST_HOME.mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(TEST_HOME))


def _ok(data: str) -> dict[str, Any]:
    parsed: dict[str, Any] = json.loads(data)
    assert parsed.get("success") is True, parsed
    return parsed


def _err(data: str) -> dict[str, Any]:
    parsed: dict[str, Any] = json.loads(data)
    assert parsed.get("success") is False, parsed
    return parsed


def _build_with_manifest(name: str = "demo") -> None:
    """Create a build and walk it to the interview phase with a manifest."""
    _ok(handle_command(f"new {name} research profile"))
    _ok(handle_command(f"scope {name} research profile for testing"))
    _ok(handle_command(f"confirm {name}"))  # scoping -> design
    manifest = json.dumps(
        {
            "create": {"description": "test profile"},
            "config": [{"key": "model.default", "value": "deepseek-v4-flash:cloud"}],
            "plugins": ["owner/repo"],
            "env": [{"key": "SECRET_TOKEN", "value": "s3cr3t-value"}],
        }
    )
    _ok(handle_command(f"design {name} {manifest}"))
    _ok(handle_command(f"confirm {name}"))  # design -> interview


def test_confirm_no_item_does_not_bulk_confirm() -> None:
    _build_with_manifest()
    # In interview, confirm with no item must ERROR (not bulk-confirm).
    result = _err(handle_command("confirm demo"))
    assert "interview not complete" in result["error"]
    assert "create" in result["error"]
    assert "config" in result["error"]
    assert "plugins" in result["error"]
    assert "env" in result["error"]


def test_confirm_requires_each_item_individually() -> None:
    _build_with_manifest()
    _ok(handle_command("confirm demo create"))
    _ok(handle_command("confirm demo config"))
    _ok(handle_command("confirm demo plugins"))
    # env still unconfirmed -> gate holds.
    result = _err(handle_command("confirm demo"))
    assert "env" in result["error"]
    # Confirm env -> gate opens.
    _ok(handle_command("confirm demo env"))
    result = _ok(handle_command("confirm demo"))
    assert result["build"]["phase"] == "implementation"


def test_propose_lists_items_with_detail() -> None:
    _build_with_manifest()
    result = _ok(handle_command("propose demo"))
    items = {it["item"]: it for it in result["items"]}
    assert set(items) == {"create", "config", "plugins", "env"}
    assert items["create"]["detail"] == "create profile demo"
    assert items["config"]["detail"] == "model.default=deepseek-v4-flash:cloud"
    assert items["plugins"]["detail"] == "owner/repo"
    assert items["env"]["confirmed"] is False
    # env values must never appear in the interview.
    assert "s3cr3t-value" not in json.dumps(result)


def test_propose_reflects_confirmed_state() -> None:
    _build_with_manifest()
    _ok(handle_command("confirm demo create"))
    result = _ok(handle_command("propose demo"))
    items = {it["item"]: it for it in result["items"]}
    assert items["create"]["confirmed"] is True
    assert items["config"]["confirmed"] is False


def test_apply_requires_all_approvals() -> None:
    _build_with_manifest()
    # Only some items confirmed — apply must refuse.
    _ok(handle_command("confirm demo create"))
    _ok(handle_command("confirm demo config"))
    result = _err(handle_command("apply demo"))
    assert "no valid approval" in result["error"] or "interview" in result["error"]
