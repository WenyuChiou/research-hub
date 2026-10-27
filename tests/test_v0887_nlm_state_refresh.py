"""v0.88.7 / v1.0.0 — NotebookLMClient session durability.

v0.88.7 root cause: Google rotates short-lived auth tokens (SIDCC /
SIDTS / OSID / CSRF) each session, but research-hub never wrote them
back to state.json.

v1.0.0 Fix-1: ``keepalive_sec`` kwarg wires the upstream background
cookie-rotation loop for long upload/download sessions.

v1.0.0 Fix-3: The old research-hub ``_save_state()`` in ``close()``
was redundant AND racy — it bypassed the upstream ``threading.Lock``
serialisation. It is removed; ``close()`` now delegates to upstream
``__aexit__`` which always persists the live jar race-free via
``ClientCore.close() → save_cookies()``.

These tests verify the wiring without spinning up a real Google session.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def saved_calls(monkeypatch):
    """Capture every save_cookies_to_storage invocation."""
    calls: list[tuple[object, Path]] = []

    def fake_save(cookie_jar, path):
        calls.append((cookie_jar, Path(str(path))))

    # Patch in notebooklm.auth so any direct calls to save_cookies_to_storage
    # from research-hub code are captured.
    import notebooklm.auth as upstream_auth

    monkeypatch.setattr(upstream_auth, "save_cookies_to_storage", fake_save)
    return calls


class _FakeUpstream:
    """Stand-in for notebooklm.NotebookLMClient — no real Google calls.

    Tracks the kwargs passed to from_storage and how many times __aexit__
    was called (representing the upstream on-close cookie save).
    """

    # Class-level registry so fake_from_storage can expose the constructed
    # instance to tests that need to inspect it.
    _last_instance: "_FakeUpstream | None" = None
    _from_storage_kwargs: dict = {}

    def __init__(self, *, storage_path: str):
        self.auth = SimpleNamespace(
            cookies={},
            cookie_jar=object(),
            csrf_token="csrf",
            session_id="sid",
            storage_path=storage_path,
        )
        self.refresh_called = 0
        self.aexit_called = 0
        _FakeUpstream._last_instance = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        # In production, ClientCore.__aexit__ → close() → save_cookies().
        # We record the call so tests can verify close() delegates here.
        self.aexit_called += 1
        return False

    async def refresh_auth(self):
        self.refresh_called += 1
        return self.auth


@pytest.fixture
def fake_client_class(monkeypatch):
    """Patch notebooklm-py's upstream client constructor so we never
    touch the network. ``from_storage`` records kwargs and returns a
    coroutine that yields a fresh ``_FakeUpstream``."""

    async def fake_from_storage(*, path, timeout=None, **kwargs):
        _FakeUpstream._from_storage_kwargs = dict(kwargs)
        return _FakeUpstream(storage_path=str(path))

    monkeypatch.setattr(
        "notebooklm.NotebookLMClient.from_storage",
        staticmethod(fake_from_storage),
    )
    return fake_from_storage


# ---------------------------------------------------------------------------
# FIX-1: keepalive forwarding
# ---------------------------------------------------------------------------

def test_keepalive_sec_forwarded_to_upstream_from_storage(
    tmp_path: Path, fake_client_class
) -> None:
    """NotebookLMClient(keepalive_sec=600) must forward keepalive=600.0 to
    the upstream from_storage() call — this is the sole wiring point for the
    background cookie-rotation loop."""
    from research_hub.notebooklm.client import NotebookLMClient

    _FakeUpstream._from_storage_kwargs = {}
    state = tmp_path / "state.json"
    state.write_text("{}", encoding="utf-8")

    client = NotebookLMClient(state, headless=True, timeout_sec=10, keepalive_sec=600)
    client.close()

    kwargs = _FakeUpstream._from_storage_kwargs
    assert "keepalive" in kwargs, (
        "keepalive_sec=600 must forward keepalive= to from_storage; "
        f"got kwargs={kwargs}"
    )
    assert kwargs["keepalive"] == 600.0, (
        f"expected keepalive=600.0, got {kwargs['keepalive']!r}"
    )


def test_default_construction_does_not_enable_keepalive(
    tmp_path: Path, fake_client_class
) -> None:
    """Default NotebookLMClient (keepalive_sec=None) must NOT pass keepalive
    to from_storage — keepalive-off is required for fast health-probe / doctor
    paths."""
    from research_hub.notebooklm.client import NotebookLMClient

    _FakeUpstream._from_storage_kwargs = {}
    state = tmp_path / "state.json"
    state.write_text("{}", encoding="utf-8")

    client = NotebookLMClient(state, headless=True, timeout_sec=10)
    client.close()

    kwargs = _FakeUpstream._from_storage_kwargs
    assert "keepalive" not in kwargs, (
        "Default construction must not pass keepalive to from_storage; "
        f"got kwargs={kwargs}"
    )


def test_upload_path_uses_keepalive_600(tmp_path: Path, monkeypatch) -> None:
    """_make_client called from upload paths must construct NotebookLMClient
    with keepalive_sec=600 so long multi-shard uploads don't drop mid-way."""
    from research_hub.notebooklm import upload as nlm_upload

    captured_keepalive: list[int | None] = []

    class _SpyClient:
        def __init__(self, state_file, *, headless=True, timeout_sec=120, keepalive_sec=None):
            captured_keepalive.append(keepalive_sec)
            self._active_notebook_id = ""

        def close(self):
            pass

    monkeypatch.setattr(nlm_upload, "NotebookLMClient", _SpyClient)

    state = tmp_path / "state.json"
    state.write_text("{}", encoding="utf-8")
    nlm_upload._make_client(state, headless=False, keepalive_sec=600)

    assert captured_keepalive == [600], (
        f"upload _make_client must pass keepalive_sec=600; got {captured_keepalive}"
    )


# ---------------------------------------------------------------------------
# FIX-3: close() delegates to upstream __aexit__ (exactly once, no double-save)
# ---------------------------------------------------------------------------

def test_close_delegates_to_upstream_aexit_exactly_once(
    tmp_path: Path, fake_client_class, saved_calls: list
) -> None:
    """After Fix-3, close() must call the upstream __aexit__ exactly once
    (which in production triggers ClientCore.close → lock-serialized save_cookies).
    The old research-hub _save_state() path — which called save_cookies_to_storage
    directly — must NOT fire from close(), eliminating the race."""
    from research_hub.notebooklm.client import NotebookLMClient

    state = tmp_path / "state.json"
    state.write_text("{}", encoding="utf-8")

    client = NotebookLMClient(state, headless=True, timeout_sec=10)
    upstream = _FakeUpstream._last_instance
    assert upstream is not None

    client.close()

    # Upstream __aexit__ called exactly once — this is the sole save path.
    assert upstream.aexit_called == 1, (
        f"Expected upstream __aexit__ called once; got {upstream.aexit_called}"
    )
    # research-hub must NOT call save_cookies_to_storage directly from close().
    # In our fake, save_cookies_to_storage is tracked by saved_calls. If
    # research-hub's old _save_state() still fires, this would be non-empty.
    assert saved_calls == [], (
        "close() must not call save_cookies_to_storage directly (race removed); "
        f"got {len(saved_calls)} direct save(s)"
    )


def test_close_retightens_state_perms_after_upstream_save(
    tmp_path: Path, fake_client_class, monkeypatch
) -> None:
    """Fix-3 must still preserve G3 P1 #2: upstream's on-close save_cookies()
    rewrites state.json (Google auth cookies) WITHOUT restricting perms, so
    close() must re-harden it AFTER the upstream __aexit__ save (the removed
    _save_state() used to carry this re-tighten)."""
    from research_hub.notebooklm import auth as nlm_auth

    calls: list[tuple[Path, int]] = []

    def fake_tighten(path):
        # Capture aexit_called at invocation time to assert ordering:
        # the re-tighten MUST run after the authoritative upstream save.
        inst = _FakeUpstream._last_instance
        calls.append((Path(str(path)), inst.aexit_called if inst else -1))

    monkeypatch.setattr(nlm_auth, "_tighten_state_file_perms", fake_tighten)

    from research_hub.notebooklm.client import NotebookLMClient

    state = tmp_path / "state.json"
    state.write_text("{}", encoding="utf-8")

    client = NotebookLMClient(state, headless=True, timeout_sec=10)
    client.close()

    assert len(calls) == 1, f"expected exactly one re-tighten on close(); got {calls}"
    tightened_path, aexit_at_call = calls[0]
    assert tightened_path == state, (
        f"re-tighten must target the state file; got {tightened_path}"
    )
    assert aexit_at_call == 1, (
        "re-tighten must run AFTER upstream __aexit__ (the authoritative "
        f"on-close cookie write); aexit_called was {aexit_at_call} at re-tighten"
    )


def test_close_does_not_raise_even_if_upstream_aexit_raises(
    tmp_path: Path, fake_client_class
) -> None:
    """close() must remain best-effort even if the upstream __aexit__ raises
    (matches the pre-existing contract)."""

    class _RaisingUpstream(_FakeUpstream):
        async def __aexit__(self, *exc):
            self.aexit_called += 1
            raise RuntimeError("upstream close failed")

    async def fake_from_storage(*, path, timeout=None, **kwargs):
        return _RaisingUpstream(storage_path=str(path))

    import notebooklm
    # Temporarily monkeypatch within the test body using a plain setattr
    # (no monkeypatch fixture available in this style — use try/finally).
    original = notebooklm.NotebookLMClient.from_storage
    notebooklm.NotebookLMClient.from_storage = staticmethod(fake_from_storage)  # type: ignore[assignment]
    try:
        from research_hub.notebooklm.client import NotebookLMClient
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        client = NotebookLMClient(state, headless=True, timeout_sec=10)
        client.close()  # Must not raise
    finally:
        notebooklm.NotebookLMClient.from_storage = original  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Legacy tests (updated for new mechanics)
# ---------------------------------------------------------------------------

def test_close_save_state_is_best_effort_on_failure(
    tmp_path: Path, monkeypatch, fake_client_class
) -> None:
    """A failing save_cookies_to_storage in the upstream layer must NOT raise
    out of close() — best-effort contract preserved."""
    import notebooklm.auth as upstream_auth

    def boom(*args, **kwargs):
        raise RuntimeError("cookie file is read-only")

    monkeypatch.setattr(upstream_auth, "save_cookies_to_storage", boom)

    from research_hub.notebooklm.client import NotebookLMClient

    state = tmp_path / "state.json"
    state.write_text("{}", encoding="utf-8")

    client = NotebookLMClient(state, headless=True, timeout_sec=10)
    # Must not raise
    client.close()


def test_refresh_and_save_delegates_persistence_without_shadow_write(
    tmp_path: Path, saved_calls: list, fake_client_class
) -> None:
    """SDK refresh owns persistence; Hub must not overwrite its live jar."""
    from research_hub.notebooklm.client import NotebookLMClient

    state = tmp_path / "state.json"
    state.write_text("{}", encoding="utf-8")

    client = NotebookLMClient(state, headless=True, timeout_sec=10)
    client.refresh_and_save()

    assert client._client.refresh_called == 1
    assert saved_calls == [], "must not write the bootstrap cookie shadow"

    client.close()
    assert saved_calls == [], "upstream lifecycle owns all cookie persistence"


def test_save_state_skipped_when_no_storage_path(
    tmp_path: Path, saved_calls: list, monkeypatch
) -> None:
    """Env-var-loaded auth has ``storage_path=None`` — skip the save
    rather than crashing or writing to an unintended file."""

    class _EnvAuthUpstream(_FakeUpstream):
        def __init__(self, *, storage_path):
            super().__init__(storage_path=storage_path)
            # Mimic NOTEBOOKLM_AUTH_JSON env-var auth path.
            self.auth.storage_path = None

    async def fake_from_storage(*, path, timeout=None, **kwargs):
        return _EnvAuthUpstream(storage_path=str(path))

    monkeypatch.setattr(
        "notebooklm.NotebookLMClient.from_storage",
        staticmethod(fake_from_storage),
    )

    from research_hub.notebooklm.client import NotebookLMClient

    state = tmp_path / "state.json"
    state.write_text("{}", encoding="utf-8")
    client = NotebookLMClient(state, headless=True, timeout_sec=10)
    client.close()

    # After Fix-3, close() doesn't call save_cookies_to_storage directly at
    # all, so saved_calls is empty regardless. This test verifies the old
    # no-storage-path path doesn't somehow trigger a rogue direct save.
    assert saved_calls == [], "no direct save_cookies_to_storage call from close()"


def test_refresh_failure_warns_without_leaking_error_details(
    tmp_path, fake_client_class, monkeypatch, capsys
):
    from unittest.mock import AsyncMock
    from research_hub.notebooklm.client import NotebookLMClient
    state = tmp_path / "state.json"
    state.write_text("{}", encoding="utf-8")
    client = NotebookLMClient(state)
    monkeypatch.setattr(client._client, "refresh_auth", AsyncMock(
        side_effect=OSError("private-token <html> /private/session.json")))
    client.refresh_and_save()  # Must not poison the already successful operation.
    output = capsys.readouterr().err
    assert output.count("WARN") == 1 and "refresh/persistence" in output
    assert all(secret not in output for secret in ("private-token", "<html>", "/private/", str(state)))
    client.close()


def test_refresh_permission_hardening_failure_is_best_effort_and_sanitized(
    tmp_path, fake_client_class, monkeypatch, capsys
):
    from research_hub.notebooklm.client import NotebookLMClient
    state = tmp_path / "state.json"
    state.write_text("{}", encoding="utf-8")
    client = NotebookLMClient(state)

    def fail_hardening(path):
        raise OSError("private-token <html> /private/session.json")

    monkeypatch.setattr("research_hub.notebooklm.auth._tighten_state_file_perms", fail_hardening)
    client.refresh_and_save()
    assert client._client.refresh_called == 1
    output = capsys.readouterr().err
    assert output.count("WARN") == 1 and "permissions" in output
    assert all(secret not in output for secret in ("private-token", "<html>", "/private/", str(state)))
    client.close()
