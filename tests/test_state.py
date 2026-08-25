"""State machine tests — phases, approvals, expiry, persistence."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from profile_builder.state import (
    DEFAULT_CONFIRM_TTL,
    Build,
    BuildError,
    BuildStore,
)


def test_phase_advance_forward_only() -> None:
    b = Build(name="test")
    b.advance("design")
    assert b.phase == "design"
    b.advance("interview")
    assert b.phase == "interview"
    with pytest.raises(BuildError):
        b.advance("scoping")  # backward


def test_require_phase() -> None:
    b = Build(name="test")
    b.require_phase("scoping")
    with pytest.raises(BuildError):
        b.require_phase("implementation")


def test_approval_expiry() -> None:
    b = Build(name="test")
    b.add_approval("plugins", "confirm plugins", ttl=1)
    assert b.has_valid_approval("plugins")
    time.sleep(1.1)
    assert not b.has_valid_approval("plugins")
    assert b.prune_expired() == 1


def test_approval_default_ttl() -> None:
    b = Build(name="test")
    b.add_approval("skin", "confirm skin")
    assert b.has_valid_approval("skin")
    assert b.approvals[0].expires_at - b.approvals[0].confirmed_at == pytest.approx(
        DEFAULT_CONFIRM_TTL
    )


def test_invalid_name_rejected() -> None:
    with pytest.raises(BuildError):
        Build(name="Bad Name!").validate_name()
    Build(name="good-name_1").validate_name()


def test_store_roundtrip(tmp_path: Path) -> None:
    store = BuildStore(tmp_path)
    b = store.create("demo")
    b.scope = "research profile"
    b.add_approval("create", "confirm create")
    store.save(b)

    loaded = store.load("demo")
    assert loaded.name == "demo"
    assert loaded.scope == "research profile"
    assert loaded.has_valid_approval("create")


def test_store_duplicate_create_rejected(tmp_path: Path) -> None:
    store = BuildStore(tmp_path)
    store.create("demo")
    with pytest.raises(BuildError):
        store.create("demo")


def test_store_list_and_delete(tmp_path: Path) -> None:
    store = BuildStore(tmp_path)
    store.create("a")
    store.create("b")
    assert len(store.list()) == 2
    store.delete("a")
    assert len(store.list()) == 1


def test_manifest_roundtrip(tmp_path: Path) -> None:
    store = BuildStore(tmp_path)
    b = store.create("demo")
    b.manifest = {
        "create": {"description": "test profile"},
        "config": [{"key": "model.default", "value": "deepseek-v4-flash:cloud"}],
        "plugins": ["owner/repo"],
    }
    store.save(b)
    loaded = store.load("demo")
    assert loaded.manifest["create"]["description"] == "test profile"
    assert loaded.manifest["config"][0]["key"] == "model.default"
