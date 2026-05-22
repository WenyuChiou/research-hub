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

import sys
import types
from pathlib import Path

import pytest

import research_hub.notebooklm.auth as auth
from research_hub.notebooklm.auth import (
    _browser_profile_dir,
    _context_has_google_session,
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
    """A browser context. *signed_in* controls whether ``cookies()`` reports
    a Google master session cookie -- the signal the auto-detect loop pairs
    with the page URL. Default True so existing success-path tests capture a
    session; set False to simulate an unauthenticated tab."""

    def __init__(self, page: _FakePage, *, signed_in: bool = True):
        self.pages = [page]
        self.storage_saved_to: str | None = None
        self.closed = False
        self._signed_in = signed_in

    def new_page(self):
        return self.pages[0]

    def cookies(self):
        if self._signed_in:
            return [
                {"name": "SID", "value": "x", "domain": ".google.com"},
                {"name": "__Secure-1PSID", "value": "y", "domain": ".google.com"},
            ]
        # Anonymous tab: notebooklm.google.com sets only analytics cookies.
        return [{"name": "_ga", "value": "z", "domain": ".notebooklm.google.com"}]

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


class _FakePlaywrightError(Exception):
    """Stand-in for ``playwright.sync_api.Error`` -- the real playwright
    package is an optional dependency and is not installed in CI."""


def _inject_playwright_module(monkeypatch, sync_playwright_factory):
    """Inject a fake ``playwright.sync_api`` module into ``sys.modules``.

    The function under test does ``from playwright.sync_api import
    sync_playwright`` / ``import Error`` at call time. playwright is an
    optional dependency (absent in CI), so we synthesise the module rather
    than patching an attribute on a package that may not be importable.
    """
    fake_api = types.ModuleType("playwright.sync_api")
    fake_api.sync_playwright = sync_playwright_factory
    fake_api.Error = _FakePlaywrightError
    pkg = sys.modules.get("playwright") or types.ModuleType("playwright")
    monkeypatch.setitem(sys.modules, "playwright", pkg)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_api)


def _install_fake_playwright(monkeypatch, chromium: _FakeChromium) -> _FakePlaywright:
    """Install a fake ``playwright.sync_api`` whose ``sync_playwright()``
    yields a browser stack wrapping *chromium*. Returns the playwright
    handle so tests can assert ``stop()`` was called on it."""
    fake = _FakeSyncPlaywright(chromium)
    _inject_playwright_module(monkeypatch, lambda: fake)
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
# _context_has_google_session -- the signed-in signal
# ---------------------------------------------------------------------------

class _CookieCtx:
    def __init__(self, cookies, *, raises=False):
        self._cookies = cookies
        self._raises = raises

    def cookies(self):
        if self._raises:
            raise RuntimeError("context busy")
        return self._cookies


def test_session_cookie_present_is_signed_in():
    ctx = _CookieCtx([{"name": "SID", "value": "x"}, {"name": "_ga", "value": "y"}])
    assert _context_has_google_session(ctx) is True


def test_no_session_cookie_is_not_signed_in():
    """An anonymous notebooklm.google.com tab carries only analytics
    cookies -- no Google master session cookie."""
    ctx = _CookieCtx([{"name": "_ga", "value": "y"}, {"name": "_gcl_au", "value": "z"}])
    assert _context_has_google_session(ctx) is False


def test_cookie_read_error_is_not_signed_in():
    """A busy/navigating context that errors on cookies() is treated as
    not-yet-signed-in so the loop simply polls again."""
    assert _context_has_google_session(_CookieCtx([], raises=True)) is False


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


def test_anonymous_tab_on_notebooklm_host_does_not_save(tmp_path, monkeypatch):
    """Regression: a fresh anonymous tab sits on notebooklm.google.com for a
    moment before redirecting to the sign-in page. The URL check alone
    matched it and the pre-fix auto-detect saved a 3-cookie unauthenticated
    session. Now the loop also requires a Google session cookie -- with
    none present the save must NOT fire even though the URL looks right."""
    state_file = tmp_path / "state.json"
    monkeypatch.setattr(auth, "_browser_profile_dir", lambda: tmp_path / "profile")

    # URL is on the NotebookLM host the whole time ...
    page = _FakePage(["https://notebooklm.google.com/"])
    # ... but the context has NO Google session cookie (not signed in).
    context = _FakeContext(page, signed_in=False)
    _install_fake_playwright(monkeypatch, _FakeChromium(context))

    # Clock lets the poll loop run several real iterations -- so the
    # session-cookie check actually executes (and returns False) each
    # pass -- before the deadline trips. (deadline = 1000 + 30 = 1030.)
    clock = iter([1000.0, 1001.0, 1002.0, 1003.0, 1004.0, 2000.0])
    monkeypatch.setattr(auth.time, "monotonic", lambda: next(clock, 9_999.0))

    rc = _login_with_auto_detect(state_file, wait_timeout=30)

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
    state_file = tmp_path / "state.json"
    monkeypatch.setattr(auth, "_browser_profile_dir", lambda: tmp_path / "profile")

    class _BrokenPlaywright:
        def start(self):
            raise RuntimeError("playwright driver did not start")

        def stop(self):  # pragma: no cover - never reached (start failed)
            pass

    _inject_playwright_module(monkeypatch, lambda: _BrokenPlaywright())

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
