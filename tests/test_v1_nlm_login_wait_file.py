"""The legacy external consent signal must never become automatic capture."""
from unittest.mock import Mock
import pytest
from research_hub.notebooklm import auth

@pytest.mark.parametrize("auto_detect", [False, True])
def test_wait_file_fails_before_browser_or_storage_side_effects(tmp_path, monkeypatch, auto_detect, capsys):
    target = tmp_path / "not-created" / "state.json"
    signal = tmp_path / "ready"
    signal.write_text("existing user signal")
    for name in ("run", "Popen"):
        monkeypatch.setattr(auth.subprocess, name, Mock(side_effect=AssertionError("must not launch")))
    assert auth.login_nlm(tmp_path, state_file=target, wait_file=signal,
                          auto_detect=auto_detect) == 2
    assert not target.parent.exists()
    assert signal.read_text() == "existing user signal"
    message = capsys.readouterr().err
    assert "--wait-file" in message and "not supported" in message


def test_rejected_wait_mode_does_not_replace_existing_state(tmp_path, monkeypatch):
    target = tmp_path / "state.json"
    target.write_text("synthetic-existing-state")
    monkeypatch.setattr(auth.subprocess, "run", Mock(side_effect=AssertionError("must not launch")))
    assert auth.login_nlm(tmp_path, state_file=target, wait_file=tmp_path / "ready") == 2
    assert target.read_text() == "synthetic-existing-state"


@pytest.mark.parametrize("other_mode", [[], ["--auto-detect"], ["--from-browser"],
                                        ["--import-from", "synthetic-vault"]])
def test_cli_wait_file_cannot_be_ignored_by_another_login_mode(monkeypatch, capsys, other_mode):
    from research_hub import cli
    monkeypatch.setattr(cli, "get_config", Mock(side_effect=AssertionError("must reject before config")))
    with pytest.raises(SystemExit) as error:
        cli.main(["notebooklm", "login", "--wait-file", "synthetic-ready", *other_mode])
    assert error.value.code == 2
    assert "--wait-file is not supported" in capsys.readouterr().err
