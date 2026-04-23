from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from research_hub.dedup import DedupHit, DedupIndex


def _cfg(tmp_path: Path) -> SimpleNamespace:
    root = tmp_path / "vault"
    raw = root / "raw"
    hub = root / "hub"
    rh = root / ".research_hub"
    raw.mkdir(parents=True)
    hub.mkdir(parents=True)
    rh.mkdir(parents=True)
    clusters_file = rh / "clusters.yaml"
    clusters_file.write_text(
        json.dumps({"clusters": {"agents": {"name": "Agents", "zotero_collection_key": "C1"}}}),
        encoding="utf-8",
    )
    return SimpleNamespace(
        root=root,
        raw=raw,
        hub=hub,
        logs=root / "logs",
        research_hub_dir=rh,
        clusters_file=clusters_file,
        dedup_index_path=rh / "dedup_index.json",
        zotero_default_collection="C1",
        zotero_collections={},
        zotero_library_id="123",
    )


def _paper() -> list[dict]:
    return [
        {
            "title": "Paper One",
            "doi": "10.1000/example",
            "authors": [{"creatorType": "author", "lastName": "Doe", "firstName": "Jane"}],
            "year": 2026,
            "abstract": "Abstract",
            "journal": "Journal",
            "summary": "Summary",
            "key_findings": ["Finding"],
            "methodology": "Method",
            "relevance": "Relevant",
            "slug": "doe2026-paper-one",
            "sub_category": "agents",
        }
    ]


def test_stub_note_includes_title_authors_year_doi():
    from research_hub.zotero_hygiene import _build_stub_note

    html = _build_stub_note(
        {
            "title": "Paper",
            "creators": [{"creatorType": "author", "firstName": "Jane", "lastName": "Doe"}],
            "date": "2024-01-01",
            "DOI": "10.1/a",
            "publicationTitle": "Journal",
        },
        "agents",
    )
    assert "Paper" in html
    assert "Jane Doe" in html
    assert "(2024)" in html
    assert "https://doi.org/10.1/a" in html


def test_dedup_branch_adds_note_when_item_has_no_children(tmp_path, monkeypatch):
    from research_hub.pipeline import run_pipeline
    from research_hub.clusters import ClusterRegistry

    cfg = _cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    (cfg.root / "papers_input.json").write_text(json.dumps(_paper()), encoding="utf-8")
    monkeypatch.setattr("research_hub.pipeline.get_config", lambda: cfg)
    monkeypatch.setattr("research_hub.pipeline.time.sleep", lambda seconds: None)
    monkeypatch.setattr("research_hub.pipeline.update_cluster_links", lambda *args, **kwargs: None)

    added: list[tuple[str, str]] = []

    class FakeZotero:
        def item(self, key):
            return {"data": {"tags": []}}

        def update_item(self, data):
            return data

        def children(self, key):
            return []

    monkeypatch.setattr(
        "research_hub.pipeline._load_or_build_dedup",
        lambda *args, **kwargs: SimpleNamespace(
            doi_to_hits={},
            title_to_hits={},
            check=lambda payload: (True, [DedupHit(source="zotero", doi=payload["doi"], title=payload["title"], zotero_key="Z1")]),
            add=lambda hit: None,
            save=lambda path: None,
        ),
    )
    monkeypatch.setattr("research_hub.pipeline.get_client", lambda: FakeZotero())
    monkeypatch.setattr("research_hub.pipeline.add_note", lambda zot, key, content: added.append((key, content)) or True)

    assert run_pipeline(dry_run=False, cluster_slug="agents", verify=False) == 0
    assert added and added[0][0] == "Z1"
    assert "<h1>Summary</h1>" in added[0][1]


def test_dedup_branch_skips_note_when_item_already_has_note(tmp_path, monkeypatch):
    from research_hub.pipeline import run_pipeline
    from research_hub.clusters import ClusterRegistry

    cfg = _cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    (cfg.root / "papers_input.json").write_text(json.dumps(_paper()), encoding="utf-8")
    monkeypatch.setattr("research_hub.pipeline.get_config", lambda: cfg)
    monkeypatch.setattr("research_hub.pipeline.time.sleep", lambda seconds: None)
    monkeypatch.setattr("research_hub.pipeline.update_cluster_links", lambda *args, **kwargs: None)

    class FakeZotero:
        def item(self, key):
            return {"data": {"tags": []}}

        def update_item(self, data):
            return data

        def children(self, key):
            return [{"data": {"itemType": "note"}}]

    monkeypatch.setattr(
        "research_hub.pipeline._load_or_build_dedup",
        lambda *args, **kwargs: SimpleNamespace(
            doi_to_hits={},
            title_to_hits={},
            check=lambda payload: (True, [DedupHit(source="zotero", doi=payload["doi"], title=payload["title"], zotero_key="Z1")]),
            add=lambda hit: None,
            save=lambda path: None,
        ),
    )
    monkeypatch.setattr("research_hub.pipeline.get_client", lambda: FakeZotero())
    monkeypatch.setattr("research_hub.pipeline.add_note", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("note should not be added")))

    assert run_pipeline(dry_run=False, cluster_slug="agents", verify=False) == 0


def test_backfill_upgrades_stale_stub_to_obsidian_rich_note(tmp_path, monkeypatch):
    from research_hub.zotero_hygiene import STUB_MARKER, run_backfill

    cfg = _cfg(tmp_path)
    note = cfg.raw / "agents" / "paper.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        "---\nsummary: Rich summary\nkey_findings:\n  - Finding one\nmethodology: Survey\nrelevance: Useful\n---\n",
        encoding="utf-8",
    )
    index = DedupIndex()
    index.add(DedupHit(source="obsidian", doi="10.1/a", title="Paper", obsidian_path=str(note)))
    index.save(cfg.dedup_index_path)

    class FakeZotero:
        def __init__(self):
            self.updated: list[dict] = []

        def collection_items(self, collection_key, start=0, limit=100, itemType=""):
            return [{"key": "I1", "data": {"key": "I1", "title": "Paper", "DOI": "10.1/a", "tags": []}}]

        def children(self, key):
            return [{"data": {"key": "N1", "itemType": "note", "note": f"<p>{STUB_MARKER}: <b>agents</b></i></p>"}}]

        def update_item(self, data):
            self.updated.append(data.copy())
            return {}

    zot = FakeZotero()
    monkeypatch.setattr(
        "research_hub.zotero.client.ZoteroDualClient",
        lambda: SimpleNamespace(web=zot),
    )

    report = run_backfill(cfg, apply=True, do_tags=False)
    assert report.upgraded_stubs == 1
    assert "<h1>Summary</h1><p>Rich summary</p>" in zot.updated[0]["note"]


def test_report_summary_breaks_down_obsidian_vs_stub():
    from research_hub.zotero_hygiene import BackfillReport

    report = BackfillReport(dry_run=False, obsidian_sourced=2, enriched_stubs=1, upgraded_stubs=3)
    report.notes_added = [{"key": "1"}, {"key": "2"}, {"key": "3"}, {"key": "4"}, {"key": "5"}, {"key": "6"}]
    summary = report.summary()
    assert "6 (2 from Obsidian, 1 enriched stubs, 3 upgraded from stubs)" in summary
