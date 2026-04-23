from __future__ import annotations

from types import SimpleNamespace


def test_setup_runs_init_then_install_then_login(monkeypatch):
    from research_hub import setup_command

    calls: list[str] = []
    monkeypatch.setattr(
        "research_hub.init_wizard.run_init",
        lambda **kwargs: calls.append("init") or 0,
    )
    monkeypatch.setattr(
        "research_hub.cli._cmd_install",
        lambda args: calls.append(f"install:{args.platform}") or 0,
    )
    monkeypatch.setattr(
        setup_command,
        "run_notebooklm_login",
        lambda: calls.append("login") or 0,
    )

    args = SimpleNamespace(
        vault="C:/vault",
        persona="researcher",
        skip_install=False,
        skip_login=False,
        platform="codex",
    )
    assert setup_command.run_setup(args) == 0
    assert calls == ["init", "install:codex", "login"]


def test_setup_skip_install_and_skip_login(monkeypatch):
    from research_hub import setup_command

    calls: list[str] = []
    monkeypatch.setattr(
        "research_hub.init_wizard.run_init",
        lambda **kwargs: calls.append("init") or 0,
    )
    monkeypatch.setattr(
        "research_hub.cli._cmd_install",
        lambda args: calls.append("install") or 0,
    )
    monkeypatch.setattr(
        setup_command,
        "run_notebooklm_login",
        lambda: calls.append("login") or 0,
    )

    args = SimpleNamespace(
        vault="C:/vault",
        persona="researcher",
        skip_install=True,
        skip_login=True,
        platform=None,
    )
    assert setup_command.run_setup(args) == 0
    assert calls == ["init"]


def test_detect_host_from_env(monkeypatch):
    from research_hub.setup_command import detect_host

    monkeypatch.setenv("RH_HOST", "cursor")
    assert detect_host() == "cursor"
