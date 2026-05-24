from __future__ import annotations

import sys

import pytest


def test_recommended_cli_invocation_uses_module_form_when_console_missing(monkeypatch):
    from research_hub._invocation import recommended_cli_invocation

    monkeypatch.setattr("research_hub._invocation.shutil.which", lambda _name: None)

    assert recommended_cli_invocation() == f"{sys.executable} -m research_hub"


def test_recommended_cli_invocation_uses_console_script_when_present(monkeypatch):
    from research_hub._invocation import recommended_cli_invocation

    monkeypatch.setattr(
        "research_hub._invocation.shutil.which",
        lambda name: "/x/research-hub" if name == "research-hub" else None,
    )

    assert recommended_cli_invocation() == "research-hub"


def test_requires_auth_refresh_uses_recommended_invocation(monkeypatch, tmp_path):
    from research_hub.errors import RequiresAuthRefresh
    from research_hub.notebooklm.auth import require_session_health

    monkeypatch.setattr("research_hub._invocation.shutil.which", lambda _name: None)

    with pytest.raises(RequiresAuthRefresh) as exc_info:
        require_session_health(tmp_path / "missing-state.json")

    command = exc_info.value.next_steps[0]
    assert "notebooklm login --auto-detect" in command
    assert not command.startswith("python -m research_hub")


def test_clean_auth_reason_removes_legacy_upstream_hint():
    from research_hub.notebooklm.auth import _clean_auth_reason

    reason = (
        "Authentication expired or invalid. "
        "Run 'notebooklm login' to re-authenticate."
    )

    assert _clean_auth_reason(reason) == "Authentication expired or invalid"
