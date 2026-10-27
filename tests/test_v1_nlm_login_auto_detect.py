"""SDK-managed login contract. No browser or user storage is accessed."""
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from research_hub.notebooklm import auth


@pytest.mark.parametrize("auto_detect", [False, True])
def test_login_delegates_to_sdk_and_validates_session(tmp_path, monkeypatch, auto_detect):
    state = tmp_path / "vault" / "state.json"
    run = Mock(return_value=SimpleNamespace(returncode=0))
    health = Mock(return_value={"ok": True})
    tighten = Mock()
    monkeypatch.setattr(auth.subprocess, "run", run)
    monkeypatch.setattr(auth, "check_session_health", health)
    monkeypatch.setattr(auth, "_tighten_state_file_perms", tighten)
    assert auth.login_nlm(tmp_path, state_file=state, auto_detect=auto_detect,
                          wait_timeout=37) == 0
    command = run.call_args.args[0]
    assert command[1:] == ["-m", "notebooklm.notebooklm_cli", "--storage", str(state),
                            "login", "--storage", str(state), "--browser-timeout", "37"]
    assert run.call_args.kwargs == {"check": False}
    assert "--headless" not in command and "--cdp" not in command
    health.assert_called_once_with(state)
    assert tighten.call_count == 2
    assert all(call.args == (state,) for call in tighten.call_args_list)


@pytest.mark.parametrize("health", [{"ok": False, "reason": "state.json missing"},
    {"ok": False, "reason": "auth invalid"}, {"ok": False, "reason": "unknown"}, {}, {"ok": "unknown"}])
def test_capture_success_is_not_authenticated_success(tmp_path, monkeypatch, health, capsys):
    monkeypatch.setattr(auth.subprocess, "run", Mock(return_value=SimpleNamespace(returncode=0)))
    monkeypatch.setattr(auth, "check_session_health", Mock(return_value=health))
    assert auth.login_nlm(tmp_path, state_file=tmp_path / "state.json", auto_detect=True) != 0
    assert "not verified" in capsys.readouterr().err


def test_failed_capture_does_not_validate_or_claim_success(tmp_path, monkeypatch):
    monkeypatch.setattr(auth.subprocess, "run", Mock(return_value=SimpleNamespace(returncode=124)))
    health = Mock(side_effect=AssertionError("failed capture must not validate"))
    monkeypatch.setattr(auth, "check_session_health", health)
    assert auth.login_nlm(tmp_path, state_file=tmp_path / "state.json", auto_detect=True) == 124
    health.assert_not_called()


@pytest.mark.parametrize("url,accepted", [
    ("https://notebook.google.com/", True), ("https://notebooklm.google.com/", True),
    ("https://accounts.google.com/signin", False),
    ("https://notebook.google.com.evil.invalid/", False),
    ("https://evil.invalid/notebook.google.com/", False),
    ("https://notebook.google.com@evil.invalid/", False), ("", False),
])
def test_sdk_host_membership_is_exact_but_not_authentication(url, accepted, monkeypatch):
    monkeypatch.delenv("NOTEBOOKLM_BASE_URL", raising=False)
    from notebooklm._browser.browser_capture import url_matches_base_host
    assert url_matches_base_host(url) is accepted


@pytest.mark.parametrize("host", ["notebook.google.com", "notebooklm.google.com"])
def test_sdk_missing_field_is_unknown_not_authenticated_or_proven_expired(host):
    from notebooklm._auth.extraction import extract_csrf_from_html, _signed_out_probe_failure
    url = f"https://{host}/"
    with pytest.raises(ValueError, match="CSRF token not found") as error:
        extract_csrf_from_html('<a href="https://accounts.google.com/">Sign in</a>', url)
    assert "Authentication expired" not in str(error.value)
    assert _signed_out_probe_failure(url, url, ()) is None
    signed_out = _signed_out_probe_failure(url, "https://accounts.google.com/signin", ())
    assert signed_out is not None and "Authentication expired" in str(signed_out)


def test_missing_saved_state_does_not_probe(tmp_path, monkeypatch):
    probe = Mock(side_effect=AssertionError("missing state must not probe"))
    monkeypatch.setattr(auth, "_probe_state_file", probe)
    assert auth.check_session_health(tmp_path / "absent.json")["ok"] is False
    probe.assert_not_called()


@pytest.mark.parametrize("mode", ["normal", "from-browser"])
def test_real_sdk_cli_binds_only_requested_storage_without_default_migration(tmp_path, monkeypatch, mode):
    from click.testing import CliRunner
    from notebooklm.notebooklm_cli import cli as sdk_cli
    from notebooklm.cli import session_cmd
    from notebooklm import migration

    target = tmp_path / "vault" / "state.json"
    calls = []
    monkeypatch.setenv("NOTEBOOKLM_HOME", str(tmp_path / "unused-default-home"))
    monkeypatch.delenv("NOTEBOOKLM_AUTH_JSON", raising=False)
    monkeypatch.setattr(migration, "ensure_profiles_dir", Mock(
        side_effect=AssertionError("explicit storage must not migrate default profiles")))

    def prepare(profile, storage, fresh):
        assert storage == str(target)
        assert fresh is False
        calls.append(("prepare", storage))
        return target, tmp_path / "synthetic-profile"

    monkeypatch.setattr(session_cmd, "prepare_paths_or_exit", prepare)
    monkeypatch.setattr(session_cmd, "_run_playwright_login",
                        lambda **kwargs: calls.append(("capture", kwargs["storage_path"])))
    monkeypatch.setattr(session_cmd, "_sync_server_language_to_config", lambda **kwargs: None)
    monkeypatch.setattr(session_cmd, "_login_browser_cookies_single",
                        lambda browser, **kwargs: calls.append(("import", kwargs["storage"])))
    cli_results = []

    def run(command, **kwargs):
        result = CliRunner().invoke(sdk_cli, command[3:])
        cli_results.append(result)
        return SimpleNamespace(returncode=result.exit_code)

    monkeypatch.setattr(auth.subprocess, "run", run)
    monkeypatch.setattr(auth, "check_session_health", Mock(return_value={"ok": True}))
    if mode == "normal":
        rc = auth.login_nlm(tmp_path, state_file=target)
        expected = [("prepare", str(target)), ("capture", target)]
    else:
        rc = auth.login_from_browser(target, browser="chrome")
        expected = [("import", str(target))]
    assert rc == 0, str(cli_results[0].exception)
    assert calls == expected
    assert not (tmp_path / "unused-default-home").exists()
    assert not target.exists()


def test_doctor_recognizes_sdk_cookie_extra_without_claiming_auth(monkeypatch):
    from research_hub import doctor
    monkeypatch.setattr(doctor.importlib.util, "find_spec",
                        lambda name: object() if name == "rookie_cookies" else None)
    result = doctor.check_nlm_auth_paths()
    assert result.status == "OK"
    assert "rookie_cookies" in result.message
    assert "logged in" not in result.message
