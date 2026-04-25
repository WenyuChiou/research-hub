"""v0.65 Track A1: NLM login flow hardening.

Three guardrails added in v0.65:
- DOM-confirmation gate before declaring session stable
- Final timeout block prints last URL + page title + actionable hint
- save_auth_state failures now WARN instead of silently passing
"""

from __future__ import annotations

import io
import sys
from contextlib import contextmanager, redirect_stderr
from unittest.mock import MagicMock, patch

import pytest


# --- helpers ---------------------------------------------------------------


def _make_page(url: str = "https://notebooklm.google.com/", title: str = "NotebookLM",
               dom_match: bool = True):
    page = MagicMock()
    page.url = url
    page.title.return_value = title
    if dom_match:
        # query_selector returns truthy element handle
        page.query_selector.return_value = MagicMock()
    else:
        page.query_selector.return_value = None
    return page


# --- A1.a DOM-confirmation gate -------------------------------------------


def test_wait_for_logged_in_dom_returns_true_when_any_selector_matches():
    from research_hub.notebooklm.browser import _wait_for_logged_in_dom

    page = _make_page(dom_match=True)
    assert _wait_for_logged_in_dom(page) is True


def test_wait_for_logged_in_dom_returns_false_when_no_selector_matches():
    from research_hub.notebooklm.browser import _wait_for_logged_in_dom

    page = MagicMock()
    page.query_selector.return_value = None
    assert _wait_for_logged_in_dom(page) is False


def test_wait_for_logged_in_dom_tolerates_per_selector_exceptions():
    from research_hub.notebooklm.browser import _wait_for_logged_in_dom

    page = MagicMock()
    page.query_selector.side_effect = RuntimeError("flaky")
    # All selectors raise -> overall returns False, not crashes
    assert _wait_for_logged_in_dom(page) is False


# --- A1.b diagnostic timeout block ----------------------------------------


def test_login_timeout_prints_url_title_and_hint(capsys, monkeypatch):
    """When the loop times out, the final block must include the actual
    final URL, page title, and a one-line user-actionable hint pointing
    at the manual-completion path."""
    from research_hub.notebooklm import browser

    page = _make_page(
        url="https://accounts.google.com/AccountChooser",
        title="Choose an account",
        dom_match=False,
    )

    fake_ctx = MagicMock()

    @contextmanager
    def fake_launch(*, user_data_dir, headless, state_file, **_kwargs):
        yield fake_ctx, page

    monkeypatch.setattr(browser, "launch_nlm_context", fake_launch)
    # Make the loop exit fast: timeout 1s, sleep noop
    monkeypatch.setattr(browser.time, "sleep", lambda _s: None)

    rc = browser.login_nlm(
        user_data_dir=MagicMock(),
        state_file=MagicMock(),
        timeout_sec=1,
        stable_hold_sec=0,
    )
    out = capsys.readouterr().out
    assert rc == 1
    assert "Login not detected after" in out
    assert "Last URL:" in out
    assert "AccountChooser" in out
    assert "Page title:" in out
    assert "Choose an account" in out
    assert "security checkup" in out or "consent" in out


# --- A1.c save_auth_state failure now WARNs --------------------------------


def test_save_state_failure_warns_to_stderr(capsys, monkeypatch, tmp_path):
    """Previously the save error was silently swallowed in finally;
    v0.65 logs to stderr so users see partial-save problems."""
    from research_hub.notebooklm import browser

    state_file = tmp_path / "state.json"

    def _raising_save(_ctx, _path):
        raise OSError("disk full")

    monkeypatch.setattr(browser, "save_auth_state", _raising_save)

    fake_ctx = MagicMock()
    fake_page = _make_page()

    fake_pw = MagicMock()
    fake_pw.chromium.launch_persistent_context.return_value = fake_ctx
    fake_ctx.pages = [fake_page]
    fake_ctx.new_page.return_value = fake_page

    monkeypatch.setattr(
        browser, "sync_playwright", lambda: MagicMock(start=lambda: fake_pw)
    )

    captured_err = io.StringIO()
    with redirect_stderr(captured_err):
        with browser.launch_nlm_context(
            user_data_dir=tmp_path / "profile",
            state_file=state_file,
        ) as (_, _p):
            pass
    err = captured_err.getvalue()
    assert "WARN" in err
    assert "disk full" in err
