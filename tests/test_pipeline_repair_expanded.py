from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from research_hub.dedup import DedupHit, DedupIndex
from research_hub.pipeline_repair import repair_cluster


def _cfg(tmp_path: Path, slug: str = "llm-agents", *, zotero_key: str = "COLL1") -> SimpleNamespace:
    research_hub_dir = tmp_path / ".research_hub"
    research_hub_dir.mkdir()
    clusters_file = research_hub_dir / "clusters.yaml"
    clusters_file.write_text(
        json.dumps(
            {
                "clusters": {
                    slug: {
                        "name": slug.replace("-", " ").title(),
                        "zotero_collection_key": zotero_key,
                        "obsidian_subfolder": slug,
                        "first_query": slug.replace("-", " "),
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return SimpleNamespace(raw=tmp_path / "raw", research_hub_dir=research_hub_dir, clusters_file=clusters_file)


def _write_note(path: Path, *, title: str, doi: str, topic_cluster: str, zotero_key: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        (
            "---\n"
            f'title: "{title}"\n'
            f'doi: "{doi}"\n'
            f'zotero-key: "{zotero_key}"\n'
            f'topic_cluster: "{topic_cluster}"\n'
            "---\n\n"
            f"# {title}\n"
        ),
        encoding="utf-8",
    )


def _zot_item(doi: str, key: str, title: str) -> dict:
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
        del itemType
        items = self.items_by_collection.get(collection_key, [])
        return items[start : start + limit]


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_repair_detects_obsidian_orphan(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    _write_note(cfg.raw / "llm-agents" / "matched.md", title="Matched", doi="10.1/a", topic_cluster="llm-agents")
    _write_note(cfg.raw / "llm-agents" / "orphan.md", title="Orphan", doi="10.1/orphan", topic_cluster="llm-agents")
    monkeypatch.setattr(
        "research_hub.zotero.client.ZoteroDualClient",
        lambda: _FakeDual({"COLL1": [_zot_item("10.1/a", "Z1", "Matched")]}),
    )

    report = repair_cluster(cfg, "llm-agents", dry_run=True)

    assert any(path.endswith("orphan.md") for path in report.obsidian_orphans)


def test_repair_detects_zotero_orphan(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    _write_note(cfg.raw / "llm-agents" / "matched.md", title="Matched", doi="10.1/a", topic_cluster="llm-agents")
    monkeypatch.setattr(
        "research_hub.zotero.client.ZoteroDualClient",
        lambda: _FakeDual({"COLL1": [_zot_item("10.1/a", "Z1", "Matched"), _zot_item("10.1/b", "Z2", "Missing")]}),
    )

    report = repair_cluster(cfg, "llm-agents", dry_run=True)

    assert [item["doi"] for item in report.zotero_orphans] == ["10.1/b"]


def test_repair_dry_run_writes_nothing(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    _write_note(cfg.raw / "llm-agents" / "paper.md", title="Paper", doi="10.1/a", topic_cluster="llm-agents")
    before = _tree_hash(tmp_path)
    monkeypatch.setattr("research_hub.zotero.client.ZoteroDualClient", lambda: _FakeDual({"COLL1": []}))

    repair_cluster(cfg, "llm-agents", dry_run=True)

    assert _tree_hash(tmp_path) == before


def test_repair_execute_creates_missing_note_from_zotero(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(
        "research_hub.zotero.client.ZoteroDualClient",
        lambda: _FakeDual({"COLL1": [_zot_item("10.1/new", "Z1", "Recovered Paper")]}),
    )

    report = repair_cluster(cfg, "llm-agents", dry_run=False)

    created = Path(report.created_notes[0])
    text = created.read_text(encoding="utf-8")
    assert created.exists()
    assert 'title: "Recovered Paper"' in text
    assert 'topic_cluster: "llm-agents"' in text


def test_repair_prunes_stale_dedup_paths(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    index = DedupIndex.empty()
    stale = str(cfg.raw / "llm-agents" / "gone.md")
    index.add(DedupHit(source="obsidian", doi="10.1/stale", title="Stale Title For Index", obsidian_path=stale))
    index.save(cfg.research_hub_dir / "dedup_index.json")
    monkeypatch.setattr("research_hub.zotero.client.ZoteroDualClient", lambda: _FakeDual({"COLL1": []}))

    repair_cluster(cfg, "llm-agents", dry_run=False)
    reloaded = DedupIndex.load(cfg.research_hub_dir / "dedup_index.json")

    assert all(hit.obsidian_path != stale for hits in reloaded.doi_to_hits.values() for hit in hits)


def test_repair_handles_renamed_cluster(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, slug="new-name", zotero_key="COLL2")
    _write_note(cfg.raw / "new-name" / "paper.md", title="Paper", doi="10.1/a", topic_cluster="old-name")
    monkeypatch.setattr("research_hub.zotero.client.ZoteroDualClient", lambda: _FakeDual({"COLL2": []}))

    report = repair_cluster(cfg, "new-name", dry_run=True)

    assert any(path.endswith("paper.md") for path in report.folder_mismatches)


def test_repair_reports_duplicate_doi_across_clusters(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    index = DedupIndex.empty()
    index.add(DedupHit(source="zotero", doi="10.1/dup", title="Duplicate Title Enough"))
    index.add(
        DedupHit(
            source="obsidian",
            doi="10.1/dup",
            title="Duplicate Title Enough",
            obsidian_path=str(cfg.raw / "llm-agents" / "a.md"),
        )
    )
    index.add(
        DedupHit(
            source="obsidian",
            doi="10.1/dup",
            title="Duplicate Title Enough",
            obsidian_path=str(cfg.raw / "policy" / "b.md"),
        )
    )
    index.save(cfg.research_hub_dir / "dedup_index.json")
    monkeypatch.setattr("research_hub.zotero.client.ZoteroDualClient", lambda: _FakeDual({"COLL1": []}))

    report = repair_cluster(cfg, "llm-agents", dry_run=True)

    assert report.duplicate_dois == [{"doi": "10.1/dup", "clusters": ["llm-agents", "policy"]}]


def test_repair_logs_all_actions_to_manifest(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    index = DedupIndex.empty()
    index.add(
        DedupHit(
            source="obsidian",
            doi="10.1/stale",
            title="Stale Title For Index",
            obsidian_path=str(cfg.raw / "llm-agents" / "gone.md"),
        )
    )
    index.save(cfg.research_hub_dir / "dedup_index.json")
    monkeypatch.setattr(
        "research_hub.zotero.client.ZoteroDualClient",
        lambda: _FakeDual({"COLL1": [_zot_item("10.1/new", "Z1", "Recovered Paper")]}),
    )

    repair_cluster(cfg, "llm-agents", dry_run=False)

    lines = [json.loads(line) for line in (cfg.research_hub_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(entry["action"].startswith("repair_") for entry in lines)
