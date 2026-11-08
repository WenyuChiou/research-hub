"""Serial, synthetic first-use checks; no accounts, browsers, or models."""

from __future__ import annotations

import json
import sys
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


@pytest.fixture
def isolated_init(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    from research_hub import config, init_wizard

    config_path = tmp_path / "config" / "config.json"
    vault = tmp_path / "vault"
    monkeypatch.setattr(init_wizard, "get_default_config_path", lambda: config_path)
    monkeypatch.setattr(config, "CONFIG_PATH", fake_home / "legacy-config.json")
    monkeypatch.setattr(config, "_LEGACY_ZOTERO_SKILL_CONFIG", fake_home / "legacy-zotero.json")
    monkeypatch.setenv("RESEARCH_HUB_CONFIG", str(config_path))
    monkeypatch.setenv("RESEARCH_HUB_ROOT", str(vault))
    monkeypatch.setenv("ZOTERO_API_KEY", "")
    monkeypatch.setenv("ZOTERO_LIBRARY_ID", "")
    monkeypatch.setattr(config, "_config", None)
    monkeypatch.setattr(config, "_config_path", None)
    monkeypatch.setattr(init_wizard.shutil, "which", lambda _name: None)
    monkeypatch.setattr("research_hub.setup_command.detect_host", lambda: "codex")
    monkeypatch.setattr("research_hub.skill_installer.list_platforms", lambda: [])

    def reject(*args, **kwargs):
        pytest.fail("Unexpected external HTTP, model, CLI, login, or browser operation")

    import pytest_socket
    pytest_socket.disable_socket()
    for target in (
        "requests.head", "requests.api.request", "requests.sessions.Session.request",
        "httpx.request", "httpx._api.request", "httpx.Client.request", "httpx.AsyncClient.request",
        "urllib.request.urlopen",
        "subprocess.Popen", "webbrowser.open", "webbrowser.open_new", "webbrowser.open_new_tab",
        "research_hub.llm_cli.invoke_llm_cli", "research_hub.llm_cli._invoke_llm_cli",
        "research_hub.auto._invoke_llm_cli", "research_hub.setup_command.run_notebooklm_login",
        "research_hub.notebooklm.auth.login_nlm", "research_hub.notebooklm.auth.login_from_browser",
    ):
        monkeypatch.setattr(target, reject)
    # The shared _block_real_patchright fixture rejects browser launches.
    # Tests of opt-in below supply synthetic Chrome availability explicitly.
    return init_wizard, config_path, vault


def _synthetic_chrome(monkeypatch, wizard):
    monkeypatch.setattr(
        wizard, "_check_first_run_readiness",
        lambda *args, **kwargs: [("chrome", "OK", "synthetic availability only")],
    )


@pytest.mark.parametrize("persona", ["researcher", "humanities", "analyst", "internal"])
def test_no_credentials_recommends_local_reading(isolated_init, capsys, persona):
    wizard, config_path, vault = isolated_init
    assert wizard.run_init(vault_root=str(vault), persona=persona, non_interactive=True) == 0
    output = capsys.readouterr().out
    assert "import-folder <folder> --cluster <slug> --extensions md,txt" in output
    assert "research-hub auto" not in output
    assert "local reading does not need it" in output
    assert "Zotero is an optional reference manager" in output
    assert "exit code 0 do not prove service access" in output
    assert config_path.is_file()


@pytest.mark.parametrize("status", [200, 403, None])
def test_only_successful_read_probe_offers_connected_pipeline(
    isolated_init, monkeypatch, capsys, status,
):
    wizard, _config_path, vault = isolated_init

    def head(*args, **kwargs):
        if status is None:
            raise ConnectionError("synthetic unavailable service")
        return SimpleNamespace(status_code=status)

    monkeypatch.setattr("requests.head", head)
    assert wizard.run_init(
        vault_root=str(vault), persona="researcher", non_interactive=True,
        zotero_key="synthetic-key", zotero_library_id="123",
    ) == 0
    output = capsys.readouterr().out
    assert ('research-hub auto "your research topic" --no-nlm' in output) is (status == 200)
    assert "verified above" not in output
    assert "credentials configured; check access" in output
    assert "synthetic-key" not in output


def test_saved_credentials_reused_without_reprompt_or_verification_claim(
    isolated_init, monkeypatch, capsys,
):
    wizard, config_path, vault = isolated_init
    _synthetic_chrome(monkeypatch, wizard)
    config_path.parent.mkdir()
    saved = {"api_key": "enc::synthetic-existing", "library_id": "123"}
    config_path.write_text(json.dumps({"zotero": saved, "custom": {"keep": True}}), encoding="utf-8")
    monkeypatch.setattr(wizard.sys.stdin, "isatty", lambda: True)
    prompts = []
    monkeypatch.setattr("builtins.input", lambda prompt="": prompts.append(prompt) or "n")
    assert wizard.run_init(vault_root=str(vault), persona="researcher") == 0
    output = capsys.readouterr().out
    assert prompts == ["  Connect NotebookLM now? [y/N]: "]
    assert "Zotero settings are saved; access is not verified" in output
    assert "research-hub auto" not in output
    assert saved["api_key"] not in output
    written = json.loads(config_path.read_text(encoding="utf-8"))
    assert written["zotero"] == saved
    assert written["custom"] == {"keep": True}


def test_connections_can_be_deferred_without_key_or_library_prompts(
    isolated_init, monkeypatch, capsys,
):
    wizard, _config_path, vault = isolated_init
    _synthetic_chrome(monkeypatch, wizard)
    monkeypatch.setattr(wizard.sys.stdin, "isatty", lambda: True)
    prompts = []
    monkeypatch.setattr("builtins.input", lambda prompt="": prompts.append(prompt) or "")
    monkeypatch.setattr(
        "research_hub.setup_command.run_notebooklm_login",
        lambda: pytest.fail("Unexpected NotebookLM login"),
    )
    assert wizard.run_init(vault_root=str(vault), persona="researcher") == 0
    assert prompts == ["  Connect Zotero now? [y/N]: ", "  Connect NotebookLM now? [y/N]: "]
    assert "research-hub auto" not in capsys.readouterr().out


def test_blank_key_defers_library_setup(isolated_init, monkeypatch):
    wizard, config_path, vault = isolated_init
    monkeypatch.setattr(wizard.sys.stdin, "isatty", lambda: True)
    answers = iter(["y", ""])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    assert wizard.run_init(vault_root=str(vault), persona="researcher", no_browser=True) == 0
    assert "zotero" not in json.loads(config_path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("credentials", [{"zotero_key": "synthetic-key"}, {"zotero_library_id": "123"}])
def test_partial_credentials_keep_local_guidance(isolated_init, capsys, credentials):
    wizard, _config_path, vault = isolated_init
    assert wizard.run_init(
        vault_root=str(vault), persona="researcher", non_interactive=True, **credentials,
    ) == 0
    output = capsys.readouterr().out
    assert "Zotero is not connected" in output
    assert "research-hub auto" not in output


def test_cli_presence_is_not_model_readiness(isolated_init, monkeypatch):
    wizard, _config_path, vault = isolated_init
    monkeypatch.setattr(wizard.shutil, "which", lambda _name: "synthetic-cli")
    rows = wizard._check_first_run_readiness(vault, persona="researcher", has_zotero=False)
    assert next(row for row in rows if row[0] == "llm-cli")[1:] == (
        "INFO", "`claude` on PATH; model access not verified",
    )


@pytest.mark.parametrize("persona", ["researcher", "humanities"])
def test_recommended_local_import_runs_without_credentials(isolated_init, capsys, persona):
    from research_hub.cli import main

    wizard, _config_path, vault = isolated_init
    source_dir = vault.parent / "selected-sources"
    source_dir.mkdir()
    (source_dir / "source.md").write_text("# Local evidence\nSynthetic reading source.\n", encoding="utf-8")
    assert wizard.run_init(vault_root=str(vault), persona=persona, non_interactive=True) == 0
    assert main([
        "import-folder", str(source_dir), "--cluster", "my-reading", "--extensions", "md,txt",
    ]) == 0
    output = capsys.readouterr().out
    assert "imported:  1" in output
    assert "failed:    0" in output
    notes = list((vault / "raw" / "my-reading").glob("*.md"))
    assert len(notes) == 1
    assert "Synthetic reading source." in notes[0].read_text(encoding="utf-8")


@pytest.mark.parametrize("payload", [
    b'{"keep":', b'\xffinvalid-utf8', b'[]', b'null',
    b'{"knowledge_base": []}', b'{"zotero": []}', b'{"knowledge_base": {"root": 42}}',
])
def test_malformed_config_is_preserved(isolated_init, capsys, payload):
    wizard, config_path, vault = isolated_init
    config_path.parent.mkdir()
    config_path.write_bytes(payload)
    assert wizard.run_init(vault_root=str(vault), persona="researcher", non_interactive=True) == 1
    assert config_path.read_bytes() == payload
    assert not vault.exists()
    assert "existing settings were not changed" in capsys.readouterr().out


def test_unreadable_config_is_preserved(isolated_init, monkeypatch, capsys):
    wizard, config_path, vault = isolated_init
    config_path.parent.mkdir()
    payload = b'{"custom": {"keep": true}}\n'
    config_path.write_bytes(payload)
    original_read = Path.read_text

    def unreadable(path, *args, **kwargs):
        if path == config_path:
            raise PermissionError("synthetic unreadable config")
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", unreadable)
    assert wizard.run_init(vault_root=str(vault), persona="researcher", non_interactive=True) == 1
    assert config_path.read_bytes() == payload
    assert not vault.exists()
    assert "existing settings were not changed" in capsys.readouterr().out


@pytest.mark.parametrize("persona_override", ["researcher", None])
def test_connect_later_reuses_saved_vault_without_override(isolated_init, monkeypatch, persona_override):
    wizard, config_path, vault = isolated_init
    custom_vault = vault.parent / "my-custom-reading-vault"
    assert wizard.run_init(
        vault_root=str(custom_vault), persona="researcher", non_interactive=True,
    ) == 0
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    saved["knowledge_base"]["hub"] = str(custom_vault / "my-hub")
    saved["custom"] = {"keep": ["unrelated", {"nested": True}]}
    saved["zotero"] = {"collections": {"saved": {"key": "KEEP"}}}
    config_path.write_text(json.dumps(saved), encoding="utf-8")
    prompts = []

    def answer(prompt=""):
        prompts.append(prompt)
        if prompt.startswith("Vault root directory"):
            return ""  # Reproduce the old default-home replacement on rerun.
        return {"> ": "y", "  Connect Zotero now? [y/N]: ": "y",
                "  Zotero API key: ": "synthetic-connect-later", "  Zotero library ID: ": "456"}[prompt]

    monkeypatch.setattr(wizard.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", answer)
    monkeypatch.setattr("requests.head", lambda *args, **kwargs: SimpleNamespace(status_code=200))
    assert wizard.run_init(persona=persona_override, no_browser=True) == 0
    written = json.loads(config_path.read_text(encoding="utf-8"))
    assert written["knowledge_base"] == saved["knowledge_base"]
    assert written["custom"] == saved["custom"]
    assert written["zotero"]["collections"] == saved["zotero"]["collections"]
    assert written["zotero"]["library_id"] == "456"
    assert not any(prompt.startswith("Vault root directory") for prompt in prompts)
    assert "> " not in prompts


@pytest.mark.parametrize("no_browser,choice,expected_calls", [(False, "y", 1), (False, "n", 0), (True, "y", 0)])
def test_nlm_opt_in_respects_no_browser(isolated_init, monkeypatch, no_browser, choice, expected_calls):
    wizard, _config_path, vault = isolated_init
    _synthetic_chrome(monkeypatch, wizard)
    monkeypatch.setattr(wizard.sys.stdin, "isatty", lambda: True)
    prompts, calls = [], []
    monkeypatch.setattr("builtins.input", lambda prompt="": prompts.append(prompt) or choice)
    monkeypatch.setattr("requests.head", lambda *args, **kwargs: SimpleNamespace(status_code=200))
    monkeypatch.setattr("research_hub.setup_command.run_notebooklm_login", lambda: calls.append("synthetic login") or 0)
    assert wizard.run_init(
        vault_root=str(vault), persona="researcher", no_browser=no_browser,
        zotero_key="synthetic-key", zotero_library_id="123",
    ) == 0
    assert len(calls) == expected_calls
    assert prompts == ([] if no_browser else ["  Connect NotebookLM now? [y/N]: "])


@pytest.mark.parametrize("retry_result", [200, 403, "exception"])
def test_retry_guidance_follows_probe_outcome(isolated_init, monkeypatch, capsys, retry_result):
    wizard, config_path, vault = isolated_init
    monkeypatch.setattr(wizard.sys.stdin, "isatty", lambda: True)
    probes = []

    def head(*args, **kwargs):
        probes.append(args[0])
        if len(probes) == 1:
            return SimpleNamespace(status_code=403)
        if retry_result == "exception":
            raise ConnectionError("synthetic retry unavailable")
        return SimpleNamespace(status_code=retry_result)

    prompts = []
    answers = iter(["y", "retry-synthetic-key", "456", "c"])
    monkeypatch.setattr("requests.head", head)
    monkeypatch.setattr("builtins.input", lambda prompt="": prompts.append(prompt) or next(answers))
    assert wizard.run_init(
        vault_root=str(vault), persona="researcher", no_browser=True,
        zotero_key="first-synthetic-key", zotero_library_id="123",
    ) == 0
    output = capsys.readouterr().out
    assert len(probes) == 2
    assert prompts.count("    Retry Zotero validation? [y/N]: ") == 1
    assert ('research-hub auto "your research topic" --no-nlm' in output) is (retry_result == 200)
    assert "verified above" not in output
    if retry_result == 403:
        assert "WARN still 403" in output
    elif retry_result == "exception":
        assert "could not reach api.zotero.org" in output
    assert "retry-synthetic-key" not in output
    assert json.loads(config_path.read_text(encoding="utf-8"))["zotero"]["library_id"] == "456"


def test_isolation_rejects_other_transports_and_runners(isolated_init):
    import httpx
    import requests
    import subprocess
    import urllib.request
    import webbrowser
    from research_hub.llm_cli import invoke_llm_cli
    from research_hub.setup_command import run_notebooklm_login

    for operation in (
        lambda: requests.get("https://synthetic.invalid"),
        lambda: requests.post("https://synthetic.invalid"),
        lambda: httpx.get("https://synthetic.invalid"),
        lambda: urllib.request.urlopen("https://synthetic.invalid"),
        lambda: subprocess.Popen(["synthetic-model-cli"]),
        lambda: invoke_llm_cli("synthetic prompt"),
        lambda: webbrowser.open("https://synthetic.invalid"),
        run_notebooklm_login,
    ):
        with pytest.raises(pytest.fail.Exception, match="Unexpected external"):
            operation()


def test_urllib3_capability_probe_is_synthetic(isolated_init):
    import socket
    from urllib3.util.connection import HAS_IPV6

    assert socket.has_ipv6 is False
    assert HAS_IPV6 is False


@pytest.mark.parametrize("non_interactive", [False, True])
def test_init_does_not_launch_a_passive_browser_probe(isolated_init, monkeypatch, capsys, non_interactive):
    wizard, _config_path, vault = isolated_init
    package = ModuleType("patchright")
    package.__path__ = []
    package.__spec__ = ModuleSpec("patchright", loader=None, is_package=True)
    api = ModuleType("patchright.sync_api")
    api.sync_playwright = lambda: pytest.fail("Init must not launch an optional browser readiness probe")
    monkeypatch.setitem(sys.modules, "patchright", package)
    monkeypatch.setitem(sys.modules, "patchright.sync_api", api)
    monkeypatch.setattr(wizard.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    assert wizard.run_init(
        vault_root=str(vault), persona="humanities", no_browser=True,
        non_interactive=non_interactive,
    ) == 0
    output = capsys.readouterr().out
    assert "browser launch and NotebookLM authentication unverified" in output
    assert "research-hub auto" not in output
