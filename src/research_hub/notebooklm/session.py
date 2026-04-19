"""Back-compat shim replaced by browser.py in v0.42."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from research_hub.notebooklm.browser import (
    LaunchConfig,
    default_state_file,
    launch_nlm_context,
    login_nlm,
)


@contextmanager
def open_cdp_session(
    user_data_dir: Path,
    *,
    headless: bool = True,
    chrome_binary: str | None = None,
) -> Iterator[tuple[object, object]]:
    """Back-compat shim delegating to launch_nlm_context."""
    del chrome_binary
    state_file = default_state_file(user_data_dir.parent.parent)
    with launch_nlm_context(
        user_data_dir=user_data_dir,
        headless=headless,
        state_file=state_file,
    ) as (ctx, page):
        yield ctx, page


SessionConfig = LaunchConfig


class PlaywrightSession:
    """Back-compat wrapper around launch_nlm_context."""

    def __init__(self, config: SessionConfig) -> None:
        self.config = config

    @contextmanager
    def open(self) -> Iterator[tuple[object, object]]:
        state_file = self.config.state_file or default_state_file(self.config.user_data_dir.parent.parent)
        with launch_nlm_context(
            user_data_dir=self.config.user_data_dir,
            headless=self.config.headless,
            state_file=state_file,
            extra_args=self.config.extra_args,
        ) as (ctx, page):
            yield ctx, page


def login_interactive_cdp(
    user_data_dir: Path,
    *,
    timeout_sec: int = 300,
    stable_hold_sec: int = 5,
    chrome_binary: str | None = None,
    keep_open: bool = False,
) -> int:
    """Back-compat shim delegating to login_nlm."""
    del chrome_binary, keep_open
    state_file = default_state_file(user_data_dir.parent.parent)
    return login_nlm(
        user_data_dir=user_data_dir,
        state_file=state_file,
        timeout_sec=timeout_sec,
        stable_hold_sec=stable_hold_sec,
    )


def login_interactive(
    user_data_dir: Path,
    *,
    use_system_chrome: bool = False,
    timeout_sec: int = 300,
    stable_hold_sec: int = 5,
    from_chrome_profile: bool = False,
    chrome_profile_path=None,
    chrome_profile_name: str = "Default",
) -> int:
    """Back-compat shim delegating to login_nlm."""
    del use_system_chrome, from_chrome_profile, chrome_profile_path, chrome_profile_name
    state_file = default_state_file(user_data_dir.parent.parent)
    return login_nlm(
        user_data_dir=user_data_dir,
        state_file=state_file,
        timeout_sec=timeout_sec,
        stable_hold_sec=stable_hold_sec,
    )
