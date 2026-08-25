"""Profile-builder state machine — phases, approval records, expiry.

A build is a JSON document under the plugin data dir:

    ~/.hermes/plugins/profile-builder/state/<name>.json

Phases are strictly ordered. Nothing is applied silently: every protected
mutation must carry a reviewed, expiring confirmation record.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

PHASES = ["scoping", "design", "interview", "implementation", "validation"]
PHASE_INDEX = {p: i for i, p in enumerate(PHASES)}

# Confirmation records expire after this many seconds (default 7 days).
DEFAULT_CONFIRM_TTL = 7 * 24 * 3600

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class BuildError(Exception):
    """Raised for invalid build state transitions or bad input."""


@dataclass
class ApprovalRecord:
    """A reviewed, expiring confirmation for one protected mutation."""

    item: str
    action: str
    confirmed_at: float
    expires_at: float
    note: str = ""

    def is_valid(self, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        return now <= self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item": self.item,
            "action": self.action,
            "confirmed_at": self.confirmed_at,
            "expires_at": self.expires_at,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ApprovalRecord":
        return cls(
            item=str(d.get("item", "")),
            action=str(d.get("action", "")),
            confirmed_at=float(d.get("confirmed_at", 0)),
            expires_at=float(d.get("expires_at", 0)),
            note=str(d.get("note", "")),
        )


@dataclass
class Build:
    """One profile build in progress."""

    name: str
    phase: str = "scoping"
    scope: str = ""
    design: str = ""
    manifest: Dict[str, Any] = field(default_factory=dict)
    confirmed: List[str] = field(default_factory=list)
    approvals: List[ApprovalRecord] = field(default_factory=list)
    snapshots: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    # -- validation -----------------------------------------------------

    def validate_name(self) -> None:
        if not _NAME_RE.match(self.name):
            raise BuildError(
                f"invalid profile name {self.name!r}: lowercase alphanumeric, "
                "hyphens and underscores only"
            )

    def advance(self, target: str) -> None:
        """Move to *target* phase. Only forward transitions are allowed."""
        if target not in PHASE_INDEX:
            raise BuildError(f"unknown phase {target!r}")
        cur = PHASE_INDEX[self.phase]
        nxt = PHASE_INDEX[target]
        if nxt < cur:
            raise BuildError(f"cannot move backward from {self.phase} to {target}")
        if nxt == cur:
            return
        self.phase = target
        self.updated_at = time.time()

    def require_phase(self, *allowed: str) -> None:
        if self.phase not in allowed:
            raise BuildError(
                f"build {self.name!r} is in phase {self.phase!r}; "
                f"expected one of {', '.join(allowed)}"
            )

    # -- approvals ------------------------------------------------------

    def add_approval(self, item: str, action: str, note: str = "", ttl: float = DEFAULT_CONFIRM_TTL) -> None:
        now = time.time()
        self.approvals.append(
            ApprovalRecord(
                item=item,
                action=action,
                confirmed_at=now,
                expires_at=now + ttl,
                note=note,
            )
        )
        self.updated_at = time.time()

    def has_valid_approval(self, item: str, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        return any(a.item == item and a.is_valid(now) for a in self.approvals)

    def prune_expired(self, now: float | None = None) -> int:
        now = time.time() if now is None else now
        before = len(self.approvals)
        self.approvals = [a for a in self.approvals if a.is_valid(now)]
        return before - len(self.approvals)

    # -- serialization --------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "phase": self.phase,
            "scope": self.scope,
            "design": self.design,
            "manifest": self.manifest,
            "confirmed": self.confirmed,
            "approvals": [a.to_dict() for a in self.approvals],
            "snapshots": self.snapshots,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Build":
        return cls(
            name=str(d.get("name", "")),
            phase=str(d.get("phase", "scoping")),
            scope=str(d.get("scope", "")),
            design=str(d.get("design", "")),
            manifest=dict(d.get("manifest") or {}),
            confirmed=[str(x) for x in d.get("confirmed", [])],
            approvals=[ApprovalRecord.from_dict(a) for a in d.get("approvals", [])],
            snapshots=[str(x) for x in d.get("snapshots", [])],
            created_at=float(d.get("created_at", time.time())),
            updated_at=float(d.get("updated_at", time.time())),
        )


class BuildStore:
    """Persist builds as JSON files under the plugin data dir."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.state_dir = data_dir / "state"
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        return self.state_dir / f"{name}.json"

    def load(self, name: str) -> Build:
        p = self._path(name)
        if not p.exists():
            raise BuildError(f"no build named {name!r} — start with /profile-build new {name}")
        try:
            return Build.from_dict(json.loads(p.read_text()))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise BuildError(f"build state for {name!r} is corrupt: {exc}") from exc

    def save(self, build: Build) -> None:
        build.validate_name()
        build.updated_at = time.time()
        p = self._path(build.name)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(build.to_dict(), indent=2))
        tmp.replace(p)

    def create(self, name: str) -> Build:
        build = Build(name=name)
        build.validate_name()
        if self._path(name).exists():
            raise BuildError(f"build {name!r} already exists")
        self.save(build)
        return build

    def list(self) -> List[Build]:
        out: List[Build] = []
        for p in sorted(self.state_dir.glob("*.json")):
            try:
                out.append(Build.from_dict(json.loads(p.read_text())))
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
        return out

    def delete(self, name: str) -> None:
        p = self._path(name)
        if p.exists():
            p.unlink()
