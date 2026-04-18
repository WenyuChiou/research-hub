"""Tests for init and doctor persona handling."""

from __future__ import annotations

import json

from research_hub.security.secret_box import decrypt, is_encrypted


def test_init_analyst_persona_skips_zotero(tmp_path, monkeypatch):
    from research_hub.init_wizard import run_init

    config_dir = tmp_path / "cfg"
    monkeypatch.setattr(
        "research_hub.init_wizard.platformdirs.user_config_dir",
        lambda *args, **kwargs: str(config_dir),
    )
    monkeypatch.setattr("research_hub.notebooklm.cdp_launcher.find_chrome_binary", lambda: None)

    assert run_init(vault_root=str(tmp_path / "vault"), non_interactive=True, persona="analyst") == 0
    config = json.loads((config_dir / "config.json").read_text(encoding="utf-8"))
    assert config["no_zotero"] is True
    assert "zotero" not in config


def test_init_analyst_non_interactive_no_zotero_key_required(tmp_path, monkeypatch):
    from research_hub.init_wizard import run_init

    monkeypatch.setattr(
        "research_hub.init_wizard.platformdirs.user_config_dir",
        lambda *args, **kwargs: str(tmp_path / "cfg"),
    )
    monkeypatch.setattr("research_hub.notebooklm.cdp_launcher.find_chrome_binary", lambda: None)

    assert run_init(vault_root=str(tmp_path / "vault"), non_interactive=True, persona="analyst") == 0


def test_init_researcher_persona_default(tmp_path, monkeypatch):
    from research_hub.init_wizard import run_init

    config_dir = tmp_path / "cfg"
    monkeypatch.setattr(
        "research_hub.init_wizard.platformdirs.user_config_dir",
        lambda *args, **kwargs: str(config_dir),
    )
    monkeypatch.setattr("research_hub.notebooklm.cdp_launcher.find_chrome_binary", lambda: None)

    assert run_init(
        vault_root=str(tmp_path / "vault"),
        zotero_key="secret",
        zotero_library_id="123",
        non_interactive=True,
    ) == 0
    config = json.loads((config_dir / "config.json").read_text(encoding="utf-8"))
    assert is_encrypted(config["zotero"]["api_key"])
    assert decrypt(config["zotero"]["api_key"], config_dir) == "secret"
    assert config["zotero"]["library_id"] == "123"
    assert "no_zotero" not in config


def test_doctor_skips_zotero_when_no_zotero_config(tmp_path, monkeypatch):
    from research_hub.doctor import run_doctor

    root = tmp_path / "vault"
    (root / "raw").mkdir(parents=True)
    (root / ".research_hub").mkdir()
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(
        json.dumps({"knowledge_base": {"root": str(root)}, "no_zotero": True}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "research_hub.config.platformdirs.user_config_dir",
        lambda *args, **kwargs: str(config_dir),
    )
    monkeypatch.setattr("research_hub.notebooklm.cdp_launcher.find_chrome_binary", lambda: None)

    result = next(item for item in run_doctor() if item.name == "zotero_key")
    assert result.status == "OK"
    assert result.message == "Skipped (analyst mode)"


def test_doctor_skips_zotero_when_env_var_set(tmp_path, monkeypatch):
    from research_hub.doctor import run_doctor

    root = tmp_path / "vault"
    (root / "raw").mkdir(parents=True)
    (root / ".research_hub").mkdir()
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(
        json.dumps({"knowledge_base": {"root": str(root)}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "research_hub.config.platformdirs.user_config_dir",
        lambda *args, **kwargs: str(config_dir),
    )
    monkeypatch.setattr("research_hub.notebooklm.cdp_launcher.find_chrome_binary", lambda: None)
    monkeypatch.setenv("RESEARCH_HUB_NO_ZOTERO", "1")

    result = next(item for item in run_doctor() if item.name == "zotero_key")
    assert result.status == "OK"
    assert result.message == "Skipped (analyst mode)"
