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
