from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from research_hub.doi_lookup import batch_lookup_missing_dois, lookup_doi_for_slug
from research_hub.paper import _parse_frontmatter


def _cfg(tmp_path: Path) -> SimpleNamespace:
    root = tmp_path / "vault"
    raw = root / "raw"
    raw.mkdir(parents=True)
    return SimpleNamespace(root=root, raw=raw)


def _write_note(path: Path, doi: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        'title: "Behavioral Theory of the Firm"\n'
        'authors: "Cyert, Richard"\n'
        'year: "1963"\n'
        f'doi: "{doi}"\n'
        'topic_cluster: "agents"\n'
        "---\n\nBody\n",
        encoding="utf-8",
    )


def test_lookup_doi_single_writes_frontmatter(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    note = cfg.raw / "agents" / "behavioral-theory.md"
    _write_note(note)

    class FakeCrossref:
        def search(self, query, limit=5):
            return [
                SimpleNamespace(
                    title="Behavioral Theory of the Firm",
                    doi="10.1000/behavioral",
                    year=1963,
                )
            ]

    monkeypatch.setattr("builtins.input", lambda prompt="": "y")

    result = lookup_doi_for_slug(cfg, "behavioral-theory", crossref=FakeCrossref())
    meta = _parse_frontmatter(note.read_text(encoding="utf-8"))

    assert result["status"] == "updated"
    assert meta["doi"] == "10.1000/behavioral"


def test_lookup_doi_batch_skips_existing_dois(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    missing = cfg.raw / "agents" / "missing-doi.md"
    existing = cfg.raw / "agents" / "has-doi.md"
    _write_note(missing)
    _write_note(existing, doi="10.1000/already")

    class FakeCrossref:
        def search(self, query, limit=5):
            return [SimpleNamespace(title="Behavioral Theory of the Firm", doi="10.1000/behavioral", year=1963)]

    monkeypatch.setattr("research_hub.doi_lookup.CrossrefBackend", lambda delay_seconds=1.0: FakeCrossref())
    monkeypatch.setattr("research_hub.doi_lookup.time.sleep", lambda seconds: None)

    result = batch_lookup_missing_dois(cfg, "agents")
    log = json.loads((cfg.raw / "agents" / "lookup_log.json").read_text(encoding="utf-8"))

    assert any(item["slug"] == "has-doi" and item["status"] == "skipped" for item in log)
    assert any(item["slug"] == "missing-doi" and item["status"] == "updated" for item in log)
    assert result["log_path"].endswith("lookup_log.json")
