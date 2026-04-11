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


def login_interactive(
    user_data_dir: Path,
    *,
    use_system_chrome: bool = False,
    timeout_sec: int = 300,
    stable_hold_sec: int = 5,
) -> int:
    """Open NotebookLM in a visible browser and auto-detect login completion.

    Polls the page URL every second. When it lands on
    ``notebooklm.google.com`` and stays there for ``stable_hold_sec``
    consecutive seconds (away from any ``accounts.google.com`` or
    ``oauth`` redirect), the session is considered saved and the
    browser closes automatically.

    ``use_system_chrome=True`` launches Playwright with ``channel="chrome"``
    so it uses the installed Chrome binary (better Google login UX than
    bare Chromium). The user data directory is still isolated under
    ``<vault>/.research_hub/nlm_sessions/`` — Chrome profile reuse is
    NOT enabled here, which keeps it from conflicting with a running
    Chrome or corrupting the user's real profile. Full profile reuse is
    deferred to a later release.

    Returns 0 on success, 1 on timeout.
    """
    print("Opening NotebookLM in a visible browser window...")
    print(f"  Session dir:  {user_data_dir}")
    print(f"  Chrome channel: {'system-chrome' if use_system_chrome else 'bundled-chromium'}")
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
