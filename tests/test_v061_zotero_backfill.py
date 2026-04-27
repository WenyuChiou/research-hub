from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from research_hub.dedup import DedupHit, DedupIndex
from research_hub.zotero_hygiene import run_backfill


def _cfg(tmp_path: Path, clusters: dict | None = None) -> SimpleNamespace:
    research_hub_dir = tmp_path / ".research_hub"
    research_hub_dir.mkdir()
    clusters_file = research_hub_dir / "clusters.yaml"
    clusters_file.write_text(
        json.dumps({"clusters": clusters or {"agents": {"name": "Agents", "zotero_collection_key": "C1"}}}),
        encoding="utf-8",
    )
    return SimpleNamespace(
        research_hub_dir=research_hub_dir,
        run_dir=research_hub_dir,
        clusters_file=clusters_file,
        dedup_index_path=research_hub_dir / "dedup_index.json",
    )


def _item(tags: list[str] | None = None, doi: str = "10.1/a", key: str = "I1") -> dict:
    return {
        "key": key,
        "data": {
            "key": key,
            "itemType": "journalArticle",
            "title": "Paper",
            "DOI": doi,
            "tags": [{"tag": tag} for tag in (tags or [])],
        },
    }


class FakeZotero:
    def __init__(self, items: list[dict], children: list[dict] | None = None):
        self.items = items
        self.child_items = children if children is not None else []
        self.updated: list[dict] = []
        self.created: list[dict] = []

    def collection_items(self, collection_key, start=0, limit=100, itemType=""):
        return self.items[start : start + limit]

    def update_item(self, data):
        self.updated.append(data.copy())
        return {"successful": {"0": {"key": data.get("key", "")}}}

    def children(self, key):
        return self.child_items

    def item_template(self, item_type):
        return {"itemType": item_type}

    def create_items(self, items):
        self.created.extend(items)
        return {"successful": {"0": {"key": "N1"}}}


def _patch_dual(monkeypatch, zot):
    monkeypatch.setattr(
        "research_hub.zotero.client.ZoteroDualClient",
        lambda: SimpleNamespace(web=zot),
    )


def test_backfill_dry_run_returns_report_no_writes(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    zot = FakeZotero([_item(["foo"])])
    _patch_dual(monkeypatch, zot)

    report = run_backfill(cfg)

    assert report.dry_run is True
    assert report.tags_added
    assert report.notes_added
    assert zot.updated == []
    assert zot.created == []


def test_backfill_skips_cluster_without_zotero_collection_key(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, {"agents": {"name": "Agents", "zotero_collection_key": None}})
    zot = FakeZotero([])
    _patch_dual(monkeypatch, zot)

    report = run_backfill(cfg)

    assert report.errors == [{"slug": "agents", "error": "cluster has no Zotero collection"}]


def test_backfill_adds_missing_hub_tags(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    zot = FakeZotero([_item(["foo"])], children=[{"data": {"itemType": "note"}}])
    _patch_dual(monkeypatch, zot)

    report = run_backfill(cfg, apply=True)

    assert report.dry_run is False
    # v0.68.4: _compose_hub_tags now defaults type/<itemType> to
    # journalArticle when the paper dict has no doc_type, so backfill
    # emits one more tag than before.
    assert [tag["tag"] for tag in zot.updated[0]["tags"]] == [
        "foo",
        "research-hub",
        "cluster/agents",
        "type/journalArticle",
        "src/zotero",
    ]


def test_backfill_does_not_duplicate_existing_hub_tag(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    # v0.68.4: include type/journalArticle in pre-existing tags since
    # _compose_hub_tags now emits it by default — without it the backfill
    # would add it and break the "no duplicate" assertion.
    zot = FakeZotero(
        [_item(["foo", "research-hub", "cluster/agents", "type/journalArticle", "src/zotero"])],
        children=[{"data": {"itemType": "note"}}],
    )
    _patch_dual(monkeypatch, zot)

    report = run_backfill(cfg, apply=True)

    assert report.tags_added == []
    assert zot.updated == []


def test_backfill_creates_note_from_obsidian_frontmatter(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    note = tmp_path / "raw" / "agents" / "paper.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        "---\n"
        "title: Paper\n"
        "doi: 10.1/a\n"
        "summary: Frontmatter summary\n"
        "key_findings:\n"
        "  - Finding one\n"
        "methodology: Survey\n"
        "relevance: Useful\n"
        "---\n",
        encoding="utf-8",
    )
    index = DedupIndex()
    index.add(DedupHit(source="obsidian", doi="10.1/a", title="Paper", obsidian_path=str(note)))
    index.save(cfg.dedup_index_path)
    zot = FakeZotero([_item(["research-hub", "cluster/agents", "src/zotero"])])
    _patch_dual(monkeypatch, zot)

    report = run_backfill(cfg, apply=True, do_tags=False)

    assert report.notes_added == [{"key": "I1", "slug": "agents", "source": "obsidian"}]
    assert "<h1>Summary</h1><p>Frontmatter summary</p>" in zot.created[0]["note"]
    assert "<li>Finding one</li>" in zot.created[0]["note"]


def test_backfill_falls_back_to_stub_note_when_obsidian_missing(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    zot = FakeZotero([_item(["research-hub", "cluster/agents", "src/zotero"], doi="")])
    _patch_dual(monkeypatch, zot)

    report = run_backfill(cfg, apply=True, do_tags=False)

    assert report.notes_added == [{"key": "I1", "slug": "agents", "source": "stub"}]
    assert "<h3>Paper</h3>" in zot.created[0]["note"]
    assert "Imported from research-hub cluster" in zot.created[0]["note"]
