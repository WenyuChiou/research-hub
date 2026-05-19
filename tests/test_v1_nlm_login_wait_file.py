"""PR-D: `notebooklm login --wait-file` — non-interactive login.

Replaces the upstream `input("press ENTER")` gate with a file signal:
the user signs in in the browser then creates the wait-file (or an
automation wrapper does); research-hub feeds the newline that triggers
the upstream storage_state save. Fail-closed on timeout (nothing saved).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import research_hub.notebooklm.auth as auth
from research_hub.notebooklm.auth import _login_with_wait_file


class _Stdin:
    """Capture stub that survives .close() (real BytesIO does not)."""
    def __init__(self):
        self.buf = b""
    def write(self, b):
        self.buf += b
    def flush(self):
        pass
    def close(self):
        pass
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
        if self.returncode is not None:        # already exited (real semantics)
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


def test_signal_file_triggers_save(tmp_path, monkeypatch):
    wait_file = tmp_path / "ready"
    proc = _FakeProc()
    monkeypatch.setattr(auth.subprocess, "Popen", lambda *a, **k: proc)
    # The fn clears any stale signal first, then polls. Simulate the user
    # creating the file mid-loop: the (mocked) inter-poll sleep touches it.
    monkeypatch.setattr(auth.time, "sleep",
                        lambda *_a, **_k: wait_file.write_text("", encoding="utf-8"))

    rc = _login_with_wait_file(["x"], wait_file, wait_timeout=30,
                               state_file=tmp_path / "s")

    assert rc == 0
    assert proc.stdin.getvalue() == b"\n"          # ENTER fed programmatically
    assert not proc.terminated


def test_timeout_is_fail_closed(tmp_path, monkeypatch):
    wait_file = tmp_path / "never"                  # never created
    proc = _FakeProc()
    monkeypatch.setattr(auth.subprocess, "Popen", lambda *a, **k: proc)
    # deadline calc sees 1000; every subsequent check is past the
    # deadline. Robust to extra monotonic() calls (no StopIteration).
    seq = iter([1000.0, 1000.0])

    def _clock():
        try:
            return next(seq)
        except StopIteration:
            return 9_999.0

    monkeypatch.setattr(auth.time, "monotonic", _clock)

    rc = _login_with_wait_file(["x"], wait_file, wait_timeout=5, state_file=tmp_path / "s")

    assert rc == 124                                # fail-closed sentinel
    assert proc.terminated
    assert proc.stdin.getvalue() == b""             # nothing fed -> no save


def test_upstream_self_exit_propagates(tmp_path, monkeypatch):
    wait_file = tmp_path / "ready"
    proc = _FakeProc(exits_with=3)                  # upstream errored pre-signal
    monkeypatch.setattr(auth.subprocess, "Popen", lambda *a, **k: proc)

    rc = _login_with_wait_file(["x"], wait_file, wait_timeout=30,
                               state_file=tmp_path / "s")

    assert rc == 3
    assert proc.stdin.getvalue() == b""


def test_stale_signal_is_cleared_first(tmp_path, monkeypatch):
    """A leftover wait-file from a previous run must not auto-trigger
    before the user has actually logged in."""
    wait_file = tmp_path / "stale"
    wait_file.write_text("old", encoding="utf-8")
    unlinked = {"done": False}
    real_unlink = Path.unlink

    def tracking_unlink(self, *a, **k):
        if self == wait_file:
            unlinked["done"] = True
        return real_unlink(self, *a, **k)

    monkeypatch.setattr(Path, "unlink", tracking_unlink)
    proc = _FakeProc(exits_with=0)
    monkeypatch.setattr(auth.subprocess, "Popen", lambda *a, **k: proc)

    _login_with_wait_file(["x"], wait_file, wait_timeout=5,
                           state_file=tmp_path / "s")
    assert unlinked["done"] is True                 # stale signal removed


def test_post_signal_wait_timeout_tightens_and_fails(tmp_path, monkeypatch):
    """Upstream saved storage_state but is slow to EXIT after the signal:
    proc.wait() times out -> rc 1, BUT perms must still be tightened
    (the file is on disk with default perms) and the proc killed."""
    wait_file = tmp_path / "ready"
    state_file = tmp_path / "state.json"

    class _SlowProc(_FakeProc):
        def wait(self, timeout=None):
            raise subprocess.TimeoutExpired(cmd=["x"], timeout=timeout)

    proc = _SlowProc()
    monkeypatch.setattr(auth.subprocess, "Popen", lambda *a, **k: proc)
    monkeypatch.setattr(auth.time, "sleep",
                        lambda *_a, **_k: wait_file.write_text("", encoding="utf-8"))
    tightened = {"called": False}
    monkeypatch.setattr(auth, "_tighten_state_file_perms",
                        lambda p: tightened.__setitem__("called", True))

    rc = _login_with_wait_file(["x"], wait_file, wait_timeout=30,
                               state_file=state_file)

    assert rc == 1                                  # non-zero (fail)
    assert proc.stdin.getvalue() == b"\n"           # signal WAS fed
    assert tightened["called"] is True              # G3 P1 #2 upheld
    assert proc.terminated                          # slow proc killed
