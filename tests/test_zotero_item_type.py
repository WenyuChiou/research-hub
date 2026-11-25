"""Phase D / v1.1 — Zotero metadata correctness.

Locks two parity fixes (pipeline.py only, no LLM in the path):

  D1  _zotero_item_type: backends only ever set doc_type /
      publication_type / source, never item_type, so the pipeline
      historically filed EVERY paper as a journalArticle (wrong
      BibTeX export for arXiv / preprint / conference). The
      type-aware fallback maps them; an explicit pp["item_type"]
      still wins (the `pp.get("item_type","") or _zotero_item_type`
      precedence at the call site).
  D2  fit/<bucket> tag + Provenance child-note line: surface the
      Phase A provenance/fit_score in Zotero too — and crucially
      OMIT the fit/ tag entirely when there is no numeric score
      (no bogus tag on legacy / unscored papers).

Decision recap: thin-citation is v1.0-acceptable (the authenticity
gate is upstream of the Zotero write — Zotero only ever receives
accepted/real papers). These are v1.1 quality/parity fixes, not a
fabrication hole.
"""

from __future__ import annotations

import pytest

from research_hub.pipeline import (
    _build_note_html,
    _compose_hub_tags,
    _zotero_item_type,
)


# --- D1: itemType mapping ------------------------------------------------

@pytest.mark.parametrize(
    ("pp", "expected"),
    [
        ({"source": "arxiv"}, "preprint"),
        ({"doc_type": "arXiv preprint"}, "preprint"),
        ({"source": "biorxiv"}, "preprint"),
        ({"found_in": "medRxiv"}, "preprint"),
        ({"publication_type": "preprint"}, "preprint"),
        ({"doc_type": "posted-content"}, "preprint"),  # Crossref preprint type
        ({"source": "SSRN"}, "preprint"),
        ({"doc_type": "proceedings-article"}, "conferencePaper"),
        ({"publication_type": "Conference Paper"}, "conferencePaper"),
        ({"doc_type": "phdthesis"}, "thesis"),
        ({"publication_type": "Doctoral Dissertation"}, "thesis"),
        ({"doc_type": "technical report"}, "report"),
        ({"publication_type": "working paper"}, "report"),
        ({"doc_type": "book-chapter"}, "bookSection"),
        ({"doc_type": "book-section"}, "bookSection"),
        ({"doc_type": "book"}, "book"),
        ({"source": "crossref", "doc_type": "journal-article"}, "journalArticle"),
        ({"source": "semantic-scholar"}, "journalArticle"),
        ({}, "journalArticle"),  # empty -> safe default
        ({"doc_type": None, "source": None}, "journalArticle"),
    ],
)
def test_zotero_item_type_mapping(pp: dict, expected: str) -> None:
    assert _zotero_item_type(pp) == expected


def test_explicit_item_type_wins_over_mapper() -> None:
    """Mirrors pipeline.py's `pp.get("item_type","") or
    _zotero_item_type(pp)` — an explicitly supplied item_type is
    honoured even if the heuristic would say otherwise."""
    pp = {"item_type": "manuscript", "source": "arxiv"}
    resolved = pp.get("item_type", "") or _zotero_item_type(pp)
    assert resolved == "manuscript"  # not "preprint"

    pp_fallback = {"source": "arxiv"}
    resolved_fb = pp_fallback.get("item_type", "") or _zotero_item_type(pp_fallback)
    assert resolved_fb == "preprint"  # fallback engaged


# --- D2a: fit/<bucket> tag ----------------------------------------------

@pytest.mark.parametrize(
    ("score", "bucket"),
    [(5, "high"), (6, "high"), (4, "mid"), (3, "mid"), (2, "low"), (0, "low")],
)
def test_fit_bucket_tag_from_provenance(score: int, bucket: str) -> None:
    tags = _compose_hub_tags({"provenance": {"fit_score": score}}, "cluster-x")
    assert f"fit/{bucket}" in tags


def test_fit_bucket_tag_from_bare_fit_score() -> None:
    """Legacy papers may carry a top-level fit_score (no provenance)."""
    tags = _compose_hub_tags({"fit_score": 5}, "cluster-x")
    assert "fit/high" in tags


@pytest.mark.parametrize(
    "pp",
    [
        {},  # no provenance, no score
        {"provenance": {}},  # provenance present but no fit_score
        {"provenance": {"fit_score": None}},  # explicit None
        {"provenance": {"fit_score": "5"}},  # non-numeric string
        {"fit_score": True},  # bool is an int subclass — must NOT count
        {"provenance": "corroborated"},  # provenance not a dict
    ],
)
def test_no_bogus_fit_tag_when_unscored(pp: dict) -> None:
    """The no-bogus-tag contract: never emit a fit/ tag without a
    real numeric score (bool excluded — it subclasses int)."""
    tags = _compose_hub_tags(pp, "cluster-x")
    assert not any(t.startswith("fit/") for t in tags)


# --- D2b: Provenance child-note line ------------------------------------

def test_note_html_includes_provenance_block_when_present() -> None:
    pp = {
        "summary": "S",
        "provenance": {
            "resolved_via": "doi.org",
            "corroboration": "corroborated",
            "doi_checked_at": "2026-05-17",
            "fit_score": 5,
        },
    }
    html = _build_note_html(pp)
    assert "<h2>Provenance</h2>" in html
    assert "resolved via doi.org" in html
    assert "corroborated" in html
    assert "fit score 5" in html
    assert "DOI checked 2026-05-17" in html


@pytest.mark.parametrize(
    "pp",
    [
        {"summary": "S"},  # no provenance key
        {"summary": "S", "provenance": {}},  # empty provenance
        {"summary": "S", "provenance": "corroborated"},  # not a dict
    ],
)
def test_note_html_omits_provenance_block_when_absent(pp: dict) -> None:
    assert "<h2>Provenance</h2>" not in _build_note_html(pp)


def test_write_papers_to_zotero_respects_strict_zotero_templates() -> None:
    """Real Zotero templates reject venue/pagination fields unsupported by the itemType."""
    from research_hub.pipeline import write_papers_to_zotero

    strict_templates = {
        "note": {"itemType": "note", "note": "", "parentItem": "", "tags": [], "collections": [], "relations": {}},
        "preprint": {"itemType": "preprint", "title": "", "creators": [], "date": "", "DOI": "", "url": "", "abstractNote": "", "repository": "", "archiveID": "", "tags": [], "collections": []},
        "conferencePaper": {"itemType": "conferencePaper", "title": "", "creators": [], "date": "", "DOI": "", "url": "", "abstractNote": "", "proceedingsTitle": "", "volume": "", "issue": "", "pages": "", "tags": [], "collections": []},
        "bookSection": {"itemType": "bookSection", "title": "", "creators": [], "date": "", "DOI": "", "url": "", "abstractNote": "", "bookTitle": "", "volume": "", "pages": "", "tags": [], "collections": []},
        "book": {"itemType": "book", "title": "", "creators": [], "date": "", "DOI": "", "url": "", "abstractNote": "", "publisher": "", "volume": "", "tags": [], "collections": []},
        "thesis": {"itemType": "thesis", "title": "", "creators": [], "date": "", "url": "", "abstractNote": "", "university": "", "tags": [], "collections": []},
        "report": {"itemType": "report", "title": "", "creators": [], "date": "", "url": "", "abstractNote": "", "institution": "", "pages": "", "tags": [], "collections": []},
        "journalArticle": {"itemType": "journalArticle", "title": "", "creators": [], "date": "", "DOI": "", "url": "", "abstractNote": "", "publicationTitle": "", "volume": "", "issue": "", "pages": "", "tags": [], "collections": []},
        "dataset": {"itemType": "dataset", "title": "", "creators": [], "date": "", "DOI": "", "url": "", "abstractNote": "", "tags": [], "collections": []},
    }

    class _StrictZot:
        def __init__(self) -> None:
            self.created: list[dict] = []

        def item_template(self, item_type: str) -> dict:
            return dict(strict_templates[item_type])

        def create_items(self, items: list[dict]) -> dict:
            for idx, item in enumerate(items):
                allowed = set(strict_templates[item["itemType"]])
                extra_keys = set(item) - allowed
                assert not extra_keys, f"Invalid keys {extra_keys} for {item['itemType']}"
            self.created.extend(items)
            return {"successful": {str(i): {"key": f"Z{i}"} for i in range(len(items))}}

    papers = [
        {"title": "Preprint", "authors": ["Jane Doe"], "year": 2024, "doi": "10.48550/arXiv.2401.00001", "url": "https://arxiv.org/abs/2401.00001", "journal": "arXiv", "abstract": "A", "source": "arxiv"},
        {"title": "Conf", "authors": ["Jane Doe"], "year": 2024, "doi": "10.1000/conf", "journal": "ICML", "abstract": "A", "item_type": "conferencePaper"},
        {"title": "BookSec", "authors": ["Jane Doe"], "year": 2024, "doi": "10.1000/sec", "journal": "Handbook", "abstract": "A", "item_type": "bookSection"},
        {"title": "Book", "authors": ["Jane Doe"], "year": 2024, "doi": "10.1000/book", "journal": "MIT Press", "abstract": "A", "item_type": "book"},
        {"title": "Journal", "authors": ["Jane Doe"], "year": 2024, "doi": "10.1000/jour", "journal": "Nature", "abstract": "A", "item_type": "journalArticle"},
        {"title": "Thesis", "authors": ["Jane Doe"], "year": 2024, "journal": "MIT", "abstract": "A", "item_type": "thesis"},
        {"title": "Report", "authors": ["Jane Doe"], "year": 2024, "doi": "", "journal": "RAND", "abstract": "A", "item_type": "report"},
        {"title": "Data", "authors": ["Jane Doe"], "year": 2024, "doi": "10.5281/zenodo.1", "journal": "Zenodo", "abstract": "A", "item_type": "dataset"},
    ]
    zot = _StrictZot()
    zr, notes_out, errors = write_papers_to_zotero(zot, papers, "c-slug", "COLL1", batch_coll="BATCH1", log=lambda _: None)
    assert errors == [] and len(zr) == 8 and len(notes_out) == 8
    pre = next(x for x in zot.created if x["itemType"] == "preprint")
    assert "publicationTitle" not in pre
    assert pre["repository"] == "arXiv"
    assert pre["archiveID"] == "arXiv:2401.00001"
    conf = next(x for x in zot.created if x["itemType"] == "conferencePaper")
    assert conf["proceedingsTitle"] == "ICML"
    sec = next(x for x in zot.created if x["itemType"] == "bookSection")
    assert sec["bookTitle"] == "Handbook"
    bk = next(x for x in zot.created if x["itemType"] == "book")
    assert bk["publisher"] == "MIT Press"
    jour = next(x for x in zot.created if x["itemType"] == "journalArticle")
    assert jour["publicationTitle"] == "Nature"
    ds = next(x for x in zot.created if x["itemType"] == "dataset")
    assert "publicationTitle" not in ds


def test_reused_zotero_hit_updates_collections_preserves_zr_and_string_authors(tmp_path, monkeypatch) -> None:
    """Raw pyzotero reuse routes collections, retains zr statuses, and allows string authors in suggestions."""
    import json
    from types import SimpleNamespace
    from research_hub import pipeline
    from research_hub.clusters import ClusterRegistry
    from research_hub.dedup import DedupHit, DedupIndex

    root = tmp_path / "vault"
    (root / "raw").mkdir(parents=True)
    (root / "logs").mkdir(parents=True)
    (root / ".research_hub").mkdir(parents=True)
    cfg = SimpleNamespace(
        root=root, raw=root / "raw", logs=root / "logs", research_hub_dir=root / ".research_hub",
        clusters_file=root / ".research_hub" / "clusters.yaml",
        zotero_default_collection="CLUST1", zotero_collections={}, zotero_library_id="123",
    )
    ClusterRegistry(cfg.clusters_file).create(query="q", name="C", slug="c", zotero_collection_key="CLUST1")

    papers = [
        {"title": "Reused Paper Long Title", "doi": "10.1000/reused", "authors": ["Alice Smith"], "year": 2024,
         "abstract": "Abs", "journal": "J", "summary": "S", "key_findings": ["F"], "methodology": "M",
         "relevance": "R", "slug": "smith2024-reused", "sub_category": "c", "citation_count": 1},
        {"title": "Fresh Paper Long Title", "doi": "10.1000/fresh", "authors": ["Bob Jones"], "year": 2025,
         "abstract": "Abs", "journal": "J", "summary": "S", "key_findings": ["F"], "methodology": "M",
         "relevance": "R", "slug": "jones2025-fresh", "sub_category": "c", "citation_count": 1},
    ]
    (root / "papers_input.json").write_text(json.dumps({"papers": papers}), encoding="utf-8")

    class _PyzoteroLike:
        def __init__(self) -> None:
            self.updated: list[dict] = []

        def collections_sub(self, key: str) -> list[dict]:
            return [{"key": "BATCH1", "data": {"name": "20261125-q", "parentCollection": key}}]

        def create_collections(self, payload: list[dict]) -> dict:
            return {"successful": {"0": {"key": "BATCH2"}}}

        def item_template(self, item_type: str) -> dict:
            return {"itemType": item_type}

        def create_items(self, items: list[dict]) -> dict:
            return {"successful": {"0": {"key": "NEWKEY"}}}

        def item(self, key: str) -> dict:
            return {"data": {"key": key, "itemType": "journalArticle", "tags": [], "collections": []}}

        def children(self, key: str) -> list:
            return [{"data": {"itemType": "note"}}]

        def update_item(self, data: dict) -> bool:
            self.updated.append(data)
            return True

    dedup = DedupIndex()
    dedup.add(DedupHit(source="zotero", doi="10.1000/reused", title="Reused Paper Long Title", zotero_key="OLDKEY"))
    z = _PyzoteroLike()
    monkeypatch.setattr("research_hub.pipeline.get_config", lambda: cfg)
    monkeypatch.setattr(pipeline, "get_client", lambda: z)
    monkeypatch.setattr(pipeline, "check_duplicate", lambda *a, **k: False)
    monkeypatch.setattr(pipeline, "add_note", lambda *a, **k: True)
    monkeypatch.setattr(pipeline, "_load_or_build_dedup", lambda *a, **k: dedup)
    monkeypatch.setattr("research_hub.pipeline.time.sleep", lambda _: None)
    monkeypatch.setattr("research_hub.pipeline.update_cluster_links", lambda *a, **k: None)

    assert pipeline.run_pipeline(dry_run=False, cluster_slug="c", verify=False) == 0
    assert z.updated and set(z.updated[0]["collections"]) >= {"CLUST1", "BATCH2"}
    output = json.loads((cfg.logs / "pipeline_output.json").read_text(encoding="utf-8"))
    statuses = {row["title"]: row["status"] for row in output["zotero_results"]}
    assert statuses == {"Reused Paper Long Title": "REUSED", "Fresh Paper Long Title": "CREATED"}


def test_check_duplicate_normalizes_doi_and_falls_back_to_title() -> None:
    from research_hub.zotero.client import check_duplicate

    class _Zot:
        def items(self, *, q: str, limit: int = 5) -> list[dict]:
            if q.startswith("Large Language"):
                return [{"data": {"title": "Large Language Model based Multi-Agents", "DOI": "10.48550/arxiv.2402.01680"}}]
            if q == "untitled-check":
                return [{"data": {"itemType": "note"}}, {"data": {"title": None, "DOI": "10.1000/match"}}]
            return []

    assert check_duplicate(_Zot(), "Large Language Model based Multi-Agents", "10.48550/arXiv.2402.01680") is True
    assert check_duplicate(_Zot(), "", "untitled-check") is False
    assert check_duplicate(_Zot(), None, "10.1000/MATCH") is False  # type: ignore[arg-type]

    class _ZotNoneTitle:
        def items(self, *, q: str, limit: int = 5) -> list[dict]:
            return [{"data": {"title": None}}, {"data": {"title": "Other", "DOI": "10.1000/match"}}]

    assert check_duplicate(_ZotNoneTitle(), None, "10.1000/MATCH") is True  # type: ignore[arg-type]
