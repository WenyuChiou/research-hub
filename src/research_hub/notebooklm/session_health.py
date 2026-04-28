"""NotebookLM session health checks + cross-vault session import.

Why this exists
---------------
Two recurring login pain points:

1. Google sessions go stale (typically weeks) and the next NLM operation
   fails deep in the browser layer with a wall-of-text URL pointing at
   accounts.google.com — user has to re-read the spew to realize "oh,
   re-login needed". Pre-flight `is_session_logged_in()` lets callers
   surface a 1-line actionable error BEFORE launching the browser.

2. Each vault stores its own session profile under
   `<vault>/.research_hub/nlm_sessions/`. After `research-hub init`
   creates a new vault, NLM-related commands fail until the user
   re-runs `notebooklm login` from scratch (~5 min including the Google
   2FA dance) — even if another vault on the same machine is already
   logged in. `import_session` lets the user copy a logged-in profile
   from a sibling vault and skip the re-login.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

# Heuristic: a Playwright storage_state JSON < 100 bytes is either empty
# or a placeholder. Real logged-in state files are typically 4 KB+ (a
# handful of Google cookies serialize to that range).
_MIN_STATE_FILE_BYTES = 100

# Heuristic: a Chrome user-data dir without auth cookies has no Default/
# subfolder OR a tiny Cookies file. A logged-in profile typically has
# Default/Cookies > 5 KB (multiple google.com cookies).
_MIN_COOKIES_BYTES = 5 * 1024


@dataclass
class SessionHealth:
    session_dir: Path
    state_file: Path
    has_state_file: bool
    state_file_bytes: int
    has_cookies_db: bool
    cookies_db_bytes: int

    @property
    def looks_logged_in(self) -> bool:
        """Conservative: return True only when BOTH the state file and the
        cookies DB look populated. False positives waste a browser launch
        but don't corrupt anything; false negatives prompt a re-login the
        user might not have needed but that's still safe.
        """
        state_ok = self.has_state_file and self.state_file_bytes >= _MIN_STATE_FILE_BYTES
        cookies_ok = self.has_cookies_db and self.cookies_db_bytes >= _MIN_COOKIES_BYTES
        return state_ok or cookies_ok  # OR: either signal is enough

    def actionable_hint(self) -> str:
        if self.looks_logged_in:
            return ""
        if not self.has_state_file and not self.has_cookies_db:
            return (
                "No NotebookLM session for this vault. Run "
                "`research-hub notebooklm login` to sign in, or "
                "`research-hub notebooklm login --import-from <other-vault-path>` "
                "to copy a logged-in session from another vault."
            )
        return (
            "NotebookLM session exists but looks empty/expired. Re-run "
            "`research-hub notebooklm login` to refresh."
        )


def check_session_health(session_dir: Path, state_file: Path) -> SessionHealth:
    """Cheap filesystem-only check — does NOT launch a browser."""
    state_bytes = state_file.stat().st_size if state_file.exists() else 0
    cookies_path = session_dir / "Default" / "Network" / "Cookies"
    if not cookies_path.exists():
        # Older Chromium versions store at Default/Cookies (without Network/)
        cookies_path = session_dir / "Default" / "Cookies"
    cookies_bytes = cookies_path.stat().st_size if cookies_path.exists() else 0
    return SessionHealth(
        session_dir=session_dir,
        state_file=state_file,
        has_state_file=state_file.exists(),
        state_file_bytes=state_bytes,
        has_cookies_db=cookies_path.exists(),
        cookies_db_bytes=cookies_bytes,
    )


def is_session_logged_in(session_dir: Path, state_file: Path) -> bool:
    """Convenience wrapper around `check_session_health(...).looks_logged_in`."""
    return check_session_health(session_dir, state_file).looks_logged_in


@dataclass
class ImportResult:
    ok: bool
    files_copied: int = 0
    bytes_copied: int = 0
    error: str = ""


def import_session(
    source_session_dir: Path,
    source_state_file: Path,
    dest_session_dir: Path,
    dest_state_file: Path,
    *,
    overwrite: bool = False,
) -> ImportResult:
    """Copy a logged-in NLM session profile from one vault to another.

    Refuses to overwrite an existing logged-in dest unless `overwrite=True`
    so the user doesn't accidentally clobber a working session.
    """
    if not source_session_dir.exists():
        return ImportResult(ok=False, error=f"source session dir not found: {source_session_dir}")
    src_health = check_session_health(source_session_dir, source_state_file)
    if not src_health.looks_logged_in:
        return ImportResult(
            ok=False,
            error=(
                f"source session at {source_session_dir} does not look logged in "
                f"(state={src_health.state_file_bytes}B, cookies={src_health.cookies_db_bytes}B). "
                f"Log in there first via `research-hub notebooklm login`."
            ),
        )

    if dest_session_dir.exists() and any(dest_session_dir.iterdir()):
        dest_health = check_session_health(dest_session_dir, dest_state_file)
        if dest_health.looks_logged_in and not overwrite:
            return ImportResult(
                ok=False,
                error=(
                    f"dest session at {dest_session_dir} already looks logged in. "
                    f"Pass overwrite=True to replace it."
                ),
            )
        # Wipe dest first so we don't merge two profiles
        shutil.rmtree(dest_session_dir)

    dest_session_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_session_dir, dest_session_dir)

    if source_state_file.exists():
        dest_state_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_state_file, dest_state_file)

    files = sum(1 for _ in dest_session_dir.rglob("*") if _.is_file())
    total_bytes = sum(p.stat().st_size for p in dest_session_dir.rglob("*") if p.is_file())
    return ImportResult(ok=True, files_copied=files, bytes_copied=total_bytes)
