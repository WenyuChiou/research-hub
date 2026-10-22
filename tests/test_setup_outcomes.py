"""Synthetic setup outcomes: no install, login, model, or account calls."""
from types import SimpleNamespace

import pytest

from research_hub import setup_command as setup


def args(**changes):
    values = dict(vault="synthetic-vault", persona="researcher", platform="codex",
                  skip_install=False, skip_login=False, skip_sample=False, no_browser=True)
    values.update(changes)
    return SimpleNamespace(**values)


@pytest.fixture
def isolated(monkeypatch):
    monkeypatch.setattr("research_hub.init_wizard.run_init", lambda **kw: 0)
    monkeypatch.setattr("research_hub.cli._cmd_install", lambda args: 0)
    monkeypatch.setattr(setup, "run_notebooklm_login", lambda: 0)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    monkeypatch.setattr(setup, "detect_host", lambda: None)


def test_failed_install_and_login_are_not_setup_complete(isolated, monkeypatch, capsys):
    monkeypatch.setattr("research_hub.cli._cmd_install", lambda args: 7)
    monkeypatch.setattr(setup, "run_notebooklm_login", lambda: 9)
    assert setup.run_setup(args()) == 0  # legacy orchestration exit, not readiness
    out = capsys.readouterr().out
    assert "install: failed" in out
    assert "notebooklm_login: failed" in out
    assert "Setup complete" not in out
    assert "research-hub install --platform codex" in out
    assert "research-hub notebooklm login --auto-detect" in out


def test_missing_vault_does_not_redefine_legacy_ready(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, "_probe_required_env_vars", lambda env: ({}, []))
    monkeypatch.setattr(setup, "_probe_zotero_reachability", lambda env: (True, ""))
    monkeypatch.setattr(setup, "_detect_llm_cli", lambda: "")
    monkeypatch.setattr(setup, "_probe_installed_skills", lambda platform: [])
    report = setup.run_autonomous(vault=tmp_path / "absent", persona="agent")
    assert report.ready and setup.autonomous_exit_code(report) == 0
    data = report.to_dict()
    assert data["ready_scope"] == "legacy_required_env_and_zotero_probe_only"
    assert data["components"]["vault"]["status"] == "failed"
    assert data["components"]["notebooklm_auth"]["status"] == "unknown"


@pytest.mark.parametrize("result, status", [(0, "passed"), (2, "failed"),
    (KeyboardInterrupt(), "cancelled"), (RuntimeError("synthetic"), "failed")])
def test_login_outcome(isolated, monkeypatch, capsys, result, status):
    def login():
        if isinstance(result, BaseException):
            raise result
        return result
    monkeypatch.setattr(setup, "run_notebooklm_login", login)
    assert setup.run_setup(args(skip_sample=True)) == 0
    out = capsys.readouterr().out
    assert f"notebooklm_login: {status}" in out
    assert "notebooklm login --auto-detect" in out
    assert "Setup complete" not in out


@pytest.mark.parametrize("changes, text", [
    ({"skip_login": True}, "notebooklm_login: skipped"),
    ({"persona": "analyst"}, "notebooklm_login: skipped"),
    ({"vault": None, "skip_login": True}, "notebooklm_login: unknown"),
    ({"skip_install": True}, "install: skipped"),
    ({"platform": None}, "install: skipped"),
])
def test_skips_and_delegated_login(isolated, monkeypatch, capsys, changes, text):
    if changes.get("skip_login") or changes.get("persona") == "analyst":
        monkeypatch.setattr(setup, "run_notebooklm_login", lambda: pytest.fail("Unexpected login"))
    assert setup.run_setup(args(skip_sample=True, **changes)) == 0
    assert text in capsys.readouterr().out


def test_init_failure_preserves_exit_and_does_not_attempt_later_steps(isolated, monkeypatch, capsys):
    monkeypatch.setattr("research_hub.init_wizard.run_init", lambda **kw: 4)
    monkeypatch.setattr("research_hub.cli._cmd_install", lambda args: pytest.fail("Unexpected install"))
    monkeypatch.setattr(setup, "run_notebooklm_login", lambda: pytest.fail("Unexpected login"))
    assert setup.run_setup(args()) == 4
    out = capsys.readouterr().out
    assert "init: failed" in out and "install: skipped" in out


@pytest.mark.parametrize("vault_kind", ["file", "unwritable", "directory"])
def test_vault_checks_are_scoped(tmp_path, monkeypatch, vault_kind):
    vault = tmp_path / "vault"
    if vault_kind == "file":
        vault.write_text("synthetic")
    else:
        vault.mkdir()
    monkeypatch.setattr(setup.os, "access", lambda *a: vault_kind != "unwritable")
    monkeypatch.setattr(setup, "_probe_required_env_vars", lambda env: ({}, []))
    monkeypatch.setattr(setup, "_probe_zotero_reachability", lambda env: (True, ""))
    monkeypatch.setattr(setup, "_detect_llm_cli", lambda: "codex")
    monkeypatch.setattr(setup, "_probe_installed_skills", lambda platform: ["synthetic-skill"])
    report = setup.run_autonomous(vault=vault, persona="agent")
    assert report.ready is True
    assert report.components["vault"]["status"] == ("passed" if vault_kind == "directory" else "failed")
    assert report.components["llm_cli"]["status"] == "unknown"
    assert report.components["skills"]["status"] == "unknown"
    copied = report.to_dict()
    copied["components"]["vault"]["status"] = "changed"
    assert report.components["vault"]["status"] != "changed"


@pytest.mark.parametrize("state", [None, "", '{"cookies":[]}'])
def test_nlm_state_is_never_authenticated_evidence(tmp_path, monkeypatch, state):
    if state is not None:
        path = tmp_path / ".research_hub/nlm_sessions/state.json"
        path.parent.mkdir(parents=True)
        path.write_text(state)
    monkeypatch.setattr(setup, "_probe_required_env_vars", lambda env: ({}, ["ZOTERO_API_KEY"]))
    monkeypatch.setattr(setup, "_probe_zotero_reachability", lambda env: pytest.fail("Unexpected probe"))
    monkeypatch.setattr(setup, "_detect_llm_cli", lambda: "")
    monkeypatch.setattr(setup, "_probe_installed_skills", lambda platform: [])
    monkeypatch.setattr(setup, "run_notebooklm_login", lambda: pytest.fail("Unexpected login"))
    report = setup.run_autonomous(vault=tmp_path, persona="agent")
    assert not report.ready
    assert report.nlm_auth_status == ("present" if state else "missing")
    assert report.components["notebooklm_auth"]["status"] == "unknown"
    assert report.components["zotero"]["status"] == "skipped"
    assert report.components["environment"]["status"] == "failed"


def test_failed_zotero_probe_is_not_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, "_probe_required_env_vars", lambda env: ({}, []))
    monkeypatch.setattr(setup, "_probe_zotero_reachability", lambda env: (False, "synthetic failure"))
    monkeypatch.setattr(setup, "_detect_llm_cli", lambda: "")
    monkeypatch.setattr(setup, "_probe_installed_skills", lambda platform: [])
    report = setup.run_autonomous(vault=tmp_path, persona="agent")
    assert report.components["zotero"]["status"] == "failed"
    assert setup.autonomous_exit_code(report) == 1


@pytest.mark.parametrize("result,status", [(SimpleNamespace(ok=False), "failed"), (None, "unknown"), (SimpleNamespace(ok="yes"), "unknown"), (SimpleNamespace(ok=True), "passed")])
def test_sample_return_value_not_just_absence_of_exception(isolated, monkeypatch, capsys, result, status):
    answers = iter(["y", "synthetic-topic"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    monkeypatch.setattr("research_hub.auto.auto_pipeline", lambda **kw: result)
    calls = []
    monkeypatch.setattr("research_hub.dashboard.generate_dashboard", lambda **kw: calls.append(kw))
    assert setup.run_setup(args()) == 0
    out = capsys.readouterr().out
    assert f"sample: {status}" in out
    assert len(calls) == (1 if status == "passed" else 0)
    assert "Setup complete" not in out


def test_dashboard_failure_does_not_relabel_sample(isolated, monkeypatch, capsys):
    answers = iter(["y", "synthetic-topic"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    monkeypatch.setattr("research_hub.auto.auto_pipeline", lambda **kw: SimpleNamespace(ok=True))
    def fail(**kw):
        raise RuntimeError("synthetic")
    monkeypatch.setattr("research_hub.dashboard.generate_dashboard", fail)
    assert setup.run_setup(args()) == 0
    out = capsys.readouterr().out
    assert "sample: passed" in out and "dashboard: failed" in out


@pytest.mark.parametrize("exception", [KeyboardInterrupt, EOFError])
def test_topic_prompt_cancel_does_not_start_sample(isolated, monkeypatch, capsys, exception):
    answers = iter(["y"])
    def answer(prompt=""):
        if "Topic to try" in prompt:
            raise exception
        return next(answers)
    monkeypatch.setattr("builtins.input", answer)
    monkeypatch.setattr("research_hub.auto.auto_pipeline", lambda **kw: pytest.fail("Unexpected sample"))
    assert setup.run_setup(args()) == 0
    assert "sample: cancelled" in capsys.readouterr().out


def test_init_banner_does_not_claim_all_setup_complete(tmp_path, monkeypatch, capsys):
    from research_hub.init_wizard import _print_completion_banner
    monkeypatch.setattr(setup, "detect_host", lambda: "codex")
    monkeypatch.setattr("research_hub.skill_installer.list_platforms", lambda: [])
    _print_completion_banner(tmp_path, tmp_path / "synthetic-config.json")
    out = capsys.readouterr().out
    assert "Setup complete" not in out
    assert "Vault/config initialization complete" in out


def test_dashboard_cancel_does_not_relabel_sample(isolated, monkeypatch, capsys):
    answers = iter(["y", "synthetic-topic"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    monkeypatch.setattr("research_hub.auto.auto_pipeline", lambda **kw: SimpleNamespace(ok=True))
    def cancel(**kw):
        raise KeyboardInterrupt
    monkeypatch.setattr("research_hub.dashboard.generate_dashboard", cancel)
    assert setup.run_setup(args()) == 0
    out = capsys.readouterr().out
    assert "sample: passed" in out and "dashboard: cancelled" in out


@pytest.mark.parametrize("stage", ["init", "install"])
@pytest.mark.parametrize("error,status", [(RuntimeError("synthetic"), "failed"), (KeyboardInterrupt(), "cancelled"), (EOFError(), "cancelled"), (SystemExit(3), "failed"), (SystemExit(0), "cancelled")])
def test_aborted_stage_reports_and_reraises_original(isolated, monkeypatch, capsys, stage, error, status):
    def abort(*a, **kw):
        raise error
    target = "research_hub.init_wizard.run_init" if stage == "init" else "research_hub.cli._cmd_install"
    monkeypatch.setattr(target, abort)
    monkeypatch.setattr(setup, "run_notebooklm_login", lambda: pytest.fail("Unexpected later login"))
    with pytest.raises(type(error)) as caught:
        setup.run_setup(args())
    assert caught.value is error
    out = capsys.readouterr().out
    assert f"{stage}: {status}" in out
    assert "notebooklm_login: skipped" in out
    assert "sample: skipped" in out and "dashboard: skipped" in out
    assert "partial changes may exist" in out
    if stage == "init":
        assert "install: skipped" in out
    else:
        assert "init: passed" in out


def test_broken_summary_output_does_not_mask_original_failure(isolated, monkeypatch):
    error = RuntimeError("original synthetic failure")
    def abort(**kw):
        raise error
    def broken_output(*a):
        raise BrokenPipeError("synthetic closed pipe")
    monkeypatch.setattr("research_hub.init_wizard.run_init", abort)
    monkeypatch.setattr(setup, "_print_outcomes", broken_output)
    with pytest.raises(RuntimeError) as caught:
        setup.run_setup(args())
    assert caught.value is error


def test_interrupted_interactive_init_does_not_invent_login_skip(isolated, monkeypatch, capsys):
    def abort(**kw):
        raise RuntimeError("synthetic init failed after possible delegated login")
    monkeypatch.setattr("research_hub.init_wizard.run_init", abort)
    with pytest.raises(RuntimeError):
        setup.run_setup(args(vault=None))
    assert "notebooklm_login: unknown" in capsys.readouterr().out
