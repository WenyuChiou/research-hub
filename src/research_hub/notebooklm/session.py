"""Playwright session manager with persistent context for Google auth."""

from __future__ import annotations

import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from research_hub.notebooklm.selectors import NAV_TIMEOUT_MS, NOTEBOOKLM_HOME


@dataclass
class SessionConfig:
    user_data_dir: Path
    headless: bool = True
    chromium_args: tuple[str, ...] = ()
    viewport_width: int = 1400
    viewport_height: int = 900
    use_system_chrome: bool = False


class PlaywrightSession:
    """Wrap Playwright's persistent context in a reusable context manager."""

    def __init__(self, config: SessionConfig) -> None:
        self.config = config
        self._playwright = None
        self._context = None

    @contextmanager
    def open(self) -> Iterator[tuple[object, object]]:
        """Yield `(context, page)` and close both on exit."""
        from playwright.sync_api import sync_playwright

        self.config.user_data_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = sync_playwright().start()
        try:
            launch_kwargs: dict[str, object] = {
                "user_data_dir": str(self.config.user_data_dir),
                "headless": self.config.headless,
                "args": list(self.config.chromium_args),
                "viewport": {
                    "width": self.config.viewport_width,
                    "height": self.config.viewport_height,
                },
                "accept_downloads": True,
            }
            if self.config.use_system_chrome:
                launch_kwargs["channel"] = "chrome"
            self._context = self._playwright.chromium.launch_persistent_context(**launch_kwargs)
            self._context.set_default_navigation_timeout(NAV_TIMEOUT_MS)
            self._context.set_default_timeout(NAV_TIMEOUT_MS)
            page = self._context.pages[0] if self._context.pages else self._context.new_page()
            yield self._context, page
        finally:
            if self._context is not None:
                try:
                    self._context.close()
                except Exception:
                    pass
            if self._playwright is not None:
                try:
                    self._playwright.stop()
                except Exception:
                    pass


def login_interactive_cdp(
    user_data_dir: Path,
    *,
    timeout_sec: int = 300,
    stable_hold_sec: int = 5,
    chrome_binary: str | None = None,
) -> int:
    """CDP-attach login flow that bypasses Google's Playwright bot detection.

    Instead of letting Playwright launch Chrome (which sets
    ``navigator.webdriver = true`` and similar automation fingerprints
    that Google's sign-in flow detects), we launch Chrome ourselves as
    a normal subprocess with ``--remote-debugging-port`` and have
    Playwright ``connect_over_cdp`` to the running instance. Chrome
    itself never knows it is being automated — it is just a regular
    Chrome window that happens to have a DevTools endpoint open — so
    Google's bot check never fires.

    The isolated ``user_data_dir`` persists cookies across runs, so
    after the one-time interactive sign-in here, subsequent
    ``research-hub notebooklm upload`` runs can attach headless and
    reuse the session.
    """
    from research_hub.notebooklm.cdp_launcher import (
        find_chrome_binary,
        launch_chrome_with_cdp,
        stop_cdp,
    )

    binary = chrome_binary or find_chrome_binary()
    if binary is None:
        print("  [ERR] Could not find Chrome binary on this system.")
        print("  [ERR] Install Chrome, or pass --chrome-binary <path>.")
        return 1

    print("Launching Chrome with CDP remote debugging enabled...")
    print(f"  Chrome binary: {binary}")
    print(f"  Session dir:   {user_data_dir}")
    print(f"  Mode:          cdp-attach (no Playwright automation fingerprint)")
    print(f"  Timeout:       {timeout_sec}s  (will auto-close {stable_hold_sec}s after login)")
    print()
    print(">>> Sign in with your Google account in the opened Chrome.")
    print(">>> The window will close AUTOMATICALLY when login is detected.")
    print(">>> (Press Ctrl+C in this terminal if you need to abort.)")
    print()

    endpoint = launch_chrome_with_cdp(
        user_data_dir=user_data_dir,
        chrome_binary=binary,
        headless=False,
        startup_url=NOTEBOOKLM_HOME,
    )
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(endpoint.cdp_url)
            try:
                contexts = browser.contexts
                if not contexts:
                    print("  [ERR] CDP-attached Chrome has no browser context yet.")
                    return 1
                context = contexts[0]
                pages = context.pages
                page = pages[0] if pages else context.new_page()

                start = time.time()
                stable_since: float | None = None
                last_status_url = ""
                while time.time() - start < timeout_sec:
                    try:
                        current_url = page.url
                    except Exception:
                        current_url = ""

                    on_notebooklm = (
                        "notebooklm.google.com" in current_url
                        and "accounts.google.com" not in current_url
                        and "oauth" not in current_url.lower()
                        and "signin" not in current_url.lower()
                    )

                    if on_notebooklm:
                        if stable_since is None:
                            stable_since = time.time()
                            print(
                                f"  [{_tstamp()}] On notebooklm.google.com — "
                                f"waiting {stable_hold_sec}s for session to stabilize..."
                            )
                            sys.stdout.flush()
                        elif time.time() - stable_since >= stable_hold_sec:
                            print(f"  [{_tstamp()}] Login detected. Session saved.")
                            return 0
                    else:
                        if current_url and current_url != last_status_url:
                            last_status_url = current_url
                            short = current_url[:80] + ("..." if len(current_url) > 80 else "")
                            print(f"  [{_tstamp()}] On {short}")
                            sys.stdout.flush()
                        stable_since = None

                    time.sleep(1)

                print(f"  [{_tstamp()}] Login not detected after {timeout_sec}s.")
                return 1
            finally:
                try:
                    browser.close()
                except Exception:
                    pass
    finally:
        stop_cdp(endpoint)


def login_interactive(
    user_data_dir: Path,
    *,
    use_system_chrome: bool = False,
    timeout_sec: int = 300,
    stable_hold_sec: int = 5,
    from_chrome_profile: bool = False,
    chrome_profile_path: Path | None = None,
    chrome_profile_name: str = "Default",
) -> int:
    """Open NotebookLM in a visible browser and auto-detect login completion.

    Polls the page URL every second. When it lands on
    ``notebooklm.google.com`` and stays there for ``stable_hold_sec``
    consecutive seconds (away from any ``accounts.google.com`` or
    ``oauth`` redirect), the session is considered saved and the
    browser closes automatically.

    Three modes:

    - ``from_chrome_profile=True`` (recommended when Google blocks
      Playwright with "browser may have security concerns"). Clones
      the user's real Chrome profile from
      ``<LOCALAPPDATA>/Google/Chrome/User Data`` into
      ``user_data_dir`` and launches Playwright with it. Google sees
      the same auth cookies it issued to the real Chrome session and
      does not block. Chrome MUST be closed before running. Forces
      ``channel="chrome"``.

    - ``use_system_chrome=True`` launches Playwright with
      ``channel="chrome"`` (installed Chrome binary) but an isolated
      profile. Works if Google is not currently blocking Playwright;
      no profile mutation risk. First-run requires manual sign-in.

    - Default: launches bundled Chromium with isolated profile.
      Lightest-weight but most likely to hit Google's bot check on
      fresh logins.

    Returns 0 on success, 1 on timeout or setup failure.
    """
    if from_chrome_profile:
        from research_hub.notebooklm.chrome_clone import (
            clone_chrome_profile,
            default_chrome_user_data_dir,
        )

        src = chrome_profile_path or default_chrome_user_data_dir()
        if src is None:
            print("  [ERR] Could not find Chrome user data dir.")
            print("  [ERR] Set --chrome-profile-path to the directory containing 'Default'.")
            return 1
        print(f"  Cloning Chrome profile from: {src}")
        print(f"  (profile: {chrome_profile_name} — Chrome must be fully closed)")
        try:
            clone_chrome_profile(src, user_data_dir, profile_name=chrome_profile_name)
        except RuntimeError as exc:
            print(f"  [ERR] {exc}")
            return 1
        except FileNotFoundError as exc:
            print(f"  [ERR] {exc}")
            return 1
        print(f"  [OK] Profile cloned to {user_data_dir}")
        use_system_chrome = True  # clone requires real Chrome binary

    print("Opening NotebookLM in a visible browser window...")
    print(f"  Session dir:  {user_data_dir}")
    print(f"  Chrome channel: {'system-chrome' if use_system_chrome else 'bundled-chromium'}")
    print(f"  Mode:         {'cloned-chrome-profile' if from_chrome_profile else 'isolated-profile'}")
    print(f"  Timeout:      {timeout_sec}s  (will auto-close {stable_hold_sec}s after login)")
    print()
    print(">>> Sign in with your Google account in the opened browser.")
    print(">>> The window will close AUTOMATICALLY when login is detected.")
    print(">>> (Press Ctrl+C in this terminal if you need to abort.)")
    print()

    cfg = SessionConfig(
        user_data_dir=user_data_dir,
        headless=False,
        use_system_chrome=use_system_chrome,
    )
    session = PlaywrightSession(cfg)
    with session.open() as (_, page):
        page.goto(NOTEBOOKLM_HOME)

        start = time.time()
        stable_since: float | None = None
        last_status_url = ""
        while time.time() - start < timeout_sec:
            try:
                current_url = page.url
            except Exception:
                current_url = ""

            on_notebooklm = (
                "notebooklm.google.com" in current_url
                and "accounts.google.com" not in current_url
                and "oauth" not in current_url.lower()
                and "signin" not in current_url.lower()
            )

            if on_notebooklm:
                if stable_since is None:
                    stable_since = time.time()
                    print(f"  [{_tstamp()}] On notebooklm.google.com — waiting {stable_hold_sec}s for session to stabilize...")
                    sys.stdout.flush()
                elif time.time() - stable_since >= stable_hold_sec:
                    print(f"  [{_tstamp()}] Login detected. Session saved.")
                    return 0
            else:
                if current_url != last_status_url and current_url:
                    last_status_url = current_url
                    short = current_url[:80] + ("..." if len(current_url) > 80 else "")
                    print(f"  [{_tstamp()}] On {short}")
                    sys.stdout.flush()
                stable_since = None

            time.sleep(1)

        print(f"  [{_tstamp()}] Login not detected after {timeout_sec}s — session may be incomplete.")
        return 1


def _tstamp() -> str:
    return time.strftime("%H:%M:%S")
