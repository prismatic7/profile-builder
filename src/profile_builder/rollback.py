"""Rollback — restore a profile from snapshot evidence.

Every apply step records a snapshot before mutating. Rollback restores the
most recent snapshot (or the ABSENT marker, which deletes the profile dir).
"""

from __future__ import annotations

from .apply import _restore_snapshot
from .state import Build, BuildError, BuildStore


def rollback(build: Build, store: BuildStore, profile: str) -> str:
    """Restore the most recent snapshot for this build."""
    if not build.snapshots:
        raise BuildError(f"build {build.name!r} has no snapshots to roll back to")
    rel = build.snapshots[-1]
    _restore_snapshot(profile, rel, store)
    # Pop the restored snapshot so a second rollback goes further back.
    build.snapshots = build.snapshots[:-1]
    store.save(build)
    return f"restored {profile} from snapshot {rel}"


def snapshot_history(build: Build) -> list[str]:
    """List snapshot refs for a build, newest last."""
    return list(build.snapshots)
