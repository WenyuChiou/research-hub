from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace


def test_completion_banner_includes_install_step(monkeypatch, capsys, tmp_path):
    from research_hub import init_wizard

    monkeypatch.setattr(
        "research_hub.setup_command.detect_host",
        lambda: "codex",
    )
    monkeypatch.setattr(
        "research_hub.skill_installer.list_platforms",
        lambda: [("codex", "Codex", False)],
    )

    init_wizard._print_completion_banner(tmp_path / "vault", tmp_path / "config.json", persona="researcher")
    output = capsys.readouterr().out
    assert "research-hub install --platform codex" in output


def test_mandatory_nlm_login_when_chrome_ok_and_researcher_persona(tmp_path, monkeypatch):
    from research_hub import init_wizard

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    calls: list[str] = []
    monkeypatch.setattr(init_wizard.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(
        init_wizard.platformdirs,
        "user_config_dir",
        lambda *args, **kwargs: str(config_dir),
    )
    monkeypatch.setattr(
        "requests.head",
        lambda *args, **kwargs: SimpleNamespace(status_code=200),
    )
    monkeypatch.setattr(
        "research_hub.init_wizard._check_first_run_readiness",
        lambda *args, **kwargs: [("chrome", "OK", "ready")],
    )
    monkeypatch.setattr(
        "research_hub.setup_command.run_notebooklm_login",
        lambda: calls.append("login") or 0,
    )
    monkeypatch.setattr(
        "research_hub.skill_installer.list_platforms",
        lambda: [("claude-code", "Claude Code", True)],
    )

    rc = init_wizard.run_init(
        vault_root=str(tmp_path / "vault"),
        persona="researcher",
        zotero_key="key",
        zotero_library_id="123",
    )

    assert rc == 0
    assert calls == ["login"]


def test_zotero_retry_is_single_attempt(tmp_path, monkeypatch, capsys):
    from research_hub import init_wizard

    config_dir = tmp_path / "config"
    prompts: list[str] = []
    answers = iter(
        [
            "y",
            "1",
            str(tmp_path / "vault"),
            "bad-key",
            "111",
            "y",
            "still-bad",
            "222",
            "n",
        ]
    )
    statuses = iter([403, 403])

    monkeypatch.setattr(init_wizard.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(
        init_wizard.platformdirs,
        "user_config_dir",
        lambda *args, **kwargs: str(config_dir),
    )
    monkeypatch.setattr("builtins.input", lambda prompt="": prompts.append(prompt) or next(answers))
    monkeypatch.setattr("requests.head", lambda *args, **kwargs: SimpleNamespace(status_code=next(statuses)))
    monkeypatch.setattr(
        "research_hub.init_wizard._check_first_run_readiness",
        lambda *args, **kwargs: [("chrome", "WARN", "no chrome")],
    )

    assert init_wizard.run_init() == 0

    output = capsys.readouterr().out
    assert "WARN still 403; continuing offline." in output
    assert prompts.count("    Retry Zotero validation? [y/N]: ") == 1
    assert "    Re-enter Zotero API key: " in prompts
    assert "    Re-enter Zotero library ID: " in prompts
