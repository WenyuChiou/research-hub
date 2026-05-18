"""Authentication and session management shims for NotebookLM."""

from __future__ import annotations

import asyncio
import inspect
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from notebooklm import AuthError, NotebookLMClient
from research_hub.errors import RequiresAuthRefresh


def default_session_dir(research_hub_dir: Path) -> Path:
    """Return the legacy Chromium profile directory for this vault."""
    return research_hub_dir / "nlm_sessions" / "default"


def default_state_file(research_hub_dir: Path) -> Path:
    """Return the Playwright storage state path for this vault."""
    return research_hub_dir / "nlm_sessions" / "state.json"


def _tighten_state_file_perms(target: Path) -> None:
    """Chmod state.json to user-only (G3 P1 #2).

    Pre-fix the parent dir got chmod 0700 via chmod_sensitive but the
    state.json file itself stayed at default umask (0644 on POSIX,
    world-readable). state.json holds Google session cookies; any
    local user could read it and hijack the NLM session. On Windows,
    chmod_sensitive is currently a no-op (G3 P2 #14 will fix that in
    a separate wave); the POSIX path tightens to 0600 immediately.
    """
    if not target.is_file():
        return
    try:
        from research_hub.security import chmod_sensitive
        chmod_sensitive(target, mode=0o600)
    except Exception as exc:
        print(
            f"  [nlm] WARN could not tighten {target} permissions: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )


def login_nlm(
    user_data_dir: Path,
    *,
    state_file: Path | None = None,
    headless: bool = False,
    timeout_sec: int = 300,
    stable_hold_sec: int = 5,
) -> int:
    """Open notebooklm-py's one-time login flow and save storage state."""
    del headless, timeout_sec, stable_hold_sec
    target = Path(state_file) if state_file is not None else Path(user_data_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "notebooklm.notebooklm_cli", "login", "--storage", str(target)]
    rc = subprocess.run(cmd, check=False).returncode
    if rc == 0:
        # G3 P1 #2: tighten newly-created state.json permissions.
        _tighten_state_file_perms(target)
    return rc


def check_session_health(state_file: Path) -> dict[str, Any]:
    """Return ``ok``, ``reason``, and ``expires_at`` for a storage state."""
    state_file = Path(state_file)
    if not state_file.exists():
        return {"ok": False, "reason": "state.json missing", "expires_at": None}
    try:
        ok = asyncio.run(_probe_state_file(state_file))
        return {"ok": ok, "reason": "ok" if ok else "auth invalid", "expires_at": None}
    except AuthError as exc:
        return {"ok": False, "reason": f"auth error: {exc}", "expires_at": None}
    except Exception as exc:
        return {"ok": False, "reason": f"unexpected error: {exc}", "expires_at": None}


def require_session_health(state_file: Path) -> None:
    """Raise a structured auth-refresh error when NotebookLM auth is stale."""

    health = check_session_health(state_file)
    if health.get("ok"):
        return
    reason = str(health.get("reason") or "auth invalid")
    from research_hub._invocation import recommended_cli_invocation

    command = f"{recommended_cli_invocation()} notebooklm login"
    raise RequiresAuthRefresh(
        service="NotebookLM",
        fix_command=command,
        message=f"NotebookLM session check failed: {reason}. Run: {command}",
    )


async def _probe_state_file(state_file: Path) -> bool:
    client = NotebookLMClient.from_storage(path=str(state_file))
    if inspect.isawaitable(client):
        client = await client
    async with client:
        await client.notebooks.list()
        return True


@dataclass
class ImportResult:
    ok: bool
    files_copied: int = 0
    bytes_copied: int = 0
    error: str = ""


def import_session(
    source_session_dir: Path,
    source_state_file: Path,
    dest_session_dir: Path | None = None,
    dest_state_file: Path | None = None,
    *,
    overwrite: bool = False,
) -> ImportResult:
    """Import a saved NotebookLM session from another vault.

    Supports the legacy four-path call shape used by the CLI. When only two
    paths are supplied, it copies a single storage state file.
    """
    source_session_dir = Path(source_session_dir)
    source_state_file = Path(source_state_file)
    if dest_session_dir is None and dest_state_file is None:
        raise TypeError("dest_state_file is required")
    if dest_state_file is None:
        dest_state_file = Path(source_state_file)
        source_state_file = source_session_dir
        dest_session_dir = None
    else:
        dest_state_file = Path(dest_state_file)
        dest_session_dir = Path(dest_session_dir) if dest_session_dir is not None else None

    if not source_state_file.exists():
        return ImportResult(ok=False, error=f"source state file not found: {source_state_file}")

    files_copied = 0
    bytes_copied = 0
    if dest_session_dir is not None and source_session_dir.exists():
        if dest_session_dir.exists():
            if not overwrite and any(dest_session_dir.iterdir()):
                return ImportResult(
                    ok=False,
                    error=f"dest session at {dest_session_dir} already exists; pass overwrite=True",
                )
            shutil.rmtree(dest_session_dir)
        dest_session_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_session_dir, dest_session_dir)
        copied_files = [path for path in dest_session_dir.rglob("*") if path.is_file()]
        files_copied += len(copied_files)
        bytes_copied += sum(path.stat().st_size for path in copied_files)

    dest_state_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_state_file, dest_state_file)
    files_copied += 1
    bytes_copied += dest_state_file.stat().st_size

    return ImportResult(ok=True, files_copied=files_copied, bytes_copied=bytes_copied)


def login_from_browser(
    state_file: Path,
    *,
    browser: str | None = None,
) -> int:
    """Non-interactive login by importing cookies from an already-logged-in browser.

    Delegates to the upstream ``notebooklm.notebooklm_cli login --browser-cookies``
    path (which uses rookiepy to extract Google cookies without launching Playwright).
    Requires ``rookiepy`` to be installed: ``pip install 'research-hub[browser-auth]'``.

    Precedence (in CLI dispatch):
        --import-from > --from-browser > interactive default

    Args:
        state_file: Path where the storage state JSON will be written.
        browser: Specific browser to read cookies from (e.g. ``"chrome"``,
            ``"firefox"``, ``"edge"``). Pass ``None`` for auto-detection
            (rookiepy tries all installed browsers). Do NOT pass ``"auto"`` —
            that is the CLI-layer sentinel; callers should normalise it to None.

    Returns:
        The upstream subprocess return code (0 = success, non-zero = failure).
        On failure the caller should print an actionable hint referencing
        ``pip install 'research-hub[browser-auth]'``.
    """
    state_file = Path(state_file)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m", "notebooklm.notebooklm_cli",
        "login",
        "--storage", str(state_file),
        "--browser-cookies",
    ]
    # Append the specific browser name only when one is requested; bare
    # --browser-cookies means "auto-detect" to the upstream CLI.
    if browser is not None:
        cmd.append(browser)
    rc = subprocess.run(cmd, check=False).returncode
    if rc == 0:
        _tighten_state_file_perms(state_file)
    return rc


def is_session_logged_in(state_file: Path) -> bool:
    """Compatibility helper around ``check_session_health``."""
    return bool(check_session_health(state_file).get("ok"))
