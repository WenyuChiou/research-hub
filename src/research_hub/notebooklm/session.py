"""Playwright session manager with persistent context for Google auth."""

from __future__ import annotations

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
            self._context = self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.config.user_data_dir),
                headless=self.config.headless,
                args=list(self.config.chromium_args),
                viewport={
                    "width": self.config.viewport_width,
                    "height": self.config.viewport_height,
                },
                accept_downloads=True,
            )
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


def login_interactive(user_data_dir: Path) -> int:
    """Open NotebookLM in a visible browser and wait for the user to sign in."""
    print("Opening NotebookLM in a visible Chromium window...")
    print(f"Session will be saved at: {user_data_dir}")
    session = PlaywrightSession(SessionConfig(user_data_dir=user_data_dir, headless=False))
    with session.open() as (_, page):
        page.goto(NOTEBOOKLM_HOME)
        print()
        print(">>> Sign in with your Google account in the opened browser.")
        print(">>> When you see your notebook list (or an empty Create page),")
        print(">>> return to this terminal and press Enter to save the session.")
        input()
    print("Session saved. You can now run `research-hub notebooklm upload` headless.")
    return 0
