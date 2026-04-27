from __future__ import annotations

from types import ModuleType, SimpleNamespace

import pytest

from research_hub import setup_command


@pytest.mark.parametrize(
    ("host", "env_key"),
    [
        ("claude-code", "CLAUDE_CODE_SESSION"),
        ("cursor", "CURSOR_SESSION"),
        ("codex", "CODEX_CLI_SESSION"),
        ("gemini", "GEMINI_CLI_SESSION"),
    ],
)
def test_detect_host_returns_each_known_platform(monkeypatch, host: str, env_key: str):
    for _host, keys in setup_command.DETECT_HOSTS:
        for key in keys:
            monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("RH_HOST", raising=False)
    monkeypatch.setenv(env_key, "1")

    assert setup_command.detect_host() == host


def test_detect_host_env_override_priority(monkeypatch):
    monkeypatch.setenv("RH_HOST", "codex")
    monkeypatch.setenv("CLAUDE_CODE_SESSION", "1")

    assert setup_command.detect_host() == "codex"


def test_detect_host_returns_none_when_no_signal(monkeypatch):
    monkeypatch.delenv("RH_HOST", raising=False)
    for _host, keys in setup_command.DETECT_HOSTS:
        for key in keys:
            monkeypatch.delenv(key, raising=False)

    assert setup_command.detect_host() is None


def test_run_setup_persona_fallback_when_config_read_fails(monkeypatch):
    init_module = ModuleType("research_hub.init_wizard")
    init_module.run_init = lambda **_kwargs: 0
    cli_module = ModuleType("research_hub.cli")
    cli_module._cmd_install = lambda _args: 0
    config_module = ModuleType("research_hub.config")
    config_module.get_config = lambda: (_ for _ in ()).throw(RuntimeError("broken config"))
    monkeypatch.setitem(__import__("sys").modules, "research_hub.init_wizard", init_module)
    monkeypatch.setitem(__import__("sys").modules, "research_hub.cli", cli_module)
    monkeypatch.setitem(__import__("sys").modules, "research_hub.config", config_module)
    calls: list[str] = []
    monkeypatch.setattr(setup_command, "run_notebooklm_login", lambda: calls.append("login") or 0)

    args = SimpleNamespace(
        vault="C:/vault",
        persona="",
        skip_install=True,
        skip_login=False,
        skip_sample=True,
        platform=None,
        no_browser=True,
    )

    assert setup_command.run_setup(args) == 0
    # v0.68.4: with persona="" the setup is interactive (vault+persona
    # bound check fails), so the new guard skips the second login launch
    # — run_init is responsible for it in interactive mode. Previously
    # this assertion was calls==["login"] because the unconditional
    # second launch was the bug being fixed (PR #11).
    assert calls == []


def test_run_setup_sample_run_keyboard_interrupt_handled(monkeypatch, capsys):
    init_module = ModuleType("research_hub.init_wizard")
    init_module.run_init = lambda **_kwargs: 0
    cli_module = ModuleType("research_hub.cli")
    cli_module._cmd_install = lambda _args: 0
    auto_module = ModuleType("research_hub.auto")

    def _raise_keyboard_interrupt(**_kwargs):
        raise KeyboardInterrupt

    auto_module.auto_pipeline = _raise_keyboard_interrupt
    monkeypatch.setitem(__import__("sys").modules, "research_hub.init_wizard", init_module)
    monkeypatch.setitem(__import__("sys").modules, "research_hub.cli", cli_module)
    monkeypatch.setitem(__import__("sys").modules, "research_hub.auto", auto_module)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    answers = iter(["y", "agent-based systems"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))

    args = SimpleNamespace(
        vault="C:/vault",
        persona="researcher",
        skip_install=True,
        skip_login=True,
        skip_sample=False,
        platform=None,
        no_browser=True,
    )

    assert setup_command.run_setup(args) == 0
    out = capsys.readouterr().out
    assert "Sample run cancelled" in out
