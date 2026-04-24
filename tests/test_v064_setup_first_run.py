"""v0.64.1: setup must be exempt from require_config so it can run on a fresh machine."""

from __future__ import annotations

import pytest


def test_setup_is_exempt_from_require_config(monkeypatch):
    """`research-hub setup` must NOT call require_config(); otherwise it can never
    serve as the first-run command on an uninitialized machine."""
    from research_hub import cli

    require_config_calls = []

    def _fake_require_config(*args, **kwargs):
        require_config_calls.append((args, kwargs))
        raise SystemExit(99)

    captured: dict = {}

    def _fake_run_setup(args):
        captured["args"] = args
        return 0

    monkeypatch.setattr("research_hub.cli.require_config", _fake_require_config)
    monkeypatch.setattr("research_hub.setup_command.run_setup", _fake_run_setup)

    rc = cli.main(["setup", "--vault", "/tmp/x", "--persona", "analyst", "--skip-install", "--skip-login", "--skip-sample"])

    assert rc == 0
    assert require_config_calls == [], "setup must not invoke require_config"
    assert "args" in captured, "setup dispatcher must reach run_setup"


def test_init_is_still_exempt_from_require_config(monkeypatch):
    """Regression guard: bumping the exempt set must not unintentionally drop init."""
    from research_hub import cli

    require_config_calls = []

    def _fake_require_config(*args, **kwargs):
        require_config_calls.append((args, kwargs))
        raise SystemExit(99)

    monkeypatch.setattr("research_hub.cli.require_config", _fake_require_config)
    monkeypatch.setattr("research_hub.init_wizard.run_init", lambda **kw: 0)

    rc = cli.main(["init", "--vault", "/tmp/x", "--non-interactive", "--persona", "analyst"])

    assert rc == 0
    assert require_config_calls == [], "init must not invoke require_config"
