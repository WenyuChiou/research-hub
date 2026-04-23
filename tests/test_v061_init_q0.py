from __future__ import annotations

import json
from types import SimpleNamespace

from research_hub.security.secret_box import decrypt, is_encrypted


def _patch_init(monkeypatch, init_wizard, tmp_path):
    config_dir = tmp_path / "config"
    monkeypatch.setattr(init_wizard.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(
        init_wizard.platformdirs,
        "user_config_dir",
        lambda *args, **kwargs: str(config_dir),
    )
    monkeypatch.setattr(
        init_wizard,
        "_check_first_run_readiness",
        lambda vault, *, persona, has_zotero: [("chrome", "INFO", "not checked")],
    )
    return config_dir


def test_q0_no_routes_to_analyst_or_internal(tmp_path, monkeypatch):
    from research_hub import init_wizard

    config_dir = _patch_init(monkeypatch, init_wizard, tmp_path)
    answers = iter(["n", "1"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    assert init_wizard.run_init(vault_root=str(tmp_path / "vault")) == 0

    config = json.loads((config_dir / "config.json").read_text(encoding="utf-8"))
    assert config["persona"] == "analyst"
    assert config["no_zotero"] is True


def test_q0_yes_keeps_zotero_branch(tmp_path, monkeypatch):
    from research_hub import init_wizard

    config_dir = _patch_init(monkeypatch, init_wizard, tmp_path)
    answers = iter(["y", "1", "z-key", "123"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    monkeypatch.setattr("requests.head", lambda *args, **kwargs: SimpleNamespace(status_code=200))

    assert init_wizard.run_init(vault_root=str(tmp_path / "vault")) == 0

    config = json.loads((config_dir / "config.json").read_text(encoding="utf-8"))
    assert config["persona"] == "researcher"
    assert "no_zotero" not in config
    assert is_encrypted(config["zotero"]["api_key"])
    assert decrypt(config["zotero"]["api_key"], config_dir) == "z-key"
    assert config["zotero"]["library_id"] == "123"
