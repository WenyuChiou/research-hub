"""``notebooklm login --auto-detect`` -- fully-automatic zero-touch login.

research-hub drives a Chromium browser directly and polls the LIVE
``page.url``. The moment the page settles on the NotebookLM host -- and
holds there for a few consecutive polls -- the session is captured
straight from the live browser context via ``storage_state``. No terminal
ENTER, no upstream subprocess, no on-disk Cookies-SQLite race.

Root-cause history: the pre-fix implementation shelled out to the
upstream ``notebooklm login`` subprocess and polled the patchright
Chromium profile's Cookies SQLite on disk. Chromium buffers cookies in
memory and flushes to that SQLite store only on a lazy timer, so a
freshly-signed-in session stayed invisible on disk for minutes and the
poll loop timed out without ever firing the save. Polling ``page.url``
reads live browser state and has no such race.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import research_hub.notebooklm.auth as auth
from research_hub.notebooklm.auth import (
    _browser_profile_dir,
    _is_on_notebooklm_homepage,
    _login_with_auto_detect,
)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Make the poll loop spin instantly -- detection / timeout is driven
    by the mocked clock or the page-URL sequence, never by wall time."""
    monkeypatch.setattr(auth.time, "sleep", lambda *_a, **_k: None)


# ---------------------------------------------------------------------------
# Playwright test doubles
# ---------------------------------------------------------------------------

class _FakePage:
    """A page whose ``.url`` walks a fixed sequence, one step per read."""

    def __init__(self, url_sequence):
        self._urls = list(url_sequence)
        self._idx = 0
        self.goto_calls: list[str] = []

    @property
    def url(self) -> str:
        value = self._urls[min(self._idx, len(self._urls) - 1)]
        self._idx += 1
        return value

    def goto(self, url, **_kwargs):
        self.goto_calls.append(url)


class _FakeContext:
    def __init__(self, page: _FakePage):
        self.pages = [page]
        self.storage_saved_to: str | None = None
        self.closed = False

    def new_page(self):
        return self.pages[0]

    def storage_state(self, path):
        self.storage_saved_to = str(path)
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('{"cookies": [], "origins": []}', encoding="utf-8")

    def close(self):
        self.closed = True


class _FakeChromium:
    def __init__(self, context: _FakeContext | None, *, launch_error: Exception | None = None):
        self._context = context
        self._launch_error = launch_error
        self.launch_kwargs: dict | None = None

    def launch_persistent_context(self, **kwargs):
        self.launch_kwargs = kwargs
        if self._launch_error is not None:
            raise self._launch_error
        return self._context


class _FakePlaywright:
    """The handle ``sync_playwright().start()`` returns. ``.stop()`` tears
    down the driver -- the function under test calls it in a ``finally``."""

    def __init__(self, chromium: _FakeChromium):
        self.chromium = chromium
        self.stopped = False

    def stop(self):
        self.stopped = True


class _FakeSyncPlaywright:
    """Mimics ``sync_playwright()`` -- ``.start()`` returns the playwright
    handle (matching the manual start/stop API the function drives)."""

    def __init__(self, chromium: _FakeChromium):
        self._pw = _FakePlaywright(chromium)

    def start(self) -> _FakePlaywright:
        return self._pw


def _install_fake_playwright(monkeypatch, chromium: _FakeChromium) -> _FakePlaywright:
    """Patch ``playwright.sync_api.sync_playwright`` so the function under
    test gets our fake. The function does ``from playwright.sync_api import
    sync_playwright`` at call time, so patching the module attribute is
    sufficient. Returns the playwright handle so tests can assert ``stop()``
    was called on it."""
    import playwright.sync_api as pw_api

    fake = _FakeSyncPlaywright(chromium)
    monkeypatch.setattr(pw_api, "sync_playwright", lambda: fake)
    return fake._pw


# ---------------------------------------------------------------------------
# _is_on_notebooklm_homepage -- pure unit tests
# ---------------------------------------------------------------------------

def test_homepage_url_is_recognised():
    assert _is_on_notebooklm_homepage("https://notebooklm.google.com/") is True


def test_google_signin_url_is_not_homepage():
    assert _is_on_notebooklm_homepage("https://accounts.google.com/signin") is False


def test_notebooklm_login_interstitial_is_not_homepage():
    """NotebookLM serves a brief ``/login`` interstitial before bouncing to
    Google -- it is on the right host but the user is NOT signed in yet."""
    assert _is_on_notebooklm_homepage("https://notebooklm.google.com/login") is False


def test_empty_url_is_not_homepage():
    assert _is_on_notebooklm_homepage("") is False


# ---------------------------------------------------------------------------
# _browser_profile_dir
# ---------------------------------------------------------------------------

def test_browser_profile_dir_uses_sdk_helper(tmp_path, monkeypatch):
    from notebooklm.cli import session as nlm_session

    profile = tmp_path / "sdk_profile"
    monkeypatch.setattr(nlm_session, "get_browser_profile_dir", lambda: profile)

    assert _browser_profile_dir() == profile


def test_browser_profile_dir_falls_back_when_helper_unavailable(monkeypatch):
    """If the SDK helper raises, fall back to the documented default path
    under ``~/.notebooklm`` rather than crashing the login."""
    from notebooklm.cli import session as nlm_session

    def _boom():
        raise RuntimeError("SDK changed")

    monkeypatch.setattr(nlm_session, "get_browser_profile_dir", _boom)

    result = _browser_profile_dir()

    assert result == Path.home() / ".notebooklm" / "profiles" / "default" / "browser_profile"


# ---------------------------------------------------------------------------
# _login_with_auto_detect -- integration with a mocked browser
# ---------------------------------------------------------------------------

def test_reaching_homepage_saves_session(tmp_path, monkeypatch):
    """The user signs in: page.url moves off accounts.google.com onto the
    NotebookLM host. After it holds there for the required consecutive
    polls, storage_state is captured and rc is 0."""
    state_file = tmp_path / "state.json"
    monkeypatch.setattr(auth, "_browser_profile_dir", lambda: tmp_path / "profile")

    # poll 1: still on Google sign-in. polls 2-4: on the NotebookLM host
    # (3 consecutive -> stable threshold met -> save).
    page = _FakePage([
        "https://accounts.google.com/signin",
        "https://notebooklm.google.com/",
        "https://notebooklm.google.com/",
        "https://notebooklm.google.com/",
    ])
    context = _FakeContext(page)
    chromium = _FakeChromium(context)
    fake = _install_fake_playwright(monkeypatch, chromium)

    rc = _login_with_auto_detect(state_file, wait_timeout=30)

    assert rc == 0
    assert context.storage_saved_to == str(state_file)
    assert state_file.exists()
    assert context.closed is True
    # The driver is always torn down on the way out.
    assert fake.stopped is True
    # The post-login double-navigation forces .google.com regional cookies.
    assert "https://accounts.google.com/" in page.goto_calls
    assert page.goto_calls.count("https://notebooklm.google.com/") >= 1


def test_transient_homepage_flash_does_not_trigger_premature_save(tmp_path, monkeypatch):
    """A single mid-redirect flash onto the NotebookLM host must NOT fire a
    save -- the URL has to hold for the consecutive-poll threshold. Here it
    flashes once, drops back to Google, and never stabilises -> timeout."""
    state_file = tmp_path / "state.json"
    monkeypatch.setattr(auth, "_browser_profile_dir", lambda: tmp_path / "profile")

    page = _FakePage([
        "https://notebooklm.google.com/",        # flash
        "https://accounts.google.com/signin",    # back to sign-in
        "https://accounts.google.com/signin",
    ])
    context = _FakeContext(page)
    _install_fake_playwright(monkeypatch, _FakeChromium(context))

    # Mocked clock: first call sets the deadline, later calls blow past it.
    clock = iter([1000.0, 1000.5, 1001.0])
    monkeypatch.setattr(auth.time, "monotonic", lambda: next(clock, 9_999.0))

    rc = _login_with_auto_detect(state_file, wait_timeout=5)

    assert rc == 124
    assert context.storage_saved_to is None
    assert not state_file.exists()
    assert context.closed is True


def test_timeout_is_fail_closed(tmp_path, monkeypatch):
    """The user never finishes signing in -> deadline expires -> context
    closed, rc 124, nothing saved."""
    state_file = tmp_path / "state.json"
    monkeypatch.setattr(auth, "_browser_profile_dir", lambda: tmp_path / "profile")

    page = _FakePage(["https://accounts.google.com/signin"])
    context = _FakeContext(page)
    _install_fake_playwright(monkeypatch, _FakeChromium(context))

    clock = iter([1000.0, 2000.0])
    monkeypatch.setattr(auth.time, "monotonic", lambda: next(clock, 9_999.0))

    rc = _login_with_auto_detect(state_file, wait_timeout=30)

    assert rc == 124
    assert context.storage_saved_to is None
    assert context.closed is True


def test_browser_launch_error_returns_one_and_does_not_raise(tmp_path, monkeypatch):
    """A browser-launch failure is reported and surfaces as rc 1 -- the
    function never raises into the CLI, and the driver is still stopped."""
    state_file = tmp_path / "state.json"
    monkeypatch.setattr(auth, "_browser_profile_dir", lambda: tmp_path / "profile")

    chromium = _FakeChromium(None, launch_error=RuntimeError("chromium missing"))
    fake = _install_fake_playwright(monkeypatch, chromium)

    rc = _login_with_auto_detect(state_file, wait_timeout=30)

    assert rc == 1
    assert not state_file.exists()
    assert fake.stopped is True


def test_driver_start_failure_returns_one_and_does_not_raise(tmp_path, monkeypatch):
    """If the Playwright driver itself fails to start (``sync_playwright().
    start()`` raises), the failure is caught and surfaced as rc 1 rather
    than propagating into the CLI."""
    import playwright.sync_api as pw_api

    state_file = tmp_path / "state.json"
    monkeypatch.setattr(auth, "_browser_profile_dir", lambda: tmp_path / "profile")

    class _BrokenPlaywright:
        def start(self):
            raise RuntimeError("playwright driver did not start")

        def stop(self):  # pragma: no cover - never reached (start failed)
            pass

    monkeypatch.setattr(pw_api, "sync_playwright", lambda: _BrokenPlaywright())

    rc = _login_with_auto_detect(state_file, wait_timeout=30)

    assert rc == 1
    assert not state_file.exists()


def test_dispatch_routes_to_auto_detect_when_flag_set(tmp_path, monkeypatch):
    """``login_nlm(auto_detect=True, ...)`` must dispatch to
    ``_login_with_auto_detect`` (with the new 2-arg signature), not to
    ``_login_with_wait_file`` or a plain ``subprocess.run``."""
    import subprocess

    called = {"wait_file": False, "auto_detect": False, "run": False}
    captured: dict = {}

    def fake_run(*a, **k):
        called["run"] = True
        return subprocess.CompletedProcess(args=a, returncode=0)

    def fake_wait_file(*a, **k):
        called["wait_file"] = True
        return 0

    def fake_auto_detect(state_file, wait_timeout):
        called["auto_detect"] = True
        captured["args"] = (state_file, wait_timeout)
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
        wait_timeout=600,
    )

    assert rc == 0
    assert called["auto_detect"] is True
    assert called["wait_file"] is False
    assert called["run"] is False
    # Dispatched with the storage-state target and the timeout, no `cmd`.
    assert captured["args"] == (state, 600)
