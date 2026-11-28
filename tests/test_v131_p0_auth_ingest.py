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
    assert quarantined2[0]["reason"] == "corroboration_conflict"
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
        title="LLM Agents for Flood Forecasting",
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


# ---------------------------------------------------------------------------
# 5. v1.3.2 astra gate blocker regressions (§§1-3)
# ---------------------------------------------------------------------------


def test_corroboration_blocks_empty_dict_titleless_record_and_3_record_conflict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert auth._records_agree([{"source": "openalex", "title": "Paper T"}, {}]) is False
    assert auth._records_agree([{"source": "openalex", "title": "Paper T"}, {"source": "crossref"}]) is False

    # Empty backend_records must not mask source_records conflict.
    paper_empty_br = _paper(
        backend_records=[],
        source_records=[
            {"source": "openalex", "title": "Machine Learning Applications for Short-term Flood Forecasting", "year": 2025, "authors": ["Doe, Jane"]},
            {"source": "crossref", "title": "Unrelated Quantum Spin Paper", "year": 2018, "authors": ["Smith, Bob"]},
        ],
    )
    assert _corroboration_label(paper_empty_br) == "conflict"

    # 2 agreeing records must NOT mask a 3rd contradicting record.
    paper_3way = _paper(
        backends=["openalex", "crossref", "semantic-scholar"],
        source_records=[
            {"source": "openalex", "title": "Machine Learning Applications for Short-term Flood Forecasting", "year": 2025, "authors": ["Doe, Jane"]},
            {"source": "crossref", "title": "Machine Learning Applications for Short-term Flood Forecasting", "year": 2025, "authors": ["Jane Doe"]},
            {"source": "semantic-scholar", "title": "Completely Contradictory Botany Monograph", "year": 2010, "authors": ["Brown, Eve"]},
        ],
    )
    assert _corroboration_label(paper_3way) == "conflict"

    cfg = _cfg(tmp_path)
    _ok_head(monkeypatch)
    accepted, quarantined = verify_authenticity([paper_3way], cfg, cluster_slug="agents")
    assert accepted == []
    assert quarantined[0]["reason"] == "corroboration_conflict"

    # Titleless crossref dict cannot corroborate single-source paper.
    titleless = _paper(source="openalex", source_records=[{"source": "crossref"}])
    assert _corroboration_label(titleless) == "single-source"

    # Candidate paper metadata contradicting agreeing source_records must return conflict.
    paper_vs_records = _paper(
        title="Completely Different Candidate Paper Title",
        backends=["openalex", "crossref"],
        source_records=[
            {"source": "openalex", "title": "LLM Agents for Flood Forecasting", "year": 2025, "authors": ["Doe, Jane"]},
            {"source": "crossref", "title": "LLM Agents for Flood Forecasting", "year": 2025, "authors": ["Jane Doe"]},
        ],
    )
    assert _corroboration_label(paper_vs_records) == "conflict"


def test_classic_book_isbn_and_historical_year_pass_l0_and_l3(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _cfg(tmp_path)
    seen_urls: list[str] = []

    def fake_head(url, *args, **kwargs):
        seen_urls.append(url)
        return _Resp(200)

    monkeypatch.setattr(auth.requests, "head", fake_head)
    book = _paper(
        title="An Inquiry into the Nature and Causes of the Wealth of Nations",
        doi="",
        isbn="978-0-14-044913-6",
        doc_type="book",
        year=1776,
        authors=[{"creatorType": "author", "firstName": "Adam", "lastName": "Smith"}],
        citation_count=50,
    )
    accepted, quarantined = verify_authenticity([book], cfg, cluster_slug="economics")
    assert quarantined == []
    assert len(accepted) == 1
    assert seen_urls == ["https://openlibrary.org/isbn/9780140449136.json"]
    assert accepted[0]["provenance"]["resolved_via"] == "openlibrary.org"


def test_discover_apply_variations_and_merge_preserve_backends_and_urls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from research_hub.discover import QueryVariation, _merge_search_dict_candidates, apply_variations
    from research_hub.search._rank import _merge_record
    from research_hub.search.base import SearchResult

    cfg = _cfg(tmp_path)

    def fake_search(query, **kwargs):
        return [
            SearchResult(
                title="Shared Hydrology Paper",
                doi="10.1000/hydro",
                authors=["Jane Doe"],
                year=2024,
                source="openalex",
                confidence=0.5,
                found_in=["openalex"],
            )
        ]

    monkeypatch.setattr("research_hub.search.search_papers", fake_search)
    out = apply_variations(cfg, "hydro", [QueryVariation("flood modeling"), QueryVariation("runoff forecast")])
    assert len(out) == 1
    assert out[0]["found_in"] == ["openalex"]
    assert out[0]["_discover_meta"]["matched_variations"] == ["flood modeling", "runoff forecast"]
    assert auth._backend_names({"source": "openalex", "found_in": ["flood modeling", "runoff forecast"]}) == ["openalex"]

    merged_sr = _merge_record(
        SearchResult(title="T", doi="10.1/x", source="openalex", found_in=["openalex"], url=""),
        SearchResult(title="T", doi="10.1/x", source="crossref", found_in=["crossref"], url="https://example.org/x"),
    )
    assert merged_sr.url == "https://example.org/x"
    assert merged_sr.found_in == ["openalex", "crossref"]

    merged_dicts = _merge_search_dict_candidates([
        {
            "title": "T",
            "doi": "10.1/x",
            "source": "openalex",
            "found_in": ["openalex"],
            "source_records": [{"source": "openalex", "title": "T"}],
            "backend_records": [{"source": "openalex", "title": "T"}],
        },
        {
            "title": "T",
            "doi": "10.1/x",
            "source": "crossref",
            "url": "https://example.org/x",
            "source_records": [{"source": "crossref", "title": "T"}],
            "backend_records": [{"source": "crossref", "title": "T"}],
        },
    ])
    assert len(merged_dicts) == 1
    assert merged_dicts[0]["url"] == "https://example.org/x"
    assert merged_dicts[0]["found_in"] == ["openalex", "crossref"]
    assert merged_dicts[0]["backends"] == ["openalex", "crossref"]
    assert len(merged_dicts[0]["source_records"]) == 2
    assert len(merged_dicts[0]["backend_records"]) == 2


def test_to_papers_input_splits_semicolon_authors_and_preserves_pdf_url_and_backend_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "research_hub.search.abstract_recovery.recover_abstract",
        lambda *_a, **_kw: SimpleNamespace(text="", source=""),
    )
    [entry] = _to_papers_input(
        [
            {
                "title": "Classic Monograph",
                "doi": "",
                "authors": "Smith, Jane; Doe, John",
                "year": 1890,
                "abstract": "Observed.",
                "pdf_url": "https://example.org/classic.pdf",
                "backend_records": [{"source": "openalex", "title": "Classic Monograph"}],
            }
        ],
        "classics",
    )
    assert entry["authors"] == [
        {"creatorType": "author", "firstName": "Jane", "lastName": "Smith"},
        {"creatorType": "author", "firstName": "John", "lastName": "Doe"},
    ]
    assert entry["pdf_url"] == "https://example.org/classic.pdf"
    assert entry["backend_records"] == [{"source": "openalex", "title": "Classic Monograph"}]


def test_fit_check_string_index_and_duplicate_title_disambiguation(tmp_path: Path) -> None:
    from research_hub.discover import CANDIDATES_FILENAME, DiscoverState, STATE_FILENAME, discover_continue, stash_dir

    candidates = [
        {"title": "Collected Philosophical Works", "doi": "", "year": 1750, "authors": ["Hume, David"]},
        {"title": "Collected Philosophical Works", "doi": "", "year": 2021, "authors": ["Other, Author"]},
    ]
    report = apply_scores(
        "philosophy",
        candidates,
        [
            {"index": " 1 ", "title": "Collected Philosophical Works", "score": 5, "reason": "classic"},
            {"index": "2", "title": "Collected Philosophical Works", "score": 1, "reason": "off topic"},
            {"index": "0", "score": 5, "reason": "invalid zero"},
            {"index": 1.0, "score": 5, "reason": "invalid float"},
            {"index": "²", "score": 5, "reason": "invalid unicode digit"},
        ],
        threshold=3,
    )
    assert len(report.accepted) == 1
    assert report.accepted[0].index == 1
    assert report.accepted[0].score == 5
    assert len(report.rejected) == 1
    assert report.rejected[0].index == 2
    assert report.rejected[0].score == 1

    cfg = _cfg(tmp_path)
    dest = stash_dir(cfg, "philosophy")
    dest.mkdir(parents=True, exist_ok=True)
    (dest / STATE_FILENAME).write_text(
        DiscoverState(cluster_slug="philosophy", stage="scored_pending", query="works", candidate_count=2).to_json(),
        encoding="utf-8",
    )
    (dest / CANDIDATES_FILENAME).write_text(json.dumps(candidates), encoding="utf-8")
    _state, out_path = discover_continue(
        cfg,
        "philosophy",
        [
            {"index": "1", "title": "Collected Philosophical Works", "score": 5, "reason": "classic"},
            {"index": "2", "title": "Collected Philosophical Works", "score": 1, "reason": "off topic"},
        ],
        threshold=3,
    )
    papers_out = json.loads(out_path.read_text(encoding="utf-8"))
    assert len(papers_out) == 1
    assert papers_out[0]["year"] == 1750


def test_in_batch_and_vault_note_identity_enforce_metadata_even_without_doi(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from research_hub.dedup import DedupHit

    # DOI-less papers sharing a title must still check year, authors, volume, edition.
    assert _in_batch_title_match_ok(
        {"title": "Atlas of Hydrological Systems", "doi": "", "year": 1950, "authors": ["Mercator, Gerardus"]},
        {"title": "Atlas of Hydrological Systems", "doi": "", "year": 2020, "authors": ["Smith, Bob"]},
    ) is False
    assert _in_batch_title_match_ok(
        {"title": "Atlas of Hydrological Systems", "doi": "", "year": 2020, "authors": ["Smith, Bob"], "volume": "1"},
        {"title": "Atlas of Hydrological Systems", "doi": "", "year": 2020, "authors": ["Smith, Bob"], "volume": "2"},
    ) is False
    assert _in_batch_title_match_ok(
        {"title": "Atlas of Hydrological Systems", "doi": "", "year": 2020, "authors": ["Smith, Bob"], "edition": "1st"},
        {"title": "Atlas of Hydrological Systems", "doi": "", "year": 2020, "authors": ["Smith, Bob"], "edition": "2nd"},
    ) is False

    # DedupIndex.lookup must not match conflicting non-empty real DOIs on title fallback.
    idx = DedupIndex()
    idx.add(DedupHit(source="obsidian", doi="10.1000/one", title="Atlas of Hydrological Systems"))
    assert idx.lookup(doi="10.1000/two", title="Atlas of Hydrological Systems") == []

    # Vault note with conflicting zotero-key / year / authors must NOT be overwritten or skipped.
    cfg = _cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="atlas", name="Atlas", slug="atlas")
    monkeypatch.setenv("RESEARCH_HUB_NO_ZOTERO", "1")
    monkeypatch.setattr(pipeline, "get_config", lambda: cfg)
    monkeypatch.setattr(pipeline.time, "sleep", lambda _s: None)
    monkeypatch.setattr("research_hub.pipeline.update_cluster_links", lambda *a, **k: None)
    monkeypatch.setattr(
        "research_hub.authenticity.verify_authenticity",
        lambda papers, *_a, **_kw: (papers, []),
    )

    folder = cfg.raw / "atlas"
    folder.mkdir(parents=True, exist_ok=True)
    existing_note = folder / "smith2020-atlas-hydrological-systems.md"
    existing_note.write_text(
        "---\n"
        'title: "Atlas of Hydrological Systems"\n'
        'doi: ""\n'
        'year: 1950\n'
        'authors: "Mercator, Gerardus"\n'
        'zotero-key: "ZKEY_A"\n'
        "---\nOriginal classic note\n",
        encoding="utf-8",
    )
    assert pipeline._is_same_work_note(
        existing_note,
        {
            "title": "Atlas of Hydrological Systems",
            "doi": "",
            "year": 2020,
            "authors": [{"creatorType": "author", "firstName": "Bob", "lastName": "Smith"}],
            "zotero_key": "ZKEY_B",
        },
    ) is False

    dedup = DedupIndex()
    dedup.add(
        DedupHit(
            source="obsidian",
            doi="",
            title="Atlas of Hydrological Systems",
            zotero_key="ZKEY_A",
            obsidian_path=str(existing_note),
        )
    )
    monkeypatch.setattr(pipeline, "_load_or_build_dedup", lambda *a, **k: dedup)

    incoming_paper = _paper(
        title="Atlas of Hydrological Systems",
        doi="",
        arxiv_id="2001.12345",
        year=2020,
        authors=[{"creatorType": "author", "firstName": "Bob", "lastName": "Smith"}],
        slug="smith2020-atlas-hydrological-systems",
        sub_category="atlas",
        summary="2020 paper summary",
    )
    (cfg.root / "papers_input.json").write_text(
        json.dumps({"papers": [incoming_paper]}),
        encoding="utf-8",
    )
    rc = run_pipeline(dry_run=False, cluster_slug="atlas", verify=False)
    assert rc == 0
    notes = sorted(p.name for p in folder.glob("*.md"))
    assert notes == [
        "smith2020-atlas-hydrological-systems-2.md",
        "smith2020-atlas-hydrological-systems.md",
    ]
    assert "Original classic note" in existing_note.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 6. v1.3.3 astra 07b closeout regressions (§§1-3)
# ---------------------------------------------------------------------------


def test_pair_agrees_rejects_correction_and_volume_markers_and_year_bound_is_2100() -> None:
    article = {
        "source": "openalex",
        "title": "Flood Forecasting with Neural Networks",
        "year": 2024,
        "authors": ["Doe, Jane"],
    }
    correction = {
        "source": "crossref",
        "title": "Correction: Flood Forecasting with Neural Networks",
        "year": 2025,
        "authors": ["Doe, Jane"],
    }
    assert auth._pair_agrees(article, correction) is False
    assert (
        _corroboration_label(
            _paper(
                title=article["title"],
                year=2024,
                backends=["openalex", "crossref"],
                source_records=[article, correction],
            )
        )
        == "conflict"
    )
    assert (
        auth._pair_agrees(
            {"source": "openalex", "title": "History of Science Vol. I", "year": 2020, "authors": ["Doe"]},
            {"source": "crossref", "title": "History of Science Vol. II", "year": 2020, "authors": ["Doe"]},
        )
        is False
    )
    assert auth._metadata_integrity_reason(_paper(year=2100)) == ""
    assert auth._metadata_integrity_reason(_paper(year=2101)) == "year out of range"
    assert auth._metadata_integrity_reason(_paper(year=999)) == "year out of range"


def test_merge_results_retains_conflicting_source_records_for_corroboration() -> None:
    from research_hub.search._rank import merge_results
    from research_hub.search.base import SearchResult

    r1 = SearchResult(
        title="Early Hydrological Monograph",
        doi="10.1000/shared-doi",
        year=1990,
        authors=["Alice Smith"],
        abstract="Observed abstract.",
        source="openalex",
    )
    r2 = SearchResult(
        title="Modern Deep Learning Study",
        doi="10.1000/shared-doi",
        year=2020,
        authors=["Bob Jones"],
        abstract="Other observed abstract.",
        source="crossref",
    )
    merged = merge_results({"openalex": [r1], "crossref": [r2]})
    assert len(merged) == 1
    assert len(merged[0].source_records) == 2
    candidate = _to_papers_input(
        [
            {
                "title": merged[0].title,
                "doi": merged[0].doi,
                "year": merged[0].year,
                "authors": merged[0].authors,
                "abstract": merged[0].abstract,
                "found_in": merged[0].found_in,
                "source_records": merged[0].source_records,
            }
        ],
        "agents",
    )[0]
    assert _corroboration_label(candidate) == "conflict"


def test_discover_merge_and_to_papers_input_handle_dict_authors_and_extra_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from research_hub.discover import _merge_search_dict_candidates

    monkeypatch.setattr(
        "research_hub.search.abstract_recovery.recover_abstract",
        lambda *_a, **_kw: SimpleNamespace(text="", source=""),
    )
    merged = _merge_search_dict_candidates(
        [
            {
                "title": "Structured Authors Study",
                "doi": "10.1000/struct-1",
                "authors": [{"creatorType": "author", "firstName": "Jane", "lastName": "Smith"}],
                "year": 2024,
                "abstract": "Real abstract.",
                "edition": "2nd",
                "fit_index": 3,
                "corroborating_records": [{"source": "openalex", "title": "Structured Authors Study"}],
                "_discover_meta": {"matched_variations": ["q1"], "source_tags": ["openalex"], "is_seed": False},
            },
            {
                "title": "Structured Authors Study",
                "doi": "10.1000/struct-1",
                "source": "crossref",
                "corroborating_records": [{"source": "crossref", "title": "Structured Authors Study"}],
                "_discover_meta": {"matched_variations": ["q2"], "source_tags": ["crossref"], "is_seed": False},
            },
        ]
    )
    assert len(merged) == 1
    assert len(merged[0]["corroborating_records"]) == 2
    assert merged[0]["edition"] == "2nd"
    assert merged[0]["fit_index"] == 3

    [entry] = _to_papers_input(merged, "agents")
    assert entry["authors"] == [{"creatorType": "author", "firstName": "Jane", "lastName": "Smith"}]
    assert entry["slug"].startswith("smith2024-")
    assert entry["edition"] == "2nd"
    assert entry["fit_index"] == 3
    assert len(entry["corroborating_records"]) == 2
    assert entry["_discover_meta"]["matched_variations"] == ["q1", "q2"]

    [named_entry] = _to_papers_input(
        [{"title": "Named Author Study", "doi": "", "authors": [{"name": "John Doe"}], "year": 2023, "abstract": "Obs."}],
        "agents",
    )
    assert named_entry["authors"] == [{"creatorType": "author", "firstName": "John", "lastName": "Doe"}]


def test_fit_check_duplicate_title_and_conflicting_doi_do_not_misroute_into_l4(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from research_hub.discover import CANDIDATES_FILENAME, DiscoverState, STATE_FILENAME, discover_continue, stash_dir

    # Conflicting DOI or unindexed duplicate title must NOT fall back to by_title.
    cands = [
        {"title": "Collected Philosophical Works", "doi": "10.1000/real-doi"},
        {"title": "Collected Philosophical Works", "doi": ""},
    ]
    report = apply_scores(
        "philosophy",
        cands,
        [
            {"doi": "10.1000/other-doi", "title": "Collected Philosophical Works", "score": 5, "reason": "wrong doi"},
            {"title": "Collected Philosophical Works", "score": 5, "reason": "ambiguous no index"},
        ],
        threshold=3,
    )
    assert report.accepted == []

    # End-to-end: accepted 1750 book vs rejected 2021 book sharing identical title.
    cfg = _cfg(tmp_path)
    _ok_head(monkeypatch)
    monkeypatch.setattr(
        "research_hub.search.abstract_recovery.recover_abstract",
        lambda *_a, **_kw: SimpleNamespace(text="", source=""),
    )
    dup_cands = [
        {
            "title": "Collected Philosophical Works",
            "doi": "",
            "isbn": "978-0-14-044913-6",
            "year": 1750,
            "authors": ["Hume, David"],
            "abstract": "Classic treatise.",
            "source": "openalex",
            "citation_count": 50,
        },
        {
            "title": "Collected Philosophical Works",
            "doi": "",
            "isbn": "978-0-14-044914-3",
            "year": 2021,
            "authors": ["Other, Author"],
            "abstract": "Unrelated volume.",
            "source": "openalex",
            "citation_count": 50,
        },
    ]
    dest = stash_dir(cfg, "philosophy")
    dest.mkdir(parents=True, exist_ok=True)
    (dest / STATE_FILENAME).write_text(
        DiscoverState(cluster_slug="philosophy", stage="scored_pending", query="works", candidate_count=2).to_json(),
        encoding="utf-8",
    )
    (dest / CANDIDATES_FILENAME).write_text(json.dumps(dup_cands), encoding="utf-8")
    _state, out_path = discover_continue(
        cfg,
        "philosophy",
        [
            {"index": 1, "title": "Collected Philosophical Works", "score": 5, "reason": "classic"},
            {"index": 2, "title": "Collected Philosophical Works", "score": 1, "reason": "off topic"},
        ],
        threshold=3,
    )
    papers_out = json.loads(out_path.read_text(encoding="utf-8"))
    assert len(papers_out) == 1
    assert papers_out[0]["fit_index"] == 1
    accepted, quarantined = verify_authenticity(papers_out, cfg, cluster_slug="philosophy", do_fit_check=True)
    assert quarantined == []
    assert len(accepted) == 1
    assert accepted[0]["year"] == 1750
    assert accepted[0]["provenance"]["fit_score"] == 5


def test_note_identity_rejects_key_doi_title_conflicts_and_roundtrips_edition(
    tmp_path: Path,
) -> None:
    assert _in_batch_title_match_ok(
        {"title": "Shared Title Study", "zotero_key": "ZKEY1"},
        {"title": "Shared Title Study", "zotero_key": "ZKEY2"},
    ) is False

    note_path = tmp_path / "note.md"
    rendered = pipeline._render_obsidian_note(
        {
            "title": "Principles of Economics",
            "doi": "10.1000/econ-ed1",
            "zotero_key": "ZKEY_A",
            "authors": [{"creatorType": "author", "firstName": "Alfred", "lastName": "Marshall"}],
            "year": 1890,
            "edition": "1st",
            "abstract": "Classic text.",
        },
        "Economics",
        "econ",
        "economics",
    )
    note_path.write_text(rendered, encoding="utf-8")
    ident = pipeline._read_note_identity(note_path)
    assert ident["edition"] == "1st"

    # Equal Zotero keys with conflicting DOIs -> False.
    assert pipeline._is_same_work_note(
        note_path,
        {
            "title": "Principles of Economics",
            "doi": "10.1000/different-doi",
            "zotero_key": "ZKEY_A",
            "authors": [{"creatorType": "author", "firstName": "Alfred", "lastName": "Marshall"}],
            "year": 1890,
        },
    ) is False
    # Equal DOIs with conflicting Zotero keys -> False.
    assert pipeline._is_same_work_note(
        note_path,
        {
            "title": "Principles of Economics",
            "doi": "10.1000/econ-ed1",
            "zotero_key": "ZKEY_B",
            "authors": [{"creatorType": "author", "firstName": "Alfred", "lastName": "Marshall"}],
            "year": 1890,
        },
    ) is False
    # Equal DOIs with conflicting authors or edition -> False.
    assert pipeline._is_same_work_note(
        note_path,
        {
            "title": "Principles of Economics",
            "doi": "10.1000/econ-ed1",
            "zotero_key": "ZKEY_A",
            "authors": [{"creatorType": "author", "firstName": "Other", "lastName": "Person"}],
            "year": 1890,
        },
    ) is False
    assert pipeline._is_same_work_note(
        note_path,
        {
            "title": "Principles of Economics",
            "doi": "10.1000/econ-ed1",
            "zotero_key": "ZKEY_A",
            "authors": [{"creatorType": "author", "firstName": "Alfred", "lastName": "Marshall"}],
            "year": 1890,
            "edition": "2nd",
        },
    ) is False
    # Equal DOIs with completely different title -> False.
    assert pipeline._is_same_work_note(
        note_path,
        {
            "title": "Unrelated Quantum Chemistry Paper",
            "doi": "10.1000/econ-ed1",
            "zotero_key": "ZKEY_A",
            "authors": [{"creatorType": "author", "firstName": "Alfred", "lastName": "Marshall"}],
            "year": 1890,
        },
    ) is False
    # Compatible metadata -> True.
    assert pipeline._is_same_work_note(
        note_path,
        {
            "title": "Principles of Economics",
            "doi": "10.1000/econ-ed1",
            "zotero_key": "ZKEY_A",
            "authors": [{"creatorType": "author", "firstName": "Alfred", "lastName": "Marshall"}],
            "year": 1890,
            "edition": "1st",
        },
    ) is True


# ---------------------------------------------------------------------------
# 7. v1.3.4 astra 07c closeout regressions (§§2-3)
# ---------------------------------------------------------------------------


def test_v134_l4_unscored_and_ambiguous_title_never_inherit_other_work_score(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _cfg(tmp_path)
    _ok_head(monkeypatch)
    cluster_dir = cfg.hub / "agents"
    cluster_dir.mkdir(parents=True, exist_ok=True)
    (cluster_dir / ".fit_check_accepted.json").write_text(
        json.dumps(
            {
                "cluster_slug": "agents",
                "threshold": 3,
                "accepted": [
                    {
                        "index": 1,
                        "doi": "10.1234/scored",
                        "title": "Shared Monograph Title",
                        "score": 5,
                        "reason": "relevant",
                        "kept": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    fit_scores = auth._load_fit_scores(cfg, "agents")
    for idx in (None, 1, 99):
        candidate = _paper(title="Shared Monograph Title", doi="10.1234/unscored")
        if idx is not None:
            candidate["fit_index"] = idx
        status = auth._fit_status_for_paper(candidate, fit_scores, 3)
        assert status == {"kept": False, "reason": "relevance_unjudged", "score": None}

    # Two items sharing a normalized title (different DOI / index) mark title:<ntitle> ambiguous.
    (cluster_dir / ".fit_check_rejected.json").write_text(
        json.dumps(
            {
                "cluster_slug": "agents",
                "threshold": 3,
                "rejected": [
                    {
                        "index": 2,
                        "doi": "",
                        "title": "Shared Monograph Title",
                        "score": 1,
                        "reason": "off topic",
                        "kept": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    ambiguous_scores = auth._load_fit_scores(cfg, "agents")
    unindexed = _paper(title="Shared Monograph Title", doi="")
    assert auth._fit_status_for_paper(unindexed, ambiguous_scores, 3) == {
        "kept": False,
        "reason": "relevance_unjudged",
        "score": None,
    }
    exact_doi = _paper(title="Shared Monograph Title", doi="10.1234/scored")
    assert auth._fit_status_for_paper(exact_doi, ambiguous_scores, 3) == {
        "kept": True,
        "reason": "",
        "score": 5,
    }
    exact_idx = _paper(title="Shared Monograph Title", doi="", fit_index=2)
    assert auth._fit_status_for_paper(exact_idx, ambiguous_scores, 3) == {
        "kept": False,
        "reason": "low_relevance",
        "score": 1,
    }


def test_v134_merge_search_dict_candidates_synthesizes_records_without_prebuilt_arrays() -> None:
    from research_hub.discover import _merge_search_dict_candidates

    merged = _merge_search_dict_candidates(
        [
            {
                "title": "Early Hydrological Treatise",
                "doi": "10.1234/conflict-dict",
                "year": 1990,
                "authors": ["Smith, Alice"],
                "source": "openalex",
            },
            {
                "title": "Modern Neural Network Paper",
                "doi": "10.1234/conflict-dict",
                "year": 2020,
                "authors": ["Jones, Bob"],
                "source": "crossref",
            },
        ]
    )
    assert len(merged) == 1
    assert len(merged[0]["source_records"]) == 2
    assert _corroboration_label(merged[0]) == "conflict"


def test_v134_in_batch_doi_dedup_obsidian_and_zotero_hit_guards_and_zotero_roundtrip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from research_hub.dedup import DedupHit
    from research_hub.zotero.fetch import _yaml_scalar, extract_item_data, make_raw_md

    # 1. In-batch dedup must NOT collapse same-DOI candidates with differing zotero_key/edition/year.
    cfg = _cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="econ", name="Econ", slug="econ")
    monkeypatch.setenv("RESEARCH_HUB_NO_ZOTERO", "1")
    monkeypatch.setattr(pipeline, "get_config", lambda: cfg)
    monkeypatch.setattr(pipeline, "_load_or_build_dedup", lambda *a, **k: DedupIndex())
    monkeypatch.setattr(pipeline.time, "sleep", lambda _s: None)
    monkeypatch.setattr("research_hub.pipeline.update_cluster_links", lambda *a, **k: None)
    monkeypatch.setattr(
        "research_hub.authenticity.verify_authenticity",
        lambda papers, *_a, **_kw: (papers, []),
    )

    p1 = _paper(
        title="Principles of Economics",
        doi="10.1234/shared",
        zotero_key="ZKEY1",
        edition="1st",
        slug="doe2025-principles-1",
        sub_category="econ",
    )
    p2 = _paper(
        title="Principles of Economics",
        doi="10.1234/shared",
        zotero_key="ZKEY2",
        edition="2nd",
        slug="doe2025-principles-2",
        sub_category="econ",
    )
    (cfg.root / "papers_input.json").write_text(json.dumps({"papers": [p1, p2]}), encoding="utf-8")
    assert run_pipeline(dry_run=False, cluster_slug="econ", verify=False) == 0
    assert sorted(p.name for p in (cfg.raw / "econ").glob("*.md")) == [
        "doe2025-principles-1.md",
        "doe2025-principles-2.md",
    ]
    manifest_actions = [
        json.loads(line)["action"]
        for line in (cfg.research_hub_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert "dup-in-batch" not in manifest_actions

    # 2. _obsidian_hit_matches_paper must still run _is_same_work_note even when DOI matches.
    note_path = tmp_path / "disk_note.md"
    note_path.write_text(
        make_raw_md(
            {
                "key": "ZKEY1",
                "title": "Principles of Economics",
                "authors": ["Marshall, Alfred"],
                "year": "1890",
                "journal": "Macmillan",
                "volume": "1",
                "edition": "1st",
                "doi": "10.1234/shared",
                "abstract": "Classic text.",
                "tags": [],
            },
            ["Econ"],
            [],
            topic_cluster="econ",
        ),
        encoding="utf-8",
    )
    hit_same_doi = DedupHit(
        source="obsidian",
        doi="10.1234/shared",
        title="Principles of Economics",
        zotero_key="ZKEY1",
        obsidian_path=str(note_path),
    )
    assert (
        pipeline._obsidian_hit_matches_paper(
            hit_same_doi,
            {
                "title": "Principles of Economics",
                "doi": "10.1234/shared",
                "zotero_key": "ZKEY1",
                "edition": "2nd",
                "authors": [{"creatorType": "author", "firstName": "Alfred", "lastName": "Marshall"}],
                "year": 1890,
            },
        )
        is False
    )
    assert (
        pipeline._obsidian_hit_matches_paper(
            hit_same_doi,
            {
                "title": "Completely Different Title",
                "doi": "10.1234/shared",
                "zotero_key": "ZKEY1",
                "authors": [{"creatorType": "author", "firstName": "Other", "lastName": "Author"}],
                "year": 2020,
            },
        )
        is False
    )

    # 3. _zotero_hit_matches_paper rejects incompatible title or volume markers.
    z_hit = DedupHit(source="zotero", doi="10.1234/shared", title="History of Science Vol. I", zotero_key="ZK1")
    assert pipeline._zotero_hit_matches_paper(z_hit, {"doi": "10.1234/shared", "title": "History of Science Vol. II"}) is False
    assert pipeline._zotero_hit_matches_paper(z_hit, {"doi": "10.1234/shared", "title": "Completely Unrelated"}) is False

    # 4. _yaml_scalar & extract_item_data -> make_raw_md -> _read_note_identity round-trip edition & volume.
    assert _yaml_scalar('2nd "Revised"') == '2nd \\"Revised\\"'
    extracted = extract_item_data(
        {
            "key": "ZBOOK1",
            "data": {
                "itemType": "book",
                "title": "Principles of Economics",
                "creators": [{"creatorType": "author", "firstName": "Alfred", "lastName": "Marshall"}],
                "date": "1890",
                "publisher": "Macmillan",
                "volume": "2",
                "issue": "1",
                "pages": "1-500",
                "edition": '2nd "Revised"',
                "DOI": "",
                "abstractNote": "Classic.",
                "tags": [],
            },
        }
    )
    assert extracted is not None
    assert extracted["volume"] == "2"
    assert extracted["edition"] == '2nd "Revised"'
    roundtrip_path = tmp_path / "zotero_roundtrip.md"
    roundtrip_path.write_text(make_raw_md(extracted, ["Econ"], []), encoding="utf-8")
    ident = pipeline._read_note_identity(roundtrip_path)
    assert ident["volume"] == "2"
    assert ident["edition"] == '2nd "Revised"'
