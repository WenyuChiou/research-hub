"""PR-D: ``notebooklm login --auto-detect`` — fully-automatic zero-touch login.

Replaces the half-automatic ``--wait-file`` flow (which still requires
the user to ``touch`` a file after browser sign-in) with a cookies-poll
that detects "user reached the NotebookLM homepage" by looking for a
``notebooklm.google.com`` row in the patchright Chromium profile's
Cookies SQLite. When detected, research-hub feeds both ``\\n`` (any
pending ``input()`` ENTER) AND ``y\\n`` (any pending ``click.confirm``
"Save anyway?" fallback) so the upstream save fires regardless of which
prompt path the SDK takes. Fail-closed on timeout (nothing saved).
"""

from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path

import pytest

import research_hub.notebooklm.auth as auth
from research_hub.notebooklm.auth import (
    _has_notebooklm_cookie,
    _login_with_auto_detect,
)


class _Stdin:
    """Capture stub that survives .close() (real BytesIO does not)."""
    def __init__(self):
        self.buf = b""
        self.closed = False
    def write(self, b):
        self.buf += b
    def flush(self):
        pass
    def close(self):
        self.closed = True
    def getvalue(self):
        return self.buf


class _FakeProc:
    def __init__(self, *, exits_with=None):
        self.stdin = _Stdin()
        self._exits_with = exits_with        # not None -> poll() returns it
        self.returncode = None
        self.terminated = False
        self.killed = False

    def poll(self):
        if self.returncode is not None:
            return self.returncode
        if self._exits_with is not None:
            self.returncode = self._exits_with
            return self._exits_with
        return None

    def wait(self, timeout=None):
        self.returncode = 0
        return 0

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(auth.time, "sleep", lambda *_a, **_k: None)


def _build_cookies_db(path: Path, *, with_notebooklm: bool) -> None:
    """Create a real (read-only-poll-compatible) Cookies SQLite stub."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(path)) as conn:
        conn.execute(
            "CREATE TABLE cookies (host_key TEXT, name TEXT, value TEXT)"
        )
        # always seed an unrelated row so the table is non-empty
        conn.execute(
            "INSERT INTO cookies VALUES ('accounts.google.com', 'NID', 'x')"
        )
        if with_notebooklm:
            conn.execute(
                "INSERT INTO cookies VALUES "
                "('.notebooklm.google.com', 'AUTH', 'y')"
            )
        conn.commit()


# ---- _has_notebooklm_cookie unit tests ----


def test_has_notebooklm_cookie_missing_file_returns_false(tmp_path):
    assert _has_notebooklm_cookie(tmp_path / "no-such.db") is False


def test_has_notebooklm_cookie_no_matching_row_returns_false(tmp_path):
    db = tmp_path / "Cookies"
    _build_cookies_db(db, with_notebooklm=False)
    assert _has_notebooklm_cookie(db) is False


def test_has_notebooklm_cookie_matching_row_returns_true(tmp_path):
    db = tmp_path / "Cookies"
    _build_cookies_db(db, with_notebooklm=True)
    assert _has_notebooklm_cookie(db) is True


def test_has_notebooklm_cookie_corrupt_file_returns_false(tmp_path):
    """Defensive: a Cookies file that's not a SQLite DB (e.g., chromium
    still writing initial bytes) returns False so the calling loop
    simply polls again on the next iteration."""
    db = tmp_path / "Cookies"
    db.write_bytes(b"not a sqlite file")
    assert _has_notebooklm_cookie(db) is False


# ---- _login_with_auto_detect integration tests ----


def _make_cookies_appear_mid_loop(tmp_path, monkeypatch):
    """Patch ``_patchright_cookies_db`` to a tmp path; on the first
    mocked ``time.sleep`` call (mid-poll-loop), materialise a Cookies
    SQLite that contains the notebooklm.google.com row -- simulating
    the user signing in and landing on the NotebookLM homepage."""
    db = tmp_path / "browser_profile" / "Default" / "Cookies"
    monkeypatch.setattr(auth, "_patchright_cookies_db", lambda: db)

    def _sleep(*_a, **_k):
        if not db.exists():
            _build_cookies_db(db, with_notebooklm=True)

    monkeypatch.setattr(auth.time, "sleep", _sleep)
    return db


def test_cookie_detection_triggers_save(tmp_path, monkeypatch):
    proc = _FakeProc()
    monkeypatch.setattr(auth.subprocess, "Popen", lambda *a, **k: proc)
    _make_cookies_appear_mid_loop(tmp_path, monkeypatch)

    rc = _login_with_auto_detect(["x"], timeout=30, state_file=tmp_path / "s")

    assert rc == 0
    # Both ENTER and "Save anyway? y" are fed so the upstream save fires
    # whichever prompt path the SDK actually takes for this run.
    assert proc.stdin.getvalue() == b"\ny\n"
    assert not proc.terminated


def test_timeout_is_fail_closed(tmp_path, monkeypatch):
    """No cookie appears -> deadline expires -> proc killed, rc=124,
    nothing fed to stdin (no save)."""
    db = tmp_path / "browser_profile" / "Default" / "Cookies"
    monkeypatch.setattr(auth, "_patchright_cookies_db", lambda: db)
    proc = _FakeProc()
    monkeypatch.setattr(auth.subprocess, "Popen", lambda *a, **k: proc)
    seq = iter([1000.0, 1000.0])

    def _clock():
        try:
            return next(seq)
        except StopIteration:
            return 9_999.0

    monkeypatch.setattr(auth.time, "monotonic", _clock)

    rc = _login_with_auto_detect(["x"], timeout=5, state_file=tmp_path / "s")

    assert rc == 124
    assert proc.terminated
    assert proc.stdin.getvalue() == b""


def test_upstream_self_exit_propagates(tmp_path, monkeypatch):
    """Upstream SDK exits on its own (e.g., browser launch error) before
    detection; that exit code propagates out without us feeding stdin."""
    db = tmp_path / "browser_profile" / "Default" / "Cookies"
    monkeypatch.setattr(auth, "_patchright_cookies_db", lambda: db)
    proc = _FakeProc(exits_with=3)
    monkeypatch.setattr(auth.subprocess, "Popen", lambda *a, **k: proc)

    rc = _login_with_auto_detect(["x"], timeout=30, state_file=tmp_path / "s")

    assert rc == 3
    assert proc.stdin.getvalue() == b""


def test_post_signal_wait_timeout_tightens_and_fails(tmp_path, monkeypatch):
    """Upstream saved storage_state but is slow to EXIT after the signal:
    proc.wait() times out -> rc 1, BUT perms must still be tightened
    (the file is on disk with default perms) and the proc killed.
    Parity guarantee with ``_login_with_wait_file``'s equivalent test."""
    state_file = tmp_path / "state.json"

    class _SlowProc(_FakeProc):
        def wait(self, timeout=None):
            raise subprocess.TimeoutExpired(cmd=["x"], timeout=timeout)

    proc = _SlowProc()
    monkeypatch.setattr(auth.subprocess, "Popen", lambda *a, **k: proc)
    _make_cookies_appear_mid_loop(tmp_path, monkeypatch)

    tightened = {"called": False}
    monkeypatch.setattr(
        auth, "_tighten_state_file_perms",
        lambda *_a, **_k: tightened.__setitem__("called", True),
    )

    rc = _login_with_auto_detect(["x"], timeout=30, state_file=state_file)

    assert rc == 1
    assert tightened["called"] is True
    assert proc.killed or proc.terminated


def test_cookies_path_prefers_modern_network_subdir(tmp_path, monkeypatch):
    """Hotfix regression: modern Chromium (80+) stores Cookies under
    ``Default/Network/Cookies``. The pre-hotfix PR-D code hardcoded the
    legacy ``Default/Cookies`` path -- auto-detect polling looked at the
    wrong file, the user logged in but the save never fired."""
    from notebooklm.cli import session as nlm_session
    profile = tmp_path / "browser_profile"
    (profile / "Default" / "Network").mkdir(parents=True)
    (profile / "Default" / "Network" / "Cookies").write_bytes(b"modern")
    monkeypatch.setattr(nlm_session, "get_browser_profile_dir", lambda: profile)

    result = auth._patchright_cookies_db()

    assert result == profile / "Default" / "Network" / "Cookies"
    assert result.exists()


def test_cookies_path_falls_back_to_legacy_when_only_legacy_exists(tmp_path, monkeypatch):
    """A user on an old Chromium version with no Network/ subdir gets the
    legacy ``Default/Cookies`` path. Defensive fallback."""
    from notebooklm.cli import session as nlm_session
    profile = tmp_path / "browser_profile"
    (profile / "Default").mkdir(parents=True)
    (profile / "Default" / "Cookies").write_bytes(b"legacy")
    monkeypatch.setattr(nlm_session, "get_browser_profile_dir", lambda: profile)

    result = auth._patchright_cookies_db()

    assert result == profile / "Default" / "Cookies"


def test_cookies_path_returns_modern_path_when_neither_exists_yet(
    tmp_path, monkeypatch,
) -> None:
    """At browser startup neither path exists yet. Return the modern
    path so the next poll iteration finds it the moment chromium writes
    it (which it will, in the modern location)."""
    from notebooklm.cli import session as nlm_session
    profile = tmp_path / "browser_profile"
    monkeypatch.setattr(nlm_session, "get_browser_profile_dir", lambda: profile)

    result = auth._patchright_cookies_db()

    assert result == profile / "Default" / "Network" / "Cookies"
    assert not result.exists()    # neither path materialised yet


def test_stale_cookie_pre_existing_does_not_false_trigger(tmp_path, monkeypatch):
    """W1 (PR-D review): if the profile already has a stale
    notebooklm.google.com cookie from a previous login (file mtime
    pre-dates subprocess launch), the polling MUST NOT immediately
    fire a save. Detection requires fresh writes in THIS session."""
    db = tmp_path / "browser_profile" / "Default" / "Cookies"
    _build_cookies_db(db, with_notebooklm=True)
    # Backdate the mtime so the freshness check fails (no fresh writes).
    import os
    old = 1_000_000.0
    os.utime(db, (old, old))

    monkeypatch.setattr(auth, "_patchright_cookies_db", lambda: db)
    proc = _FakeProc()
    monkeypatch.setattr(auth.subprocess, "Popen", lambda *a, **k: proc)
    # Force a quick timeout so the test doesn't actually wait.
    seq = iter([2_000_000.0, 2_000_000.0])

    def _clock():
        try:
            return next(seq)
        except StopIteration:
            return 9_999_999.0

    monkeypatch.setattr(auth.time, "monotonic", _clock)

    rc = _login_with_auto_detect(["x"], timeout=5, state_file=tmp_path / "s")

    # The cookie IS present but the file mtime is older than our
    # subprocess launch -> NOT a fresh sign-in -> timeout fail-closed.
    assert rc == 124
    assert proc.stdin.getvalue() == b""    # nothing fed -> no save


def test_dispatch_routes_to_auto_detect_when_flag_set(tmp_path, monkeypatch):
    """`login_nlm(auto_detect=True, ...)` must dispatch to
    `_login_with_auto_detect`, not `_login_with_wait_file` or a plain
    `subprocess.run`. Anti-regression for the dispatch precedence."""
    called = {"wait_file": False, "auto_detect": False, "run": False}

    def fake_run(*a, **k):
        called["run"] = True
        return subprocess.CompletedProcess(args=a, returncode=0)

    def fake_wait_file(*a, **k):
        called["wait_file"] = True
        return 0

    def fake_auto_detect(*a, **k):
        called["auto_detect"] = True
        return 0

    monkeypatch.setattr(auth.subprocess, "run", fake_run)
    monkeypatch.setattr(auth, "_login_with_wait_file", fake_wait_file)
    monkeypatch.setattr(auth, "_login_with_auto_detect", fake_auto_detect)
    monkeypatch.setattr(auth, "_tighten_state_file_perms", lambda *_a, **_k: None)

    state = tmp_path / "state.json"
    rc = auth.login_nlm(
        tmp_path / "session_dir",
        state_file=state,
        auto_detect=True,
    )

    assert rc == 0
    assert called["auto_detect"] is True
    assert called["wait_file"] is False
    assert called["run"] is False
