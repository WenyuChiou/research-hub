from __future__ import annotations

import sys
from types import SimpleNamespace


def _args(**overrides):
    base = dict(
        vault="C:/vault",
        persona="researcher",
        skip_install=True,
        skip_login=True,
        skip_sample=False,
        no_browser=False,
        platform=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_setup_prompts_for_sample_run_by_default(monkeypatch, capsys):
    from research_hub import setup_command

    prompts: list[str] = []
    auto_calls: list[dict] = []
    dashboard_calls: list[bool] = []

    monkeypatch.setattr("research_hub.init_wizard.run_init", lambda **kwargs: 0)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": prompts.append(prompt) or "n")
    monkeypatch.setattr("research_hub.auto.auto_pipeline", lambda **kwargs: auto_calls.append(kwargs))
    monkeypatch.setattr(
        "research_hub.dashboard.generate_dashboard",
        lambda **kwargs: dashboard_calls.append(kwargs.get("open_browser", False)),
    )

    assert setup_command.run_setup(_args()) == 0
    assert prompts == ["  Try a sample now? [Y/n] "]
    assert auto_calls == []
    assert dashboard_calls == []
    assert "Want to try a sample research topic?" in capsys.readouterr().out


def test_setup_skip_sample_flag_skips_prompt(monkeypatch):
    from research_hub import setup_command

    prompts: list[str] = []
    auto_calls: list[dict] = []

    monkeypatch.setattr("research_hub.init_wizard.run_init", lambda **kwargs: 0)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": prompts.append(prompt) or "n")
    monkeypatch.setattr("research_hub.auto.auto_pipeline", lambda **kwargs: auto_calls.append(kwargs))

    assert setup_command.run_setup(_args(skip_sample=True)) == 0
    assert prompts == []
    assert auto_calls == []


def test_setup_analyst_persona_skips_sample_branch(monkeypatch):
    from research_hub import setup_command

    prompts: list[str] = []
    auto_calls: list[dict] = []

    monkeypatch.setattr("research_hub.init_wizard.run_init", lambda **kwargs: 0)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": prompts.append(prompt) or "n")
    monkeypatch.setattr("research_hub.auto.auto_pipeline", lambda **kwargs: auto_calls.append(kwargs))

    assert setup_command.run_setup(_args(persona="analyst")) == 0
    assert prompts == []
    assert auto_calls == []


def test_setup_keyboard_interrupt_during_sample_handled(monkeypatch):
    from research_hub import setup_command

    monkeypatch.setattr("research_hub.init_wizard.run_init", lambda **kwargs: 0)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": (_ for _ in ()).throw(KeyboardInterrupt()))
    monkeypatch.setattr("research_hub.auto.auto_pipeline", lambda **kwargs: (_ for _ in ()).throw(AssertionError()))

    assert setup_command.run_setup(_args()) == 0
