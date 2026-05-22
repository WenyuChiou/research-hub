"""Ingest dedup must be scoped to research-hub's OWN literature.

Bug (confirmed in the field): `research-hub auto` for a new topic produced
a near-empty Obsidian cluster — a search returned 25 papers, the fit-check
kept all 25, yet only ~1 Obsidian note was created.

Root cause: the dedup index (`<vault>/.research_hub/dedup_index.json`) was
dominated by `source:"zotero"` entries mirroring the user's ENTIRE Zotero
library (most of it never managed by research-hub) plus stale
`source:"obsidian"` entries pointing at deleted note files. The ingest
dedup block then:

  * treated any paper merely present in the Zotero library as a duplicate
    and `continue`-d past Obsidian-note creation — dropping it from the
    new cluster entirely; and
  * treated a stale obsidian entry (note file already deleted) as a live
    duplicate and skipped the paper.

Required behaviour: dedup may skip a paper ONLY when it duplicates
research-hub's own literature — i.e. a CURRENT Obsidian cluster note that
still exists on disk. A paper that is merely in the Zotero library must
still be ingested into the cluster (its Obsidian note created), while
reusing the existing Zotero item so no duplicate Zotero item is created.

These tests pin all three branches of the dedup block in
`research_hub.pipeline.run_pipeline`.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from research_hub import pipeline
from research_hub.clusters import ClusterRegistry
from research_hub.dedup import DedupHit, DedupIndex
from research_hub.pipeline import run_pipeline


# --- fixtures -------------------------------------------------------------


def _cfg(tmp_path: Path, *, default_collection: str | None = "DEFAULT") -> SimpleNamespace:
    root = tmp_path / "vault"
    raw = root / "raw"
    logs = root / "logs"
    hub = root / ".research_hub"
    raw.mkdir(parents=True)
    logs.mkdir(parents=True)
    hub.mkdir(parents=True)
    return SimpleNamespace(
        root=root,
        raw=raw,
        logs=logs,
        research_hub_dir=hub,
        clusters_file=hub / "clusters.yaml",
        zotero_default_collection=default_collection,
        zotero_collections={},
        zotero_library_id="123",
    )


def _paper(idx: int = 1) -> dict:
    return {
        "title": f"Already-In-Zotero Paper {idx}",
        "doi": f"10.1000/in-library-{idx}",
        "authors": [{"creatorType": "author", "lastName": "Doe", "firstName": "Jane"}],
        "year": 2026,
        "abstract": "Abstract",
        "journal": "Journal",
        "summary": "Summary",
        "key_findings": ["Finding"],
        "methodology": "Method",
        "relevance": "Relevant",
        "slug": f"doe2026-already-in-zotero-paper-{idx}",
        "sub_category": "agents",
        "citation_count": 1,
    }


class _DedupZotero:
    """Zotero stub that records writes so tests can assert no DUPLICATE
    item is created, while still serving the reads the zotero_hit reuse
    branch performs (`item` / `children` / `update_item`)."""

    def __init__(self) -> None:
        self.created: list[list[dict]] = []
        self.updated: list[dict] = []

    def item_template(self, item_type: str) -> dict:
        return {"itemType": item_type}

    def create_items(self, items):  # type: ignore[no-untyped-def]
        self.created.append(items)
        return {
            "successful": {
                str(idx): {"key": f"NEW{idx}"} for idx, _item in enumerate(items)
            }
        }

    def item(self, key: str) -> dict:
        return {"data": {"key": key, "itemType": "journalArticle", "tags": []}}

    def children(self, key: str) -> list:
        return []

    def update_item(self, data) -> bool:  # type: ignore[no-untyped-def]
        self.updated.append(data)
        return True


def _mock(monkeypatch: pytest.MonkeyPatch, cfg, dedup: DedupIndex) -> _DedupZotero:
    z = _DedupZotero()
    monkeypatch.setattr("research_hub.pipeline.get_config", lambda: cfg)
    monkeypatch.setattr(pipeline, "get_client", lambda: z)
    monkeypatch.setattr(
        pipeline, "check_duplicate", lambda zot, title, doi="", **kwargs: False
    )
    monkeypatch.setattr(pipeline, "add_note", lambda zot, key, content: True)
    monkeypatch.setattr(pipeline, "_load_or_build_dedup", lambda *a, **k: dedup)
    monkeypatch.setattr("research_hub.pipeline.time.sleep", lambda seconds: None)
    monkeypatch.setattr(
        "research_hub.pipeline.update_cluster_links", lambda *a, **k: None
    )
    return z


def _write_input(cfg, paper: dict) -> None:
    (cfg.root / "papers_input.json").write_text(
        json.dumps({"papers": [paper]}), encoding="utf-8"
    )


def _manifest_actions(cfg) -> list[str]:
    path = cfg.research_hub_dir / "manifest.jsonl"
    if not path.exists():
        return []
    return [
        json.loads(line)["action"]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


# --- branch 2: zotero_hit -> reuse Zotero item, STILL ingest into cluster --


def test_paper_already_in_zotero_library_is_still_ingested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A paper whose DOI matches a `source:"zotero"` dedup entry (it lives
    somewhere in the user's broader Zotero library) must STILL get an
    Obsidian note in the new cluster. The existing Zotero item is reused
    (key carried onto the paper) and NO duplicate Zotero item is created."""
    cfg = _cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(
        query="agents", name="Agents", slug="agents", zotero_collection_key="DEFAULT"
    )
    paper = _paper()
    _write_input(cfg, paper)

    dedup = DedupIndex()
    dedup.add(
        DedupHit(
            source="zotero",
            doi=paper["doi"],
            title=paper["title"],
            zotero_key="EXISTINGKEY",
        )
    )
    z = _mock(monkeypatch, cfg, dedup)

    rc = run_pipeline(dry_run=False, cluster_slug="agents", verify=False)

    assert rc == 0
    # The Obsidian note WAS created (the bug dropped it entirely).
    notes = list(cfg.raw.rglob("*.md"))
    assert len(notes) == 1, f"expected one ingested note, found {notes}"
    note_text = notes[0].read_text(encoding="utf-8")
    # The note reuses the existing Zotero key rather than minting a new one.
    assert "EXISTINGKEY" in note_text
    # No DUPLICATE Zotero item was created for the already-present paper.
    assert z.created == [], "reused Zotero paper must not create a new item"
    # Manifest records the reuse decision (not a skip) at the dedup stage,
    # plus a "new" entry when the Obsidian note is created downstream.
    actions = _manifest_actions(cfg)
    assert "ingest-reuse-zotero" in actions
    assert "dup-zotero" not in actions
    assert "new" in actions  # the Obsidian note was created for the reused paper


# --- branch 1a: stale obsidian_hit -> note file deleted -> ingest fresh ----


def test_stale_obsidian_entry_does_not_skip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `source:"obsidian"` dedup entry whose note file no longer exists
    is stale. It must NOT cause a skip — the paper is ingested fresh."""
    cfg = _cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(
        query="agents", name="Agents", slug="agents", zotero_collection_key="DEFAULT"
    )
    paper = _paper()
    _write_input(cfg, paper)

    dedup = DedupIndex()
    dedup.add(
        DedupHit(
            source="obsidian",
            doi=paper["doi"],
            title=paper["title"],
            zotero_key="OLDKEY",
            obsidian_path=str(tmp_path / "deleted" / "gone.md"),  # does NOT exist
        )
    )
    z = _mock(monkeypatch, cfg, dedup)

    rc = run_pipeline(dry_run=False, cluster_slug="agents", verify=False)

    assert rc == 0
    notes = list(cfg.raw.rglob("*.md"))
    assert len(notes) == 1, f"stale obsidian entry must not block ingest: {notes}"
    # Fresh ingest: a new Zotero item IS created (no real item to reuse).
    assert z.created, "stale-obsidian paper should be written to Zotero fresh"
    actions = _manifest_actions(cfg)
    assert "new" in actions
    assert "dup-obsidian" not in actions


# --- branch 1b: live obsidian_hit -> note file exists -> genuine skip ------


def test_live_obsidian_note_still_skips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A paper that IS a current research-hub Obsidian note (file exists on
    disk) is a genuine duplicate and must still be skipped."""
    cfg = _cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(
        query="agents", name="Agents", slug="agents", zotero_collection_key="DEFAULT"
    )
    paper = _paper()
    _write_input(cfg, paper)

    existing_dir = cfg.raw / "agents"
    existing_dir.mkdir(parents=True, exist_ok=True)
    existing_note = existing_dir / f"{paper['slug']}.md"
    existing_note.write_text(
        "---\n"
        f'title: "{paper["title"]}"\n'
        f'doi: "{paper["doi"]}"\n'
        'zotero-key: "LIVEKEY"\n'
        'cluster_queries: ["old query"]\n'
        'topic_cluster: "agents"\n'
        'tags: ["agents"]\n'
        "---\n",
        encoding="utf-8",
    )

    dedup = DedupIndex()
    dedup.add(
        DedupHit(
            source="obsidian",
            doi=paper["doi"],
            title=paper["title"],
            zotero_key="LIVEKEY",
            obsidian_path=str(existing_note),
        )
    )
    z = _mock(monkeypatch, cfg, dedup)

    rc = run_pipeline(dry_run=False, cluster_slug="agents", verify=False)

    assert rc == 0
    # No NEW note file appeared — only the pre-existing one.
    notes = list(cfg.raw.rglob("*.md"))
    assert notes == [existing_note], f"live obsidian dup must skip: {notes}"
    # No Zotero item created for the skipped duplicate.
    assert z.created == []
    actions = _manifest_actions(cfg)
    assert "dup-obsidian" in actions
    assert "new" not in actions
    assert "ingest-reuse-zotero" not in actions


# --- in-batch dedup: same paper from two backends under different DOIs ----


def _twin_papers() -> list[dict]:
    """Two records for the SAME paper as two backends would return it: the
    title differs only by punctuation (normalize_title collapses that) and
    each carries a different DOI (a journal DOI vs a repository DOI), so
    DOI-keyed search-merge dedup keeps both. Distinct slugs so the test
    proves the in-batch pass collapses them — not a filename overwrite."""
    base = dict(
        authors=[{"creatorType": "author", "lastName": "Kota", "firstName": "Sunil"}],
        year=2025,
        abstract="Abstract on building effective AI agents.",
        journal="Journal",
        summary="Summary",
        key_findings=["Finding"],
        methodology="Method",
        relevance="Relevant",
        sub_category="agents",
        citation_count=1,
    )
    first = dict(
        base,
        title="Building Effective AI Agents: Workflows, Design Patterns and Best Practices",
        doi="10.1000/journal-doi",
        slug="kota2025-building-effective-ai-agents",
    )
    second = dict(
        base,
        # one extra comma -> normalize_title collapses it to == first
        title="Building Effective AI Agents: Workflows, Design Patterns, and Best Practices",
        doi="10.1000/repository-doi",
        slug="kota2025-building-effective-ai-agents-v2",
    )
    return [first, second]


def _write_inputs(cfg, papers: list[dict]) -> None:
    (cfg.root / "papers_input.json").write_text(
        json.dumps({"papers": papers}), encoding="utf-8"
    )


def test_in_batch_same_paper_two_dois_collapses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two backend records for one paper (same normalized title, different
    DOIs) must collapse to a SINGLE Obsidian note + SINGLE Zotero item.
    Before the fix each got its own Zotero item (W2FTHN8X incident)."""
    cfg = _cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(
        query="agents", name="Agents", slug="agents", zotero_collection_key="DEFAULT"
    )
    _write_inputs(cfg, _twin_papers())

    dedup = DedupIndex()  # empty: neither twin is in the vault yet
    z = _mock(monkeypatch, cfg, dedup)

    rc = run_pipeline(dry_run=False, cluster_slug="agents", verify=False)

    assert rc == 0
    notes = list(cfg.raw.rglob("*.md"))
    assert len(notes) == 1, f"in-batch twin must collapse to one note: {notes}"
    created_items = [item for batch in z.created for item in batch]
    assert len(created_items) == 1, f"exactly one Zotero item expected: {z.created}"
    actions = _manifest_actions(cfg)
    assert actions.count("dup-in-batch") == 1
    assert actions.count("new") == 1


def test_in_batch_same_doi_collapses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two records sharing a normalized DOI collapse via the DOI branch —
    covers the DOI half of the `doi OR title` collapse condition (the twin
    test above exercises the title half)."""
    cfg = _cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(
        query="agents", name="Agents", slug="agents", zotero_collection_key="DEFAULT"
    )
    first = _paper(1)
    second = _paper(2)  # different title + slug ...
    second["doi"] = first["doi"]  # ... but the SAME DOI
    _write_inputs(cfg, [first, second])

    dedup = DedupIndex()
    z = _mock(monkeypatch, cfg, dedup)

    rc = run_pipeline(dry_run=False, cluster_slug="agents", verify=False)

    assert rc == 0
    notes = list(cfg.raw.rglob("*.md"))
    assert len(notes) == 1, f"same-DOI twin must collapse to one note: {notes}"
    created_items = [item for batch in z.created for item in batch]
    assert len(created_items) == 1, f"exactly one Zotero item expected: {z.created}"
    actions = _manifest_actions(cfg)
    assert actions.count("dup-in-batch") == 1


def test_in_batch_distinct_papers_both_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two genuinely different papers must both survive the in-batch pass —
    the collapse fires on shared identity, not merely on batch size.

    NOTE: this is an over-collapse guard, not a regression pin — it passes
    with OR without the fix. The regression is pinned by the two collapse
    tests above."""
    cfg = _cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(
        query="agents", name="Agents", slug="agents", zotero_collection_key="DEFAULT"
    )
    _write_inputs(cfg, [_paper(1), _paper(2)])

    dedup = DedupIndex()
    z = _mock(monkeypatch, cfg, dedup)

    rc = run_pipeline(dry_run=False, cluster_slug="agents", verify=False)

    assert rc == 0
    notes = list(cfg.raw.rglob("*.md"))
    assert len(notes) == 2, f"distinct papers must not be collapsed: {notes}"
    actions = _manifest_actions(cfg)
    assert "dup-in-batch" not in actions
