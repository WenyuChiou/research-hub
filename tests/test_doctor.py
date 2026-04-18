"""Tests for the research-hub doctor command."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def isolated_config_resolution(tmp_path, monkeypatch):
    from research_hub import config as hub_config

    hub_config._config = None
    hub_config._config_path = None
    monkeypatch.delenv("RESEARCH_HUB_CONFIG", raising=False)
    monkeypatch.delenv("RESEARCH_HUB_ROOT", raising=False)
    monkeypatch.delenv("RESEARCH_HUB_RAW", raising=False)
    monkeypatch.delenv("RESEARCH_HUB_HUB", raising=False)
    monkeypatch.delenv("RESEARCH_HUB_PROJECTS", raising=False)
    monkeypatch.delenv("RESEARCH_HUB_LOGS", raising=False)
    monkeypatch.delenv("RESEARCH_HUB_GRAPH", raising=False)
    monkeypatch.delenv("ZOTERO_API_KEY", raising=False)
    monkeypatch.delenv("ZOTERO_LIBRARY_ID", raising=False)
    monkeypatch.delenv("ZOTERO_LIBRARY_TYPE", raising=False)
    monkeypatch.delenv("RESEARCH_HUB_DEFAULT_COLLECTION", raising=False)
    monkeypatch.setattr(hub_config, "CONFIG_PATH", tmp_path / "missing-legacy-config.json")
    monkeypatch.setattr(
        hub_config.platformdirs,
        "user_config_dir",
        lambda *args, **kwargs: str(tmp_path / "missing-platformdirs"),
    )
    yield
    hub_config._config = None
    hub_config._config_path = None


def _write_config(tmp_path, monkeypatch, *, root_exists=True, zotero_key="secret", library_id="123"):
    from research_hub import config as hub_config

    root = tmp_path / "vault"
    if root_exists:
        root.mkdir(parents=True)
        (root / "raw").mkdir()
        (root / ".research_hub").mkdir()
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "knowledge_base": {"root": str(root)},
                "persona": "researcher",
                "zotero": {
                    "api_key": zotero_key,
                    "library_id": library_id,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(hub_config.platformdirs, "user_config_dir", lambda *args, **kwargs: str(tmp_path))
    return root, config_path


def test_doctor_all_green(tmp_path, monkeypatch, capsys):
    from research_hub.doctor import print_doctor_report, run_doctor
    from research_hub.security.secret_box import encrypt

    root, config_path = _write_config(tmp_path, monkeypatch)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["zotero"]["api_key"] = encrypt("secret", config_path.parent)
    config_path.write_text(json.dumps(config), encoding="utf-8")
    dedup = root / ".research_hub" / "dedup_index.json"
    dedup.write_text(
        json.dumps({"doi_to_hits": {"a": [{}], "b": [{}]}, "title_to_hits": {"t": [{}]}}),
        encoding="utf-8",
    )
    session_dir = root / ".research_hub" / "nlm_sessions" / "default"
    session_dir.mkdir(parents=True)
    (session_dir / "state.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr("requests.head", lambda *args, **kwargs: SimpleNamespace(status_code=200))
    monkeypatch.setattr(
        "research_hub.notebooklm.cdp_launcher.find_chrome_binary",
        lambda: "C:/Chrome/chrome.exe",
    )

    results = run_doctor()

    assert all(result.status == "OK" for result in results)
    assert any(
        result.name == "dedup_index" and result.message == "2 DOIs, 1 titles" for result in results
    )
    assert print_doctor_report(results) == 0
    assert "[OK] config:" in capsys.readouterr().out


def test_doctor_missing_config(monkeypatch):
    from research_hub.doctor import print_doctor_report, run_doctor

    monkeypatch.setattr(
        "research_hub.notebooklm.cdp_launcher.find_chrome_binary",
        lambda: None,
    )

    results = run_doctor()

    assert any(result.name == "config" and result.status == "FAIL" for result in results)
    assert print_doctor_report(results) == 1


def test_doctor_missing_vault(tmp_path, monkeypatch):
    from research_hub.doctor import run_doctor

    _write_config(tmp_path, monkeypatch)
    missing_root = tmp_path / "missing-vault"
    monkeypatch.setattr(
        "research_hub.config.get_config",
        lambda: SimpleNamespace(
            root=missing_root,
            research_hub_dir=missing_root / ".research_hub",
        ),
    )
    monkeypatch.setattr(
        "research_hub.notebooklm.cdp_launcher.find_chrome_binary",
        lambda: None,
    )

    results = run_doctor()

    assert any(result.name == "vault" and result.status == "FAIL" for result in results)


def test_doctor_no_zotero_key(tmp_path, monkeypatch):
    from research_hub.doctor import run_doctor

    _write_config(tmp_path, monkeypatch, zotero_key=None)
    monkeypatch.setattr(
        "research_hub.notebooklm.cdp_launcher.find_chrome_binary",
        lambda: None,
    )
    # Isolate from the user's real legacy zotero-skills config
    monkeypatch.setattr(
        "research_hub.zotero.client._load_legacy_zotero_skill_config",
        lambda: {},
    )

    results = run_doctor()

    assert any(result.name == "zotero_key" and result.status == "FAIL" for result in results)


def test_doctor_zotero_unreachable(tmp_path, monkeypatch):
    from research_hub.doctor import run_doctor

    _write_config(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "requests.head",
        lambda *args, **kwargs: (_ for _ in ()).throw(ConnectionError("boom")),
    )
    monkeypatch.setattr(
        "research_hub.notebooklm.cdp_launcher.find_chrome_binary",
        lambda: None,
    )

    results = run_doctor()

    assert any(result.name == "zotero_api" and result.status == "WARN" for result in results)


def test_doctor_chrome_not_found(tmp_path, monkeypatch):
    from research_hub.doctor import run_doctor

    _write_config(tmp_path, monkeypatch)
    monkeypatch.setattr("requests.head", lambda *args, **kwargs: SimpleNamespace(status_code=200))
    monkeypatch.setattr(
        "research_hub.notebooklm.cdp_launcher.find_chrome_binary",
        lambda: None,
    )

    results = run_doctor()

    assert any(result.name == "chrome" and result.status == "WARN" for result in results)


def test_doctor_no_nlm_session(tmp_path, monkeypatch):
    from research_hub.doctor import run_doctor

    _write_config(tmp_path, monkeypatch)
    monkeypatch.setattr("requests.head", lambda *args, **kwargs: SimpleNamespace(status_code=200))
    monkeypatch.setattr(
        "research_hub.notebooklm.cdp_launcher.find_chrome_binary",
        lambda: "C:/Chrome/chrome.exe",
    )

    results = run_doctor()

    assert any(result.name == "nlm_session" and result.status == "WARN" for result in results)


def test_doctor_exit_code_zero_if_only_warns(tmp_path, monkeypatch):
    from research_hub.doctor import print_doctor_report, run_doctor

    root, _ = _write_config(tmp_path, monkeypatch)
    monkeypatch.setenv("ZOTERO_API_KEY", "secret")
    monkeypatch.setenv("ZOTERO_LIBRARY_ID", "123")
    monkeypatch.setattr("requests.head", lambda *args, **kwargs: SimpleNamespace(status_code=403))
    monkeypatch.setattr(
        "research_hub.notebooklm.cdp_launcher.find_chrome_binary",
        lambda: None,
    )
    # Keep config OK and vault OK, but allow WARN checks for dedup/chrome/session/api.
    assert root.exists()

    results = run_doctor()

    assert all(result.status != "FAIL" for result in results)
    assert print_doctor_report(results) == 0
