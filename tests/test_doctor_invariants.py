"""Cross-system invariant check tests."""

from __future__ import annotations

import json
from types import SimpleNamespace

from research_hub.doctor import run_doctor


def _write_config(tmp_path, monkeypatch, *, no_zotero: bool = False):
    from research_hub import config as hub_config

    root = tmp_path / "vault"
    root.mkdir(parents=True)
    (root / "raw").mkdir()
    (root / ".research_hub").mkdir()
    config_path = tmp_path / "config.json"
    payload = {
        "knowledge_base": {"root": str(root)},
        "zotero": {"api_key": "secret", "library_id": "123"},
    }
    if no_zotero:
        payload["no_zotero"] = True
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    hub_config._config = None
    hub_config._config_path = None
    monkeypatch.setattr(
        hub_config.platformdirs,
        "user_config_dir",
        lambda *args, **kwargs: str(tmp_path),
    )
    monkeypatch.setattr(
        "research_hub.notebooklm.cdp_launcher.find_chrome_binary",
        lambda: "C:/Chrome/chrome.exe",
    )
    return root


def _dedup_payload(path: str) -> dict:
    return {
        "doi_to_hits": {},
        "title_to_hits": {
            "paper title": [
                {
                    "source": "obsidian",
                    "doi": "10.1000/test",
                    "title": "Paper Title",
                    "obsidian_path": path,
                }
            ]
        },
    }


def test_doctor_dedup_consistency_passes_when_paths_exist(tmp_path, monkeypatch):
    root = _write_config(tmp_path, monkeypatch)
    note = root / "raw" / "paper.md"
    note.write_text("---\ntitle: x\n---\n", encoding="utf-8")
    (root / ".research_hub" / "dedup_index.json").write_text(
        json.dumps(_dedup_payload(str(note))),
        encoding="utf-8",
    )
    monkeypatch.setattr("requests.head", lambda *args, **kwargs: SimpleNamespace(status_code=200))

    results = run_doctor()

    check = next(result for result in results if result.name == "dedup_consistency")
    assert check.status == "OK"
    assert "all valid" in check.message


def test_doctor_dedup_consistency_warns_on_stale_paths(tmp_path, monkeypatch):
    root = _write_config(tmp_path, monkeypatch)
    stale = root / "raw" / "missing.md"
    (root / ".research_hub" / "dedup_index.json").write_text(
        json.dumps(_dedup_payload(str(stale))),
        encoding="utf-8",
    )
    monkeypatch.setattr("requests.head", lambda *args, **kwargs: SimpleNamespace(status_code=200))

    results = run_doctor()

    check = next(result for result in results if result.name == "dedup_consistency")
    assert check.status == "WARN"
    assert "stale" in check.message


def test_doctor_vault_invariant_no_zotero_config(tmp_path, monkeypatch):
    root = _write_config(tmp_path, monkeypatch, no_zotero=True)
    (root / ".research_hub" / "dedup_index.json").write_text(
        json.dumps({"doi_to_hits": {}, "title_to_hits": {}}),
        encoding="utf-8",
    )

    results = run_doctor()

    check = next(result for result in results if result.name == "vault_invariant")
    assert check.status == "OK"
    assert "Skipped" in check.message


def test_doctor_vault_invariant_detects_stale_zotero_keys(tmp_path, monkeypatch):
    root = _write_config(tmp_path, monkeypatch)
    note = root / "raw" / "paper.md"
    note.write_text("---\nzotero-key: ABC123\n---\n", encoding="utf-8")

    def fake_head(url, *args, **kwargs):
        if url.endswith("/items?limit=1"):
            return SimpleNamespace(status_code=200)
        if url.endswith("/items/ABC123"):
            return SimpleNamespace(status_code=404)
        return SimpleNamespace(status_code=200)

    monkeypatch.setattr("requests.head", fake_head)

    results = run_doctor()

    check = next(result for result in results if result.name == "vault_invariant")
    assert check.status == "WARN"
    assert "deleted Zotero items" in check.message


def test_doctor_invariant_skips_large_vaults(tmp_path, monkeypatch):
    """With > 50 zotero-keyed notes, vault_invariant should report OK
    (not WARN) — skipping the probe is a rate-safety feature, not a
    problem the user needs to fix."""
    root = _write_config(tmp_path, monkeypatch)
    for index in range(60):
        (root / "raw" / f"paper-{index}.md").write_text(
            f"---\nzotero-key: KEY{index}\n---\n",
            encoding="utf-8",
        )

    results = run_doctor()

    check = next(result for result in results if result.name == "vault_invariant")
    assert check.status == "OK"
    assert "probe capped" in check.message or "probe skipped" in check.message


def test_doctor_reports_dedup_consistency_when_index_missing(tmp_path, monkeypatch):
    _write_config(tmp_path, monkeypatch, no_zotero=True)

    results = run_doctor()

    check = next(result for result in results if result.name == "dedup_consistency")
    assert check.status == "OK"
    assert "Skipped" in check.message
