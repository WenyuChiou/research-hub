"""v0.70.1 — NLM session health check + cross-vault import.

Two recurring user pain points this addresses:

1. Google sessions go stale silently. The NEXT NLM operation fails deep
   in the browser layer with a wall-of-text URL pointing at
   accounts.google.com — user has to read the spew to realize "oh,
   re-login". Pre-flight `is_session_logged_in()` surfaces a 1-line
   actionable error BEFORE launching the browser.

2. Each vault stores its own session profile. After `research-hub init`
   creates a new vault, NLM commands fail until the user re-runs the
   ~5-minute interactive login dance — even if a sibling vault on the
   same machine is already logged in. `import_session` lets the user
   copy the logged-in profile across vaults.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from research_hub.notebooklm.session_health import (
    ImportResult,
    SessionHealth,
    check_session_health,
    import_session,
    is_session_logged_in,
)


def _make_logged_in_session(vault_root: Path) -> tuple[Path, Path]:
    """Build a fixture that looks like a real logged-in NLM session:
    state file > 100B + Default/Network/Cookies > 5KB."""
    nlm_root = vault_root / ".research_hub" / "nlm_sessions"
    session_dir = nlm_root / "default"
    state_file = nlm_root / "state.json"
    session_dir.mkdir(parents=True)
    nlm_root.mkdir(exist_ok=True)
    # Realistic Playwright storage_state shape
    state_file.write_text(
        json.dumps({
            "cookies": [{"name": "SID", "value": "x" * 200, "domain": ".google.com"}] * 10,
            "origins": [],
        }),
        encoding="utf-8",
    )
    cookies_path = session_dir / "Default" / "Network" / "Cookies"
    cookies_path.parent.mkdir(parents=True)
    cookies_path.write_bytes(b"\x00" * (10 * 1024))  # 10 KB binary
    return session_dir, state_file


def _make_empty_session(vault_root: Path) -> tuple[Path, Path]:
    nlm_root = vault_root / ".research_hub" / "nlm_sessions"
    session_dir = nlm_root / "default"
    state_file = nlm_root / "state.json"
    session_dir.mkdir(parents=True)
    return session_dir, state_file


# --- session health -----------------------------------------------------


def test_check_session_health_reports_logged_in_when_state_file_and_cookies_present(tmp_path):
    session_dir, state_file = _make_logged_in_session(tmp_path)
    health = check_session_health(session_dir, state_file)
    assert health.looks_logged_in is True
    assert health.has_state_file
    assert health.state_file_bytes > 100
    assert health.has_cookies_db
    assert health.cookies_db_bytes >= 5 * 1024


def test_check_session_health_reports_not_logged_in_when_state_missing(tmp_path):
    session_dir, state_file = _make_empty_session(tmp_path)
    health = check_session_health(session_dir, state_file)
    assert health.looks_logged_in is False
    assert "No NotebookLM session" in health.actionable_hint()


def test_check_session_health_distinguishes_expired_from_missing(tmp_path):
    """A state file that exists but is tiny → 'session exists but looks
    empty/expired' (different message from 'no session at all'). Helps the
    user realize re-login is the right action vs. import."""
    session_dir, state_file = _make_empty_session(tmp_path)
    state_file.write_text("{}", encoding="utf-8")  # 2 bytes, below threshold
    cookies = session_dir / "Default" / "Network" / "Cookies"
    cookies.parent.mkdir(parents=True)
    cookies.write_bytes(b"")  # 0 bytes

    health = check_session_health(session_dir, state_file)
    assert health.looks_logged_in is False
    hint = health.actionable_hint()
    assert "expired" in hint.lower() or "empty" in hint.lower()


def test_is_session_logged_in_convenience_wrapper(tmp_path):
    session_dir, state_file = _make_logged_in_session(tmp_path)
    assert is_session_logged_in(session_dir, state_file) is True

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    assert is_session_logged_in(empty_dir, empty_dir / "state.json") is False


def test_check_session_health_handles_legacy_cookies_path(tmp_path):
    """Older Chromium stored cookies at Default/Cookies (no Network/).
    The check should accept either layout."""
    session_dir, state_file = _make_empty_session(tmp_path)
    state_file.write_text("x" * 200, encoding="utf-8")
    legacy_cookies = session_dir / "Default" / "Cookies"
    legacy_cookies.parent.mkdir(parents=True)
    legacy_cookies.write_bytes(b"\x00" * (10 * 1024))
    health = check_session_health(session_dir, state_file)
    assert health.looks_logged_in is True


# --- import_session -----------------------------------------------------


def test_import_session_copies_logged_in_profile_to_empty_dest(tmp_path):
    src_vault = tmp_path / "old"
    dest_vault = tmp_path / "new"
    src_session, src_state = _make_logged_in_session(src_vault)
    dest_session = dest_vault / ".research_hub" / "nlm_sessions" / "default"
    dest_state = dest_vault / ".research_hub" / "nlm_sessions" / "state.json"

    result = import_session(src_session, src_state, dest_session, dest_state)

    assert result.ok is True
    assert result.files_copied >= 1
    assert result.bytes_copied > 5 * 1024
    # Dest now looks logged in
    assert is_session_logged_in(dest_session, dest_state) is True


def test_import_session_refuses_to_overwrite_logged_in_dest_without_flag(tmp_path):
    src_vault = tmp_path / "old"
    dest_vault = tmp_path / "new"
    src_session, src_state = _make_logged_in_session(src_vault)
    dest_session, dest_state = _make_logged_in_session(dest_vault)

    result = import_session(src_session, src_state, dest_session, dest_state)
    assert result.ok is False
    assert "already looks logged in" in result.error
    assert "overwrite" in result.error


def test_import_session_overwrites_when_flag_set(tmp_path):
    src_vault = tmp_path / "old"
    dest_vault = tmp_path / "new"
    src_session, src_state = _make_logged_in_session(src_vault)
    dest_session, dest_state = _make_logged_in_session(dest_vault)
    # Marker file in src to verify it actually got copied over
    (src_session / "MARKER").write_text("from-src", encoding="utf-8")

    result = import_session(src_session, src_state, dest_session, dest_state, overwrite=True)
    assert result.ok is True
    assert (dest_session / "MARKER").read_text(encoding="utf-8") == "from-src"


def test_import_session_refuses_when_source_is_not_logged_in(tmp_path):
    """User asked to import from a vault that itself isn't logged in →
    error explains why instead of silently copying junk."""
    src_vault = tmp_path / "old"
    dest_vault = tmp_path / "new"
    src_session, src_state = _make_empty_session(src_vault)
    dest_session = dest_vault / ".research_hub" / "nlm_sessions" / "default"
    dest_state = dest_vault / ".research_hub" / "nlm_sessions" / "state.json"

    result = import_session(src_session, src_state, dest_session, dest_state)
    assert result.ok is False
    assert "does not look logged in" in result.error


def test_import_session_handles_missing_source_gracefully(tmp_path):
    src_session = tmp_path / "nonexistent" / "session"
    src_state = tmp_path / "nonexistent" / "state.json"
    dest_session = tmp_path / "new" / "session"
    dest_state = tmp_path / "new" / "state.json"
    result = import_session(src_session, src_state, dest_session, dest_state)
    assert result.ok is False
    assert "not found" in result.error


# --- pre-flight + CLI integration --------------------------------------


def test_preflight_nlm_session_returns_exit_code_when_not_logged_in(tmp_path, capsys):
    """The pre-flight helper used by bundle/upload/generate/download
    should print a friendly error and return 1, not crash."""
    from research_hub.cli import _preflight_nlm_session
    from types import SimpleNamespace
    cfg = SimpleNamespace(research_hub_dir=tmp_path / "vault" / ".research_hub")
    cfg.research_hub_dir.mkdir(parents=True)
    rc = _preflight_nlm_session(cfg, op_name="upload")
    assert rc == 1
    captured = capsys.readouterr()
    assert "session check failed" in captured.err
    assert "research-hub notebooklm login" in captured.err


def test_preflight_nlm_session_returns_none_when_logged_in(tmp_path):
    from research_hub.cli import _preflight_nlm_session
    from types import SimpleNamespace
    vault = tmp_path / "vault"
    _make_logged_in_session(vault)
    cfg = SimpleNamespace(research_hub_dir=vault / ".research_hub")
    rc = _preflight_nlm_session(cfg, op_name="upload")
    assert rc is None
