from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from research_hub.dedup import DedupHit, DedupIndex
from research_hub.pipeline_repair import repair_cluster


def _cfg(tmp_path: Path) -> SimpleNamespace:
    research_hub_dir = tmp_path / ".research_hub"
    research_hub_dir.mkdir()
    clusters_file = research_hub_dir / "clusters.yaml"
    clusters_file.write_text(
        json.dumps(
            {
                "clusters": {
                    "llm-agents": {
                        "name": "LLM Agents",
                        "zotero_collection_key": "COLL1",
                        "obsidian_subfolder": "llm-agents",
                        "first_query": "llm agents",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return SimpleNamespace(
        raw=tmp_path / "raw",
        research_hub_dir=research_hub_dir,
        clusters_file=clusters_file,
    )


def _write_note(path: Path, *, title: str, doi: str, zotero_key: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        (
            "---\n"
            f'title: "{title}"\n'
            f'doi: "{doi}"\n'
            f'zotero-key: "{zotero_key}"\n'
            f'topic_cluster: "llm-agents"\n'
            "---\n\n"
            f"# {title}\n"
        ),
        encoding="utf-8",
    )


def _zot_item(doi: str, key: str = "Z1", title: str = "Paper") -> dict:
    return {
        "key": key,
        "data": {
            "DOI": doi,
            "title": title,
            "itemType": "journalArticle",
            "creators": [{"creatorType": "author", "lastName": "Doe", "firstName": "Jane"}],
            "date": "2024",
            "publicationTitle": "Journal",
            "abstractNote": "Abstract",
            "tags": [],
        },
    }


class _FakeDual:
    def __init__(self, items_by_collection: dict[str, list[dict]]):
        self.web = self
        self.items_by_collection = items_by_collection

    def collection_items(self, collection_key: str, start: int = 0, limit: int = 100, itemType: str = ""):
        items = self.items_by_collection.get(collection_key, [])
        return items[start : start + limit]


def test_repair_dry_run_reports_zotero_orphans(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(
        "research_hub.zotero.client.ZoteroDualClient",
        lambda: _FakeDual({"COLL1": [_zot_item("10.1/a")]}),
    )

    report = repair_cluster(cfg, "llm-agents", dry_run=True)

    assert len(report.zotero_orphans) == 1
    assert report.created_notes == []


def test_repair_dry_run_reports_obsidian_orphans(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    _write_note(cfg.raw / "llm-agents" / "orphan.md", title="Orphan", doi="10.1/orphan")
    monkeypatch.setattr(
        "research_hub.zotero.client.ZoteroDualClient",
        lambda: _FakeDual({"COLL1": []}),
    )

    report = repair_cluster(cfg, "llm-agents", dry_run=True)

    assert len(report.obsidian_orphans) == 1
    assert report.obsidian_orphans[0].endswith("orphan.md")


def test_repair_dry_run_reports_stale_dedup_entries(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    index = DedupIndex()
    index.add(DedupHit(source="obsidian", doi="10.1/stale", title="Stale", obsidian_path="missing.md"))
    index.save(cfg.research_hub_dir / "dedup_index.json")
    monkeypatch.setattr(
        "research_hub.zotero.client.ZoteroDualClient",
        lambda: _FakeDual({"COLL1": []}),
    )

    report = repair_cluster(cfg, "llm-agents", dry_run=True)

    assert report.stale_dedup == ["10.1/stale"]


def test_repair_execute_creates_missing_obsidian_notes(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(
        "research_hub.zotero.client.ZoteroDualClient",
        lambda: _FakeDual({"COLL1": [_zot_item("10.1/a", key="Z1", title="Recovered Paper")]}),
    )

    report = repair_cluster(cfg, "llm-agents", dry_run=False)

    assert len(report.created_notes) == 1
    created = Path(report.created_notes[0])
    assert created.exists()
    assert "Recovered Paper" in created.read_text(encoding="utf-8")
    reloaded = DedupIndex.load(cfg.research_hub_dir / "dedup_index.json")
    assert "10.1/a" in reloaded.doi_to_hits


def test_repair_execute_prunes_stale_dedup_entries(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    index = DedupIndex()
    index.add(DedupHit(source="obsidian", doi="10.1/stale", title="Stale", obsidian_path="missing.md"))
    index.save(cfg.research_hub_dir / "dedup_index.json")
    monkeypatch.setattr(
        "research_hub.zotero.client.ZoteroDualClient",
        lambda: _FakeDual({"COLL1": []}),
    )

    report = repair_cluster(cfg, "llm-agents", dry_run=False)
    reloaded = DedupIndex.load(cfg.research_hub_dir / "dedup_index.json")

    assert report.stale_dedup == ["10.1/stale"]
    assert reloaded.doi_to_hits == {}


def test_repair_clean_cluster_reports_zero_orphans(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    _write_note(cfg.raw / "llm-agents" / "paper.md", title="Paper", doi="10.1/a", zotero_key="Z1")
    monkeypatch.setattr(
        "research_hub.zotero.client.ZoteroDualClient",
        lambda: _FakeDual({"COLL1": [_zot_item("10.1/a", key="Z1", title="Paper")]}),
    )

    report = repair_cluster(cfg, "llm-agents", dry_run=True)

    assert report.zotero_orphans == []
    assert report.obsidian_orphans == []
    assert report.stale_dedup == []
