"""Validation — verify a built profile actually works.

Checks are read-only: they inspect the profile dir and run `hermes` CLI
queries. The smoke test boots the profile with a trivial prompt and checks
the exit code — it never mutates the profile.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List

from .apply import _run, profile_dir
from .state import Build, BuildError


def _hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))


def _check(checks: List[Dict[str, Any]], name: str, ok: bool, detail: str) -> None:
    checks.append({"name": name, "ok": ok, "detail": detail})


def validate(build: Build, profile: str) -> List[Dict[str, Any]]:
    """Run all validation checks. Returns a list of check results."""
    build.require_phase("validation")
    checks: List[Dict[str, Any]] = []
    pdir = profile_dir(profile)

    # 1. Profile directory exists
    _check(checks, "profile_dir", pdir.exists(), str(pdir))

    # 2. SOUL.md present
    soul = pdir / "SOUL.md"
    _check(checks, "soul_md", soul.exists() and soul.stat().st_size > 0, str(soul))

    # 3. config.yaml present — with `-p` scoping, `hermes config set` writes
    #    to the profile's own config.yaml (profiles/<name>/config.yaml).
    cfg = pdir / "config.yaml"
    _check(checks, "config_yaml", cfg.exists(), str(cfg))

    # 4. Model block present (profiles don't inherit model config)
    model_ok = False
    model_detail = "no config.yaml"
    if cfg.exists():
        text = cfg.read_text()
        model_ok = "model:" in text and ("default:" in text or "provider:" in text)
        model_detail = "model block present" if model_ok else "model block MISSING"
    _check(checks, "model_block", model_ok, model_detail)

    # 5. system_prompt synced with SOUL.md (parse YAML — the raw text is
    #    YAML-escaped, so a substring match against the file is wrong)
    sync_ok = False
    sync_detail = "no SOUL.md or config.yaml"
    if soul.exists() and cfg.exists():
        soul_text = soul.read_text()
        try:
            import yaml

            cfg_data = yaml.safe_load(cfg.read_text())
            sp = (cfg_data or {}).get("system_prompt", "")
            sync_ok = sp == soul_text
            sync_detail = "system_prompt synced" if sync_ok else "system_prompt NOT synced"
        except Exception as exc:
            sync_detail = f"could not parse config.yaml: {exc}"
    _check(checks, "soul_sync", sync_ok, sync_detail)

    # 6. Profile listed by hermes (un-scoped: `profile list` lists all)
    try:
        proc = _run(["hermes", "profile", "list"], profile, scoped=False)
        listed = profile in proc.stdout
        _check(checks, "profile_listed", listed, "hermes profile list")
    except BuildError as exc:
        _check(checks, "profile_listed", False, str(exc))

    # 7. Plugins load (doctor)
    try:
        proc = _run(["hermes", "plugins", "list"], profile)
        _check(checks, "plugins_list", proc.returncode == 0, "hermes plugins list")
    except BuildError as exc:
        _check(checks, "plugins_list", False, str(exc))

    # 8. Skills visible
    try:
        proc = _run(["hermes", "skills", "list"], profile)
        _check(checks, "skills_list", proc.returncode == 0, "hermes skills list")
    except BuildError as exc:
        _check(checks, "skills_list", False, str(exc))

    # 9. Skin applied
    try:
        proc = _run(["hermes", "skin", "list"], profile)
        _check(checks, "skin_list", proc.returncode == 0, "hermes skin list")
    except BuildError as exc:
        _check(checks, "skin_list", False, str(exc))

    # 10. Memory status
    try:
        proc = _run(["hermes", "memory", "status"], profile)
        _check(checks, "memory_status", proc.returncode == 0, "hermes memory status")
    except BuildError as exc:
        _check(checks, "memory_status", False, str(exc))

    # 11. Boot check — the profile starts without error. A real chat smoke
    #     test needs API keys, so we use `hermes -p <profile> status` which
    #     exercises profile loading without network.
    smoke_ok = False
    smoke_detail = "not run"
    try:
        proc = _run(
            ["hermes", "status"],
            profile,
            timeout=120,
        )
        smoke_ok = proc.returncode == 0
        smoke_detail = f"exit {proc.returncode}"
    except BuildError as exc:
        smoke_detail = str(exc)
    _check(checks, "boot_check", smoke_ok, smoke_detail)

    return checks


def summarize(checks: List[Dict[str, Any]]) -> str:
    """Render check results as a compact report."""
    lines = []
    for c in checks:
        mark = "✅" if c["ok"] else "❌"
        lines.append(f"{mark} {c['name']}: {c['detail']}")
    passed = sum(1 for c in checks if c["ok"])
    lines.append(f"\n{passed}/{len(checks)} checks passed")
    return "\n".join(lines)
