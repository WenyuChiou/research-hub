"""v0.38 init wizard 4-persona prompt tests."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from tests._persona_factory import make_persona_vault


@pytest.mark.parametrize("persona", ["researcher", "humanities", "analyst", "internal"])
def test_init_accepts_persona_flag(tmp_path, monkeypatch, persona):
    from research_hub import init_wizard

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

    rc = init_wizard.run_init(
        vault_root=str(tmp_path / "vault"),
        zotero_key="secret" if persona in {"researcher", "humanities"} else None,
        zotero_library_id="123" if persona in {"researcher", "humanities"} else None,
        persona=persona,
        non_interactive=True,
    )

    assert rc == 0
    data = json.loads((config_dir / "config.json").read_text(encoding="utf-8"))
    assert data.get("persona") == persona
    assert data.get("no_zotero", False) is (persona in {"analyst", "internal"})


def test_init_legacy_no_zotero_implies_analyst(tmp_path, monkeypatch):
    cfg, _ = make_persona_vault(tmp_path, persona="A")
    monkeypatch.setattr(cfg, "persona", "", raising=False)
    monkeypatch.setattr(cfg, "no_zotero", True, raising=False)
    monkeypatch.delenv("RESEARCH_HUB_PERSONA", raising=False)
    monkeypatch.delenv("RESEARCH_HUB_NO_ZOTERO", raising=False)
    from research_hub.dashboard.data import _detect_persona

    assert _detect_persona(cfg, None) == "analyst"


def test_doctor_warns_when_persona_unset(tmp_path, monkeypatch):
    cfg, _ = make_persona_vault(tmp_path, persona="A")
    monkeypatch.setattr(cfg, "persona", "", raising=False)
    monkeypatch.setattr(cfg, "no_zotero", False, raising=False)
    from research_hub.doctor import check_persona_set

    result = check_persona_set(cfg)
    assert result.status == "WARN"
    assert "init --persona" in (result.remedy or "")


def test_doctor_ok_when_persona_set(tmp_path, monkeypatch):
    cfg, _ = make_persona_vault(tmp_path, persona="A")
    monkeypatch.setattr(cfg, "persona", "humanities", raising=False)
    from research_hub.doctor import check_persona_set

    result = check_persona_set(cfg)
    assert result.status == "OK"
    assert "humanities" in result.message


def test_init_persona_flag_invalid_value_rejected(tmp_path, monkeypatch):
    from research_hub.cli import build_parser

    with pytest.raises(SystemExit):
        build_parser().parse_args(["init", "--persona", "alien_value"])
