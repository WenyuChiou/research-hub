from __future__ import annotations

from research_hub.search._rank import apply_filters, rank
from research_hub.search.base import SearchResult


def _result(**overrides) -> SearchResult:
    base = SearchResult(
        title="LLM agent benchmark",
        abstract="Evaluation of agent systems",
        year=2024,
        citation_count=10,
        confidence=0.5,
        doc_type="journal-article",
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def test_apply_filters_drops_excluded_doc_type():
    results = apply_filters([_result(doc_type="report")], exclude_types=("report",))
    assert results == []


def test_apply_filters_doc_type_match_case_insensitive():
    results = apply_filters([_result(doc_type="Report")], exclude_types=("report",))
    assert results == []


def test_apply_filters_drops_excluded_term_in_title():
    results = apply_filters([_result(title="IPCC report")], exclude_terms=("ipcc",))
    assert results == []


def test_apply_filters_drops_excluded_term_in_abstract():
    results = apply_filters([_result(abstract="This covers lancet health data")], exclude_terms=("lancet",))
    assert results == []


def test_apply_filters_min_confidence_drops_low_confidence():
    results = apply_filters([_result(confidence=0.5)], min_confidence=0.75)
    assert results == []


def test_apply_filters_keeps_results_when_no_filters():
    results = apply_filters([_result()])
    assert len(results) == 1


def test_rank_smart_uses_confidence_recency_relevance():
    results = rank(
        [
            _result(title="Unrelated survey", year=2015, citation_count=500, confidence=0.5, abstract="survey"),
            _result(title="Climate migration decision modeling", year=2025, citation_count=5, confidence=1.0),
        ],
        rank_by="smart",
        current_year=2026,
        relevance_query="climate migration decision modeling",
    )

    assert results[0].title == "Climate migration decision modeling"


def test_rank_citation_legacy_uses_citation_count_desc():
    results = rank(
        [_result(title="A", citation_count=1), _result(title="B", citation_count=10)],
        rank_by="citation",
    )
    assert [item.title for item in results] == ["B", "A"]


def test_rank_year_sorts_by_recency():
    results = rank([_result(title="A", year=2023), _result(title="B", year=2025)], rank_by="year")
    assert [item.title for item in results] == ["B", "A"]


def test_rank_relevance_via_term_overlap():
    results = rank(
        [
            _result(title="LLM survey", abstract="agent methods", confidence=0.75),
            _result(title="LLM agent benchmark", abstract="benchmark details", confidence=0.75),
        ],
        rank_by="smart",
        current_year=2026,
        relevance_query="agent benchmark",
    )
    assert results[0].title == "LLM agent benchmark"
