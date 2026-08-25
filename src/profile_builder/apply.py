"""Apply layer — orchestrate native Hermes CLIs to implement a manifest.

Every apply step:
  1. requires a valid, unexpired approval record for the item,
  2. snapshots the profile directory first (rollback evidence),
  3. runs the native CLI scoped with HERMES_PROFILE,
  4. records before/after evidence in the build's snapshots list.

The plugin never reimplements profile creation — it drives `hermes`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tarfile
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .state import Build, BuildError, BuildStore

# Items that require an explicit approval record before apply.
APPROVAL_ITEMS = (
    "create",
    "config",
    "plugins",
    "skills",
    "skin",
    "memory",
    "gateway",
    "soul",
    "env",
    "mcp",
    "link",
)

# Items that are inherently destructive / high-risk — always require a
# fresh confirmation even if a stale record exists.
HIGH_RISK_ITEMS = ("env",)


def _hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))


def profile_dir(name: str) -> Path:
    return _hermes_home() / "profiles" / name


def _run(
    args: Sequence[str],
    profile: str,
    *,
    scoped: bool = True,
    timeout: int = 300,
    input_data: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a hermes CLI subprocess, scoped to *profile* via `-p`.

    `-p <profile>` is the ONLY reliable way to scope subcommands (config set,
    skin use, plugins, skills, memory, gateway, status) to a profile. The
    HERMES_PROFILE env var is NOT honoured for config writes — it writes to
    the home-level config.yaml (the default profile's config).

    Use scoped=False for commands that must run un-scoped: `profile create`
    (the profile doesn't exist yet) and `profile list` (lists all profiles).

    Uses check=False: every caller inspects returncode explicitly so the
    error messages include stderr (a CalledProcessError would otherwise
    swallow it).
    """
    env = dict(os.environ)
    cmd = list(args)
    if scoped:
        # -p is a global flag and must come right after `hermes`.
        cmd = [args[0], "-p", profile, *args[1:]]
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            check=False,
            input=input_data,
        )
    except subprocess.TimeoutExpired as exc:
        raise BuildError(f"command timed out after {timeout}s: {' '.join(args)}") from exc


def _snapshot(profile: str, build: Build, store: BuildStore) -> str:
    """Snapshot the profile dir (if it exists) into the snapshots dir."""
    src = profile_dir(profile)
    snap_dir = store.data_dir / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    rel = f"{profile}-{stamp}.tar.gz"
    dest = snap_dir / rel
    if src.exists():
        with tarfile.open(dest, "w:gz") as tar:
            tar.add(src, arcname=profile)
    else:
        # Profile doesn't exist yet — record an empty snapshot marker so
        # rollback knows the pre-state was "absent".
        dest.write_text("__ABSENT__\n")
    build.snapshots.append(rel)
    store.save(build)
    return rel


def _restore_snapshot(profile: str, rel: str, store: BuildStore) -> None:
    """Restore a snapshot. If the snapshot is the ABSENT marker, delete the profile dir."""
    snap_dir = store.data_dir / "snapshots"
    dest = snap_dir / rel
    if not dest.exists():
        raise BuildError(f"snapshot {rel!r} not found")
    target = profile_dir(profile)
    # The ABSENT marker is a plain-text file; real snapshots are gzip. Check
    # magic bytes so read_bytes() never tries to decode a tar.gz as text.
    if dest.read_bytes().startswith(b"__ABSENT__"):
        if target.exists():
            shutil.rmtree(target)
        return
    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(dest, "r:gz") as tar:
        tar.extractall(target.parent, filter="data")


def _require_approval(build: Build, item: str, action: str) -> None:
    if item in HIGH_RISK_ITEMS:
        # High-risk items need a record created for THIS action, not a
        # generic one. Callers create it via add_approval before apply.
        pass
    if not build.has_valid_approval(item):
        raise BuildError(
            f"no valid approval for {item!r} ({action}) — confirm it first "
            f"with /profile-build confirm {build.name}"
        )


def _log_step(build: Build, step: str, detail: str) -> None:
    build.updated_at = time.time()
    # Steps are recorded in the build's manifest under _log for audit.
    log = build.manifest.setdefault("_log", [])
    log.append({"t": time.time(), "step": step, "detail": detail})


# ---------------------------------------------------------------------------
# Step implementations
# ---------------------------------------------------------------------------


def apply_create(build: Build, store: BuildStore, profile: str, description: str) -> str:
    _require_approval(build, "create", f"create profile {profile}")
    rel = _snapshot(profile, build, store)
    proc = _run(
        ["hermes", "profile", "create", profile, "--description", description],
        profile,
        scoped=False,
    )
    if proc.returncode != 0:
        raise BuildError(f"hermes profile create failed: {proc.stderr.strip()}")
    _log_step(build, "create", f"created profile {profile} (snapshot {rel})")
    store.save(build)
    return f"created profile {profile}"


def apply_config(build: Build, store: BuildStore, profile: str, key: str, value: str) -> str:
    _require_approval(build, "config", f"set {key}={value}")
    rel = _snapshot(profile, build, store)
    proc = _run(["hermes", "config", "set", "--force", key, value], profile)
    if proc.returncode != 0:
        raise BuildError(f"hermes config set {key} failed: {proc.stderr.strip()}")
    _log_step(build, "config", f"set {key}={value} (snapshot {rel})")
    store.save(build)
    return f"set {key}={value}"


def apply_plugins(build: Build, store: BuildStore, profile: str, plugins: list[str]) -> str:
    _require_approval(build, "plugins", f"install {', '.join(plugins)}")
    rel = _snapshot(profile, build, store)
    results = []
    for p in plugins:
        proc = _run(["hermes", "plugins", "install", p], profile)
        if proc.returncode != 0:
            raise BuildError(f"hermes plugins install {p} failed: {proc.stderr.strip()}")
        results.append(p)
    _log_step(build, "plugins", f"installed {', '.join(results)} (snapshot {rel})")
    store.save(build)
    return f"installed plugins: {', '.join(results)}"


def apply_skills(build: Build, store: BuildStore, profile: str, skills: list[str]) -> str:
    _require_approval(build, "skills", f"install {', '.join(skills)}")
    rel = _snapshot(profile, build, store)
    results = []
    for s in skills:
        proc = _run(["hermes", "skills", "install", s], profile)
        if proc.returncode != 0:
            raise BuildError(f"hermes skills install {s} failed: {proc.stderr.strip()}")
        results.append(s)
    _log_step(build, "skills", f"installed {', '.join(results)} (snapshot {rel})")
    store.save(build)
    return f"installed skills: {', '.join(results)}"


def apply_skin(build: Build, store: BuildStore, profile: str, skin: str) -> str:
    _require_approval(build, "skin", f"use skin {skin}")
    rel = _snapshot(profile, build, store)
    proc = _run(["hermes", "skin", "use", skin], profile)
    if proc.returncode != 0:
        raise BuildError(f"hermes skin use {skin} failed: {proc.stderr.strip()}")
    _log_step(build, "skin", f"applied skin {skin} (snapshot {rel})")
    store.save(build)
    return f"applied skin {skin}"


def apply_memory(build: Build, store: BuildStore, profile: str, provider: str) -> str:
    _require_approval(build, "memory", f"setup memory provider {provider}")
    rel = _snapshot(profile, build, store)
    proc = _run(["hermes", "memory", "setup", provider], profile)
    if proc.returncode != 0:
        raise BuildError(f"hermes memory setup {provider} failed: {proc.stderr.strip()}")
    _log_step(build, "memory", f"memory provider {provider} (snapshot {rel})")
    store.save(build)
    return f"memory provider {provider}"


def apply_soul(build: Build, store: BuildStore, profile: str, soul_text: str) -> str:
    """Write SOUL.md and sync system_prompt in config.yaml."""
    _require_approval(build, "soul", f"write SOUL.md for {profile}")
    rel = _snapshot(profile, build, store)
    pdir = profile_dir(profile)
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "SOUL.md").write_text(soul_text)
    # Sync system_prompt via the CLI so config.yaml stays canonical.
    proc = _run(
        ["hermes", "config", "set", "--force", "system_prompt", soul_text],
        profile,
    )
    if proc.returncode != 0:
        raise BuildError(f"system_prompt sync failed: {proc.stderr.strip()}")
    _log_step(build, "soul", f"wrote SOUL.md + system_prompt (snapshot {rel})")
    store.save(build)
    return f"wrote SOUL.md + system_prompt for {profile}"


def apply_gateway(build: Build, store: BuildStore, profile: str, platform: str) -> str:
    _require_approval(build, "gateway", f"setup gateway platform {platform}")
    rel = _snapshot(profile, build, store)
    proc = _run(["hermes", "gateway", "setup", platform], profile)
    if proc.returncode != 0:
        raise BuildError(f"hermes gateway setup {platform} failed: {proc.stderr.strip()}")
    _log_step(build, "gateway", f"gateway platform {platform} (snapshot {rel})")
    store.save(build)
    return f"gateway platform {platform}"


def apply_env(build: Build, store: BuildStore, profile: str, key: str, value: str) -> str:
    """Write a profile-level .env entry. HIGH RISK — requires a fresh approval."""
    _require_approval(build, "env", f"write {key} to {profile} .env")
    rel = _snapshot(profile, build, store)
    pdir = profile_dir(profile)
    pdir.mkdir(parents=True, exist_ok=True)
    env_path = pdir / ".env"
    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text().splitlines()
    # Replace existing key, append otherwise.
    found = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}")
    env_path.write_text("\n".join(lines) + "\n")
    _log_step(build, "env", f"wrote {key} to .env (snapshot {rel})")
    store.save(build)
    return f"wrote {key} to {profile} .env"


def apply_mcp(
    build: Build,
    store: BuildStore,
    profile: str,
    name: str,
    command: str,
    args: list[str],
) -> str:
    """Add an MCP server to the profile's config.yaml.

    `hermes mcp add` is interactive (asks to enable tools); pipe 'Y' to
    accept. The server is scoped to the profile via `-p`.
    """
    _require_approval(build, "mcp", f"add MCP server {name}")
    rel = _snapshot(profile, build, store)
    proc = _run(
        ["hermes", "mcp", "add", name, "--command", command, "--args", *args],
        profile,
        input_data="Y\n",
    )
    if proc.returncode != 0:
        raise BuildError(f"hermes mcp add {name} failed: {proc.stderr.strip()}")
    _log_step(build, "mcp", f"added MCP server {name} (snapshot {rel})")
    store.save(build)
    return f"added MCP server {name}"


def apply_link(
    build: Build,
    store: BuildStore,
    profile: str,
    source: str,
    target: str,
) -> str:
    """Symlink a local plugin (or other dir) into the profile's plugins dir.

    `hermes plugins install` only accepts git URLs / community names, so
    local plugins (e.g. ~/.hermes/plugins/unslop) are linked instead.
    """
    _require_approval(build, "link", f"link {source} -> {target}")
    rel = _snapshot(profile, build, store)
    src = Path(source).expanduser()
    if not src.exists():
        raise BuildError(f"link source {source!r} does not exist")
    pdir = profile_dir(profile)
    plugins_dir = pdir / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    dest = plugins_dir / target
    if dest.exists() or dest.is_symlink():
        dest.unlink()
    dest.symlink_to(src, target_is_directory=src.is_dir())
    # If the linked target is a plugin (has plugin.yaml), enable it so the
    # profile actually loads it.
    if (src / "plugin.yaml").exists():
        proc = _run(["hermes", "plugins", "enable", target], profile)
        if proc.returncode != 0:
            raise BuildError(f"hermes plugins enable {target} failed: {proc.stderr.strip()}")
    _log_step(build, "link", f"linked {source} -> {target} (snapshot {rel})")
    store.save(build)
    return f"linked {source} -> {target}"


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

MANIFEST_ACTIONS: dict[str, Any] = {
    "create": apply_create,
    "config": apply_config,
    "plugins": apply_plugins,
    "skills": apply_skills,
    "skin": apply_skin,
    "memory": apply_memory,
    "soul": apply_soul,
    "gateway": apply_gateway,
    "env": apply_env,
    "mcp": apply_mcp,
    "link": apply_link,
}


def apply_manifest(build: Build, store: BuildStore, profile: str) -> list[str]:
    """Apply every confirmed manifest item in order. Returns step results."""
    build.require_phase("implementation")
    results: list[str] = []
    manifest = build.manifest
    for item in MANIFEST_ACTIONS:
        if item not in manifest:
            continue
        spec = manifest[item]
        if item == "create":
            results.append(apply_create(build, store, profile, str(spec.get("description", ""))))
        elif item == "config":
            for kv in spec:
                results.append(
                    apply_config(build, store, profile, str(kv["key"]), str(kv["value"]))
                )
        elif item in ("plugins", "skills"):
            results.append(MANIFEST_ACTIONS[item](build, store, profile, [str(x) for x in spec]))
        elif item == "skin":
            results.append(apply_skin(build, store, profile, str(spec)))
        elif item == "memory":
            results.append(apply_memory(build, store, profile, str(spec)))
        elif item == "soul":
            results.append(apply_soul(build, store, profile, str(spec)))
        elif item == "gateway":
            results.append(apply_gateway(build, store, profile, str(spec)))
        elif item == "env":
            for kv in spec:
                results.append(apply_env(build, store, profile, str(kv["key"]), str(kv["value"])))
        elif item == "mcp":
            for server in spec:
                results.append(
                    apply_mcp(
                        build,
                        store,
                        profile,
                        str(server["name"]),
                        str(server["command"]),
                        [str(a) for a in server.get("args", [])],
                    )
                )
        elif item == "link":
            for link in spec:
                results.append(
                    apply_link(
                        build,
                        store,
                        profile,
                        str(link["source"]),
                        str(link["target"]),
                    )
                )
    build.advance("validation")
    store.save(build)
    return results
