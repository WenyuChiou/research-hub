"""Regression tests for v1.3.1 Stage 1-2 P0 fixes (authenticity, fit_check, discover, pipeline)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

import research_hub.authenticity as auth
from research_hub import pipeline
from research_hub.authenticity import (
    CROSSREF_VERIFY_CACHE,
    CrossrefVerifyCache,
    _corroboration_label,
    verify_authenticity,
)
from research_hub.clusters import ClusterRegistry
from research_hub.dedup import DedupIndex
from research_hub.discover import _to_papers_input
from research_hub.fit_check import apply_scores
from research_hub.pipeline import _in_batch_title_match_ok, run_pipeline


class _Resp:
    def __init__(self, status_code: int = 200, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


def _cfg(tmp_path: Path) -> SimpleNamespace:
    root = tmp_path / "vault"
    cfg = SimpleNamespace(
        root=root,
        raw=root / "raw",
        hub=root / "hub",
        logs=root / "logs",
        research_hub_dir=root / ".research_hub",
        clusters_file=root / ".research_hub" / "clusters.yaml",
        zotero_library_id="",
        zotero_default_collection=None,
        zotero_collections={},
    )
    for path in (cfg.raw, cfg.hub, cfg.logs, cfg.research_hub_dir):
        path.mkdir(parents=True, exist_ok=True)
    return cfg


def _paper(
    title: str = "Machine Learning Applications for Short-term Flood Forecasting",
    doi: str = "10.1007/s11269-025-04093-x",
    **extra,
) -> dict:
    paper = {
        "title": title,
        "doi": doi,
        "authors": [{"creatorType": "author", "firstName": "Jane", "lastName": "Doe"}],
        "authors_str": "Doe, Jane",
        "year": 2025,
        "journal": "Journal of Testing",
        "venue": "Journal of Testing",
        "abstract": "A real abstract.",
        "summary": "Summary",
        "key_findings": ["One"],
        "methodology": "Survey",
        "relevance": "Relevant",
        "slug": "doe2025-machine-learning-applications-short-term",
        "sub_category": "agents",
        "tags": [],
        "source": "openalex",
        "citation_count": 0,
    }
    paper.update(extra)
    return paper


def _work(
    *,
    doi: str = "10.1007/s11269-025-04093-x",
    title: str = "Machine Learning Applications for Short-term Flood Forecasting",
    year: int = 2025,
    family: str = "Doe",
    given: str = "Jane",
) -> dict:
    return {
        "DOI": doi,
        "title": [title],
        "author": [{"family": family, "given": given}],
        "issued": {"date-parts": [[year, 1, 1]]},
        "container-title": ["Journal of Testing"],
        "type": "journal-article",
    }


def _ok_head(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth.requests, "head", lambda *a, **k: _Resp(200))


# ---------------------------------------------------------------------------
# 1. authenticity.py: CrossrefVerifyCache record storage + poisoned cache + conflict
# ---------------------------------------------------------------------------


def test_crossref_cache_set_and_get_entry_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / CROSSREF_VERIFY_CACHE
    cache = CrossrefVerifyCache()
    record = {"title": "Real Paper", "year": 2024, "authors": ["Doe, Jane"]}
    cache.set("doi:10.1000/real", True, record=record)
    cache.set("doi:10.1000/bare", True)
    cache.save(path)

    loaded = CrossrefVerifyCache.load(path)
    entry = loaded.get_entry("10.1000/real")
    assert entry is not None
    assert entry["verified"] is True
    assert entry["record"] == record
    assert loaded.get("doi:10.1000/real") == entry

    bare_entry = loaded.get_entry("doi:10.1000/bare")
    assert bare_entry is not None
    assert "record" not in bare_entry


def test_crossref_poisoned_cache_rejects_conflicting_second_paper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Paper 1 caches DOI X with its Crossref metadata; Paper 2 claiming DOI X
    with conflicting title/year must NOT get forged corroboration on cache hit."""
    cfg = _cfg(tmp_path)
    _ok_head(monkeypatch)
    doi = "10.1007/s11269-025-04093-x"
    monkeypatch.setattr(
        "research_hub.search.crossref.requests.get",
        lambda *a, **k: _Resp(payload={"message": _work(doi=doi)}),
    )

    paper1 = _paper(doi=doi)
    accepted1, quarantined1 = verify_authenticity([paper1], cfg, cluster_slug="agents")
    assert len(accepted1) == 1
    assert quarantined1 == []

    # Second run: Crossref HTTP must not even be needed; cached record must catch conflict.
    monkeypatch.setattr(
        auth.CrossrefBackend,
        "get_paper",
        lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("should use cache")),
    )
    paper2 = _paper(
        title="Completely Fabricated Paper Claiming Real DOI",
        doi=doi,
        year=2018,
        authors=[{"creatorType": "author", "firstName": "Bob", "lastName": "Smith"}],
    )
    accepted2, quarantined2 = verify_authenticity([paper2], cfg, cluster_slug="agents")

    assert accepted2 == []
    assert len(quarantined2) == 1
    assert quarantined2[0]["layer"] == "L2"
    assert quarantined2[0]["reason"] == "uncorroborated"
    assert "crossref" not in [str(b).casefold() for b in paper2.get("backends", [])]


def test_crossref_cache_hit_accepts_matching_second_paper_with_cached_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _cfg(tmp_path)
    _ok_head(monkeypatch)
    doi = "10.1007/s11269-025-04093-x"
    cache = CrossrefVerifyCache()
    cache.set(
        f"doi:{doi}",
        True,
        record={
            "title": "Machine Learning Applications for Short-term Flood Forecasting",
            "year": 2025,
            "authors": ["Doe, Jane"],
        },
    )
    cache.save(cfg.research_hub_dir / CROSSREF_VERIFY_CACHE)

    monkeypatch.setattr(
        auth.CrossrefBackend,
        "get_paper",
        lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("should use cache")),
    )
    paper = _paper(doi=doi)
    accepted, quarantined = verify_authenticity([paper], cfg, cluster_slug="agents")

    assert quarantined == []
    assert len(accepted) == 1
    assert accepted[0]["provenance"]["corroboration"] == "corroborated"
    assert any(r.get("source") == "crossref" for r in accepted[0]["source_records"])


def test_corroboration_label_returns_conflict_never_falls_through(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paper = _paper(
        backends=["openalex", "crossref"],
        found_in=["openalex", "crossref"],
        citation_count=10,
        source_records=[
            {
                "source": "openalex",
                "title": "LLM Agents for Flood Forecasting",
                "year": 2025,
                "authors": ["Doe, Jane"],
            },
            {
                "source": "crossref",
                "title": "Unrelated Polymer Chemistry Study",
                "year": 2019,
                "authors": ["Smith, Alice"],
            },
        ],
    )
    assert _corroboration_label(paper) == "conflict"

    cfg = _cfg(tmp_path)
    _ok_head(monkeypatch)
    accepted, quarantined = verify_authenticity([paper], cfg, cluster_slug="agents")
    assert accepted == []
    assert len(quarantined) == 1
    assert quarantined[0]["layer"] == "L2"
    assert quarantined[0]["reason"] == "corroboration_conflict"


def test_corroboration_label_returns_corroborated_when_records_agree() -> None:
    paper = _paper(
        backends=["openalex", "crossref"],
        source_records=[
            {
                "source": "openalex",
                "title": "LLM Agents for Flood Forecasting",
                "year": 2025,
                "authors": ["Doe, Jane"],
            },
            {
                "source": "crossref",
                "title": "LLM Agents for Flood Forecasting",
                "year": 2025,
                "authors": ["Jane Doe"],
            },
        ],
    )
    assert _corroboration_label(paper) == "corroborated"


# ---------------------------------------------------------------------------
# 2. fit_check.py: DOI-less books by index, arXiv, norm DOI/title, conflict guard
# ---------------------------------------------------------------------------


def test_apply_scores_doi_less_classic_book_by_index_keeps_score_5() -> None:
    candidates = [
        {"title": "An Inquiry into the Nature and Causes of the Wealth of Nations", "doi": "", "year": 1776},
        {"title": "Another Book Without DOI", "doi": "", "year": 1950},
    ]
    report = apply_scores(
        "economics",
        candidates,
        {"scores": [
            {"index": 1, "doi": "", "score": 5, "reason": "foundational classic"},
            {"index": 2, "doi": "", "score": 2, "reason": "tangential"},
        ]},
        threshold=3,
    )
    assert len(report.accepted) == 1
    assert report.accepted[0].title == candidates[0]["title"]
    assert report.accepted[0].score == 5
    assert report.accepted[0].kept is True
    assert len(report.rejected) == 1
    assert report.rejected[0].score == 2


def test_apply_scores_matches_arxiv_and_normalized_doi_and_title() -> None:
    candidates = [
        {"title": "Preprint Alpha", "doi": "", "arxiv_id": "arXiv:2401.12345"},
        {"title": "Preprint Beta", "doi": "", "arxiv_id": "2402.54321"},
        {"title": "Journal Gamma Study", "doi": "https://doi.org/10.1000/GAMMA.1"},
        {"title": "A Long Punctuated: Title, For Matching!", "doi": ""},
    ]
    report = apply_scores(
        "agents",
        candidates,
        [
            {"index": 1, "doi": "2401.12345", "score": 4, "reason": "arxiv via doi field"},
            {"arxiv_id": "arXiv:2402.54321", "score": 5, "reason": "arxiv field"},
            {"doi": "doi:10.1000/gamma.1", "score": 4, "reason": "norm doi"},
            {"title": "A Long Punctuated Title For Matching", "score": 3, "reason": "norm title"},
        ],
        threshold=3,
    )
    assert [r.score for r in report.accepted] == [4, 5, 4, 3]
    assert report.rejected == []


def test_apply_scores_index_conflict_guard_blocks_misapplied_score() -> None:
    candidates = [
        {"title": "Original Paper Alpha", "doi": "10.1000/alpha"},
        {"title": "Original Classic Book Beta", "doi": ""},
    ]
    report = apply_scores(
        "agents",
        candidates,
        [
            {"index": 1, "doi": "10.1000/wrong-doi", "score": 5, "reason": "doi conflict"},
            {"index": 2, "title": "Completely Different Book Title", "score": 5, "reason": "title conflict"},
            {"index": True, "score": 5, "reason": "bool index ignored"},
        ],
        threshold=3,
    )
    assert report.accepted == []
    assert [r.score for r in report.rejected] == [0, 0]
    assert all(r.reason == "no score provided" for r in report.rejected)


# ---------------------------------------------------------------------------
# 3. discover.py: _to_papers_input preserves metadata fields
# ---------------------------------------------------------------------------


def test_to_papers_input_preserves_discovery_metadata_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "research_hub.search.abstract_recovery.recover_abstract",
        lambda *_a, **_kw: SimpleNamespace(text="", source=""),
    )
    candidate = {
        "title": "Preserved Metadata Paper",
        "doi": "10.1000/meta-1",
        "authors": ["Jane Doe"],
        "year": 2024,
        "abstract": "Observed abstract text.",
        "abstract_source": "openalex",
        "source": "openalex",
        "citation_count": 42,
        "found_in": ["openalex", "crossref"],
        "backends": ["openalex", "crossref"],
        "doc_type": "book",
        "item_type": "book",
        "publication_types": ["Monograph"],
        "url": "https://example.org/paper",
        "pmid": "98765432",
        "openalex_id": "W123456789",
        "isbn": "978-0-12-345678-9",
        "provenance": {"track": "classic-bedrock"},
        "source_records": [{"source": "openalex", "title": "Preserved Metadata Paper"}],
    }
    [entry] = _to_papers_input([candidate], "agents")

    assert entry["citation_count"] == 42
    assert entry["found_in"] == ["openalex", "crossref"]
    assert entry["backends"] == ["openalex", "crossref"]
    assert entry["doc_type"] == "book"
    assert entry["item_type"] == "book"
    assert entry["publication_types"] == ["Monograph"]
    assert entry["url"] == "https://example.org/paper"
    assert entry["pmid"] == "98765432"
    assert entry["openalex_id"] == "W123456789"
    assert entry["isbn"] == "978-0-12-345678-9"
    assert entry["provenance"] == {"track": "classic-bedrock"}
    assert entry["source_records"] == [{"source": "openalex", "title": "Preserved Metadata Paper"}]


# ---------------------------------------------------------------------------
# 4. pipeline.py: in-batch seen_titles guard + Vault slug collision suffix
# ---------------------------------------------------------------------------


def test_in_batch_title_match_guard_distinguishes_unrelated_papers_with_different_dois() -> None:
    p_base = {
        "title": "Advances in Hydrological Modeling and Forecasting",
        "doi": "10.1000/one",
        "year": 2018,
        "authors": [{"creatorType": "author", "lastName": "Smith", "firstName": "Alice"}],
    }
    p_diff_year_author = {
        "title": "Advances in Hydrological Modeling and Forecasting",
        "doi": "10.1000/two",
        "year": 2025,
        "authors": [{"creatorType": "author", "lastName": "Jones", "firstName": "Bob"}],
    }
    p_diff_author_same_year = {
        "title": "Advances in Hydrological Modeling and Forecasting",
        "doi": "10.1000/three",
        "year": 2018,
        "authors": [{"creatorType": "author", "lastName": "Jones", "firstName": "Bob"}],
    }
    p_twin = {
        "title": "Advances in Hydrological Modeling and Forecasting",
        "doi": "10.1000/four",
        "year": 2019,
        "authors": [{"creatorType": "author", "lastName": "Smith", "firstName": "A."}],
    }
    p_vol1 = {
        "title": "History of Economic Analysis Vol. I",
        "doi": "10.1000/vol1",
        "year": 2020,
        "authors": [{"creatorType": "author", "lastName": "Schumpeter", "firstName": "J"}],
    }
    p_vol2 = {
        "title": "History of Economic Analysis Vol. II",
        "doi": "10.1000/vol2",
        "year": 2020,
        "authors": [{"creatorType": "author", "lastName": "Schumpeter", "firstName": "J"}],
    }
    p_erratum = {
        "title": "Erratum: Advances in Hydrological Modeling and Forecasting",
        "doi": "10.1000/erratum",
        "year": 2019,
        "authors": [{"creatorType": "author", "lastName": "Smith", "firstName": "Alice"}],
    }

    assert _in_batch_title_match_ok(p_base, p_diff_year_author) is False
    assert _in_batch_title_match_ok(p_base, p_diff_author_same_year) is False
    assert _in_batch_title_match_ok(p_base, p_twin) is True
    assert _in_batch_title_match_ok(p_vol1, p_vol2) is False
    assert _in_batch_title_match_ok(p_base, p_erratum) is False


def test_pipeline_in_batch_does_not_merge_distinct_dois_with_different_authors_or_years(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    monkeypatch.setenv("RESEARCH_HUB_NO_ZOTERO", "1")
    monkeypatch.setattr(pipeline, "get_config", lambda: cfg)
    monkeypatch.setattr(pipeline, "_load_or_build_dedup", lambda *a, **k: DedupIndex())
    monkeypatch.setattr(pipeline.time, "sleep", lambda _s: None)
    monkeypatch.setattr("research_hub.pipeline.update_cluster_links", lambda *a, **k: None)
    monkeypatch.setattr(
        "research_hub.authenticity.verify_authenticity",
        lambda papers, *_a, **_kw: (papers, []),
    )

    shared_title = "Comprehensive Survey of Multi-Agent Coordination Systems"
    papers = [
        _paper(
            title=shared_title,
            doi="10.1000/paper-2018",
            year=2018,
            authors=[{"creatorType": "author", "firstName": "Alice", "lastName": "Smith"}],
            slug="smith2018-comprehensive-survey",
        ),
        _paper(
            title=shared_title,
            doi="10.1000/paper-2025",
            year=2025,
            authors=[{"creatorType": "author", "firstName": "Bob", "lastName": "Jones"}],
            slug="jones2025-comprehensive-survey",
        ),
    ]
    (cfg.root / "papers_input.json").write_text(json.dumps({"papers": papers}), encoding="utf-8")

    rc = run_pipeline(dry_run=False, cluster_slug="agents", verify=False)
    assert rc == 0
    notes = sorted(p.name for p in (cfg.raw / "agents").glob("*.md"))
    assert notes == ["jones2025-comprehensive-survey.md", "smith2018-comprehensive-survey.md"]


def test_vault_slug_collision_multi_volume_books_allocates_suffix_without_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="history", name="History", slug="history")
    monkeypatch.setenv("RESEARCH_HUB_NO_ZOTERO", "1")
    monkeypatch.setattr(pipeline, "get_config", lambda: cfg)
    monkeypatch.setattr(pipeline, "_load_or_build_dedup", lambda *a, **k: DedupIndex())
    monkeypatch.setattr(pipeline.time, "sleep", lambda _s: None)
    monkeypatch.setattr("research_hub.pipeline.update_cluster_links", lambda *a, **k: None)
    monkeypatch.setattr(
        "research_hub.authenticity.verify_authenticity",
        lambda papers, *_a, **_kw: (papers, []),
    )

    # Omit slug so _auto_generate_missing_fields derives identical 4-keyword slugs.
    vol1 = {
        "title": "History of Western Political Philosophy, Vol. I",
        "doi": "",
        "arxiv_id": "2001.00001",
        "authors": [{"creatorType": "author", "firstName": "John", "lastName": "Doe"}],
        "year": 2020,
        "abstract": "Volume I abstract.",
        "journal": "Academic Press",
        "summary": "Vol I summary",
        "key_findings": ["F1"],
        "methodology": "Historical",
        "relevance": "Core",
        "sub_category": "history",
    }
    vol2 = dict(vol1, title="History of Western Political Philosophy, Vol. II", arxiv_id="2001.00002", summary="Vol II summary")
    vol3 = dict(vol1, title="History of Western Political Philosophy, Vol. III", arxiv_id="2001.00003", summary="Vol III summary")

    (cfg.root / "papers_input.json").write_text(
        json.dumps({"papers": [vol1, vol2, vol3]}),
        encoding="utf-8",
    )

    rc = run_pipeline(dry_run=False, cluster_slug="history", verify=False)
    assert rc == 0

    folder = cfg.raw / "history"
    notes = sorted(p.name for p in folder.glob("*.md"))
    assert notes == [
        "doe2020-history-western-political-philosophy-2.md",
        "doe2020-history-western-political-philosophy-3.md",
        "doe2020-history-western-political-philosophy.md",
    ]
    assert "Vol. I" in (folder / "doe2020-history-western-political-philosophy.md").read_text(encoding="utf-8")
    assert "Vol. II" in (folder / "doe2020-history-western-political-philosophy-2.md").read_text(encoding="utf-8")
    assert "Vol. III" in (folder / "doe2020-history-western-political-philosophy-3.md").read_text(encoding="utf-8")


def test_vault_same_work_overwrites_existing_note_without_suffix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    monkeypatch.setenv("RESEARCH_HUB_NO_ZOTERO", "1")
    monkeypatch.setattr(pipeline, "get_config", lambda: cfg)
    monkeypatch.setattr(pipeline, "_load_or_build_dedup", lambda *a, **k: DedupIndex())
    monkeypatch.setattr(pipeline.time, "sleep", lambda _s: None)
    monkeypatch.setattr("research_hub.pipeline.update_cluster_links", lambda *a, **k: None)
    monkeypatch.setattr(
        "research_hub.authenticity.verify_authenticity",
        lambda papers, *_a, **_kw: (papers, []),
    )

    folder = cfg.raw / "agents"
    folder.mkdir(parents=True, exist_ok=True)
    existing_note = folder / "doe2025-same-work.md"
    existing_note.write_text(
        "---\n"
        'title: "Same Work Title"\n'
        'doi: "10.1000/same-work"\n'
        'zotero-key: "ZKEY1"\n'
        "---\nOld body\n",
        encoding="utf-8",
    )

    paper = _paper(
        title="Same Work Title",
        doi="https://doi.org/10.1000/SAME-WORK",
        slug="doe2025-same-work",
        summary="Updated summary",
    )
    (cfg.root / "papers_input.json").write_text(json.dumps({"papers": [paper]}), encoding="utf-8")

    rc = run_pipeline(dry_run=False, cluster_slug="agents", verify=False)
    assert rc == 0

    notes = sorted(p.name for p in folder.glob("*.md"))
    assert notes == ["doe2025-same-work.md"]
    assert "Updated summary" in existing_note.read_text(encoding="utf-8")
