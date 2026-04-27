"""Tests for the interactive init wizard."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from research_hub.security.secret_box import decrypt, is_encrypted


@pytest.fixture(autouse=True)
def reset_config_cache():
    from research_hub import config as hub_config

    hub_config._config = None
    hub_config._config_path = None
    yield
    hub_config._config = None
    hub_config._config_path = None


def test_init_non_interactive_happy_path(tmp_path, monkeypatch, capsys):
    from research_hub import init_wizard

    vault = tmp_path / "vault"
    config_dir = tmp_path / "config"
    monkeypatch.setattr(
        init_wizard.platformdirs,
        "user_config_dir",
        lambda *args, **kwargs: str(config_dir),
    )
    monkeypatch.setattr(
        "research_hub.notebooklm.cdp_launcher.find_chrome_binary",
        lambda: None,
    )
    monkeypatch.setattr("requests.head", lambda *args, **kwargs: SimpleNamespace(status_code=200))

    exit_code = init_wizard.run_init(
        vault_root=str(vault),
        zotero_key="secret",
        zotero_library_id="12345",
        non_interactive=True,
    )

    assert exit_code == 0
    config = json.loads((config_dir / "config.json").read_text(encoding="utf-8"))
    assert config["knowledge_base"]["root"] == str(vault.resolve())
    assert is_encrypted(config["zotero"]["api_key"])
    assert decrypt(config["zotero"]["api_key"], config_dir) == "secret"
    assert config["zotero"]["library_id"] == "12345"
    assert "Config written" in capsys.readouterr().out


def test_init_non_interactive_missing_vault_fails(monkeypatch, capsys):
    from research_hub import init_wizard

    monkeypatch.setattr(init_wizard.sys.stdin, "isatty", lambda: False)

    assert init_wizard.run_init(non_interactive=True) == 1
    assert "required in non-interactive mode" in capsys.readouterr().out


def test_init_interactive_prompts(tmp_path, monkeypatch, capsys):
    from research_hub import init_wizard

    config_dir = tmp_path / "config"
    default_home = tmp_path / "home"
    answers = iter(
        [
            "y",  # Q0: do you use Zotero?
            "1",  # persona menu in Zotero branch -> researcher
            str(tmp_path / "interactive-vault"),
            "z-key",
            "999",
        ]
    )
    prompts: list[str] = []

    monkeypatch.setattr(init_wizard.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(init_wizard.Path, "home", classmethod(lambda cls: default_home))
    monkeypatch.setattr(
        init_wizard.platformdirs,
        "user_config_dir",
        lambda *args, **kwargs: str(config_dir),
    )
    monkeypatch.setattr("builtins.input", lambda prompt="": prompts.append(prompt) or next(answers))
    monkeypatch.setattr("requests.head", lambda *args, **kwargs: SimpleNamespace(status_code=200))
    monkeypatch.setattr(
        init_wizard,
        "_check_first_run_readiness",
        lambda vault, *, persona, has_zotero: [("chrome", "OK", "patchright can launch Chrome")],
    )
    # v0.62: mandatory NLM login auto-launches when chrome_ok; stub it out
    monkeypatch.setattr("research_hub.setup_command.run_notebooklm_login", lambda: None)
    # v0.68.4: stub webbrowser.open so the test does not actually launch a
    # real browser to https://www.zotero.org/settings/keys when the user
    # hasn't pre-supplied a key. (Test was popping the page on every full
    # `pytest` run.)
    browser_calls: list[str] = []
    monkeypatch.setattr("webbrowser.open", lambda url, *a, **k: browser_calls.append(url) or True)

    assert init_wizard.run_init() == 0

    output = capsys.readouterr().out
    config = json.loads((config_dir / "config.json").read_text(encoding="utf-8"))
    assert config["knowledge_base"]["root"] == str((tmp_path / "interactive-vault").resolve())
    assert is_encrypted(config["zotero"]["api_key"])
    assert decrypt(config["zotero"]["api_key"], config_dir) == "z-key"
    assert config["zotero"]["library_id"] == "999"
    # v0.62: when chrome_ok, NLM login auto-launches (no [y/N] prompt)
    assert prompts == [
        "> ",  # Q0
        "> ",  # persona menu in Zotero branch
        f"Vault root directory [{default_home / 'knowledge-base'}]: ",
        "  Zotero API key: ",
        "  Zotero library ID: ",
    ]
    assert "First-run readiness check" in output
    assert "patchright can launch Chrome" in output
    # v0.68.4: regression — interactive flow MUST route through the
    # mocked webbrowser.open (not pop a real browser). This test was
    # actually launching the Zotero keys page on every full pytest run
    # before the mock was added.
    assert browser_calls == ["https://www.zotero.org/settings/keys"]


def test_init_creates_vault_subdirs(tmp_path, monkeypatch):
    from research_hub import init_wizard

    vault = tmp_path / "vault"
    config_dir = tmp_path / "config"
    monkeypatch.setattr(
        init_wizard.platformdirs,
        "user_config_dir",
        lambda *args, **kwargs: str(config_dir),
    )
    monkeypatch.setattr(
        "research_hub.notebooklm.cdp_launcher.find_chrome_binary",
        lambda: None,
    )

    assert init_wizard.run_init(vault_root=str(vault), non_interactive=True) == 0

    for name in ("raw", "hub", "logs", "pdfs", ".research_hub"):
        assert (vault / name).is_dir()


def test_init_preserves_existing_config(tmp_path, monkeypatch):
    from research_hub import init_wizard

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(
        json.dumps(
            {
                "knowledge_base": {"hub": "/existing/hub"},
                "zotero": {"collections": {"A": {"name": "Saved"}}},
                "custom": {"feature": True},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        init_wizard.platformdirs,
        "user_config_dir",
        lambda *args, **kwargs: str(config_dir),
    )
    monkeypatch.setattr(
        "research_hub.notebooklm.cdp_launcher.find_chrome_binary",
        lambda: None,
    )

    assert init_wizard.run_init(vault_root=str(tmp_path / "vault"), non_interactive=True) == 0

    config = json.loads((config_dir / "config.json").read_text(encoding="utf-8"))
    assert config["knowledge_base"]["hub"] == "/existing/hub"
    assert config["zotero"]["collections"] == {"A": {"name": "Saved"}}
    assert config["custom"] == {"feature": True}


def test_init_validates_zotero_credentials(tmp_path, monkeypatch, capsys):
    from research_hub import init_wizard

    config_dir = tmp_path / "config"
    statuses = iter([200, 403])

    def fake_head(*args, **kwargs):
        return SimpleNamespace(status_code=next(statuses))

    monkeypatch.setattr(
        init_wizard.platformdirs,
        "user_config_dir",
        lambda *args, **kwargs: str(config_dir),
    )
    monkeypatch.setattr("requests.head", fake_head)
    monkeypatch.setattr(
        "research_hub.notebooklm.cdp_launcher.find_chrome_binary",
        lambda: None,
    )

    assert (
        init_wizard.run_init(
            vault_root=str(tmp_path / "vault"),
            zotero_key="secret",
            zotero_library_id="123",
            non_interactive=True,
        )
        == 0
    )
    assert (
        init_wizard.run_init(
            vault_root=str(tmp_path / "vault"),
            zotero_key="secret",
            zotero_library_id="123",
            non_interactive=True,
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "Zotero credentials: OK" in output
    assert "returned 403" in output


def test_init_zotero_validation_failure(tmp_path, monkeypatch, capsys):
    from research_hub import init_wizard

    config_dir = tmp_path / "config"
    monkeypatch.setattr(
        init_wizard.platformdirs,
        "user_config_dir",
        lambda *args, **kwargs: str(config_dir),
    )
    monkeypatch.setattr(
        "requests.head",
        lambda *args, **kwargs: (_ for _ in ()).throw(ConnectionError("boom")),
    )
    monkeypatch.setattr(
        "research_hub.notebooklm.cdp_launcher.find_chrome_binary",
        lambda: None,
    )

    assert (
        init_wizard.run_init(
            vault_root=str(tmp_path / "vault"),
            zotero_key="secret",
            zotero_library_id="123",
            non_interactive=True,
        )
        == 0
    )
    assert "could not reach api.zotero.org" in capsys.readouterr().out


def test_init_chrome_detected(tmp_path, monkeypatch, capsys):
    from research_hub import init_wizard

    config_dir = tmp_path / "config"
    monkeypatch.setattr(
        init_wizard.platformdirs,
        "user_config_dir",
        lambda *args, **kwargs: str(config_dir),
    )
    monkeypatch.setattr(
        init_wizard,
        "_check_first_run_readiness",
        lambda vault, *, persona, has_zotero: [
            ("chrome", "OK", "patchright can launch Chrome (channel='chrome')"),
        ],
    )

    assert init_wizard.run_init(vault_root=str(tmp_path / "vault"), non_interactive=True) == 0
    out = capsys.readouterr().out
    assert "First-run readiness check" in out
    assert "chrome" in out and "OK" in out


def test_init_chrome_not_found(tmp_path, monkeypatch, capsys):
    from research_hub import init_wizard

    config_dir = tmp_path / "config"
    monkeypatch.setattr(
        init_wizard.platformdirs,
        "user_config_dir",
        lambda *args, **kwargs: str(config_dir),
    )
    monkeypatch.setattr(
        init_wizard,
        "_check_first_run_readiness",
        lambda vault, *, persona, has_zotero: [
            ("chrome", "WARN", "patchright cannot launch Chrome: no chrome binary found"),
        ],
    )

    assert init_wizard.run_init(vault_root=str(tmp_path / "vault"), non_interactive=True) == 0
    out = capsys.readouterr().out
    assert "First-run readiness check" in out
    assert "WARN" in out and "patchright cannot launch Chrome" in out


def test_init_idempotent(tmp_path, monkeypatch):
    from research_hub import init_wizard

    vault = tmp_path / "vault"
    config_dir = tmp_path / "config"
    monkeypatch.setattr(
        init_wizard.platformdirs,
        "user_config_dir",
        lambda *args, **kwargs: str(config_dir),
    )
    monkeypatch.setattr(
        "research_hub.notebooklm.cdp_launcher.find_chrome_binary",
        lambda: None,
    )

    assert init_wizard.run_init(vault_root=str(vault), non_interactive=True) == 0
    assert init_wizard.run_init(vault_root=str(vault), non_interactive=True) == 0

    config = json.loads((config_dir / "config.json").read_text(encoding="utf-8"))
    assert config["knowledge_base"]["root"] == str(vault.resolve())
