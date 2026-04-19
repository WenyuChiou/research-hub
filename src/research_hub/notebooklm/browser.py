"""Patchright-based NotebookLM browser launcher.

Adapted from PleasePrompto/notebooklm-skill (MIT):
https://github.com/PleasePrompto/notebooklm-skill

Replaces the old cdp_launcher.py + session.py modules. Uses persistent
Chrome context with anti-automation flags, honors the cookie replay
workaround for Playwright bug #36139, and exposes ``launch_nlm_context``.
"""

from __future__ import annotations

import json
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from patchright.sync_api import BrowserContext, Page, sync_playwright

from research_hub.notebooklm.selectors import NAV_TIMEOUT_MS, NOTEBOOKLM_HOME

_DEFAULT_LAUNCH_ARGS = (
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage",
    "--no-sandbox",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-features=GlobalMediaControls",
    "--disable-sync",
)

_IGNORE_DEFAULT_ARGS = ("--enable-automation",)

_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


@dataclass
class LaunchConfig:
    user_data_dir: Path
    headless: bool = False
    state_file: Path | None = None
    user_agent: str = _DEFAULT_USER_AGENT
    extra_args: tuple[str, ...] = ()
    viewport_width: int = 1400
    viewport_height: int = 900


def save_auth_state(context: BrowserContext, state_file: Path) -> None:
    """Persist cookies + localStorage to ``state_file`` for later replay."""
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state = context.storage_state()
    state_file.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _load_auth_state(context: BrowserContext, state_file: Path) -> bool:
    """Inject cookies from ``state_file`` into ``context`` if present."""
    if not state_file.exists():
        return False
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        return False
    cookies = state.get("cookies", [])
    if cookies:
        try:
            context.add_cookies(cookies)
            return True
        except Exception:
            return False
    return False


@contextmanager
def launch_nlm_context(
    *,
    user_data_dir: Path,
    headless: bool = False,
    state_file: Path | None = None,
    extra_args: tuple[str, ...] = (),
) -> Iterator[tuple[BrowserContext, Page]]:
    """Yield ``(context, page)`` for NotebookLM automation."""
    user_data_dir.mkdir(parents=True, exist_ok=True)
    args = list(_DEFAULT_LAUNCH_ARGS) + list(extra_args)

    playwright = sync_playwright().start()
    context: BrowserContext | None = None
    try:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            channel="chrome",
            headless=headless,
            args=args,
            ignore_default_args=list(_IGNORE_DEFAULT_ARGS),
            user_agent=_DEFAULT_USER_AGENT,
            viewport={"width": 1400, "height": 900},
            accept_downloads=True,
        )
        context.set_default_navigation_timeout(NAV_TIMEOUT_MS)
        context.set_default_timeout(NAV_TIMEOUT_MS)

        if state_file is not None:
            _load_auth_state(context, state_file)

        page = context.pages[0] if context.pages else context.new_page()
        page.goto(NOTEBOOKLM_HOME)
        yield context, page
    finally:
        if context is not None:
            try:
                if state_file is not None:
                    try:
                        save_auth_state(context, state_file)
                    except Exception:
                        pass
                context.close()
            except Exception:
                pass
        try:
            playwright.stop()
        except Exception:
            pass


def default_session_dir(research_hub_dir: Path) -> Path:
    """Return ``<vault>/.research_hub/nlm_sessions/default/``."""
    return research_hub_dir / "nlm_sessions" / "default"


def default_state_file(research_hub_dir: Path) -> Path:
    """Return ``<vault>/.research_hub/nlm_sessions/state.json``."""
    return research_hub_dir / "nlm_sessions" / "state.json"


def dismiss_overlay(page, *, max_escapes: int = 3) -> None:
    """Dismiss NotebookLM dialog backdrops that block page interaction."""
    for _ in range(max_escapes):
        backdrop = page.locator(".cdk-overlay-backdrop-showing").first
        try:
            if backdrop.count() == 0:
                return
        except Exception:
            return
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
        except Exception:
            return


def login_nlm(
    user_data_dir: Path,
    *,
    state_file: Path,
    timeout_sec: int = 300,
    stable_hold_sec: int = 5,
) -> int:
    """Interactive one-time Google sign-in using the new launcher."""
    print("Opening NotebookLM in a real-Chrome window for Google sign-in.")
    print("  Session dir:  {0}".format(user_data_dir))
    print("  State file:   {0}".format(state_file))
    print(
        "  Timeout:      {0}s (auto-close {1}s after login)".format(
            timeout_sec, stable_hold_sec
        )
    )
    print()
    print(">>> Sign in with your Google account.")
    print(">>> The window closes automatically when login is detected.")
    print()

    with launch_nlm_context(
        user_data_dir=user_data_dir,
        headless=False,
        state_file=state_file,
    ) as (_, page):
        start = time.time()
        stable_since: float | None = None
        last_status_url = ""
        while time.time() - start < timeout_sec:
            try:
                current_url = page.url or ""
            except Exception:
                current_url = ""
            lowered = current_url.lower()
            on_notebooklm = (
                "notebooklm.google.com" in lowered
                and "accounts.google.com" not in lowered
                and "oauth" not in lowered
                and "signin" not in lowered
            )
            if on_notebooklm:
                if stable_since is None:
                    stable_since = time.time()
                    print(
                        "  [{0}] On notebooklm.google.com - waiting {1}s for session to "
                        "stabilize...".format(_tstamp(), stable_hold_sec)
                    )
                    sys.stdout.flush()
                elif time.time() - stable_since >= stable_hold_sec:
                    print("  [{0}] Login detected. Session saved.".format(_tstamp()))
                    return 0
            else:
                if current_url and current_url != last_status_url:
                    last_status_url = current_url
                    short = current_url[:80] + ("..." if len(current_url) > 80 else "")
                    print("  [{0}] On {1}".format(_tstamp(), short))
                    sys.stdout.flush()
                stable_since = None
            time.sleep(1)
    print("  [{0}] Login not detected after {1}s.".format(_tstamp(), timeout_sec))
    return 1


def _tstamp() -> str:
    return time.strftime("%H:%M:%S")
