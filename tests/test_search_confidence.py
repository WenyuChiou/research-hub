from __future__ import annotations

from research_hub.search._rank import confidence_from_backends, merge_results
from research_hub.search.base import SearchResult


def test_confidence_single_backend_is_0_5():
    assert confidence_from_backends(["openalex"]) == 0.5


def test_confidence_two_backends_is_0_75():
    assert confidence_from_backends(["openalex", "crossref"]) == 0.75


def test_confidence_three_backends_is_1_0():
    assert confidence_from_backends(["openalex", "crossref", "dblp"]) == 1.0


def test_confidence_caps_at_1_0():
    assert confidence_from_backends(["a", "b", "c", "d"]) == 1.0


def test_merge_results_by_doi():
    merged = merge_results(
        {
            "openalex": [SearchResult(title="Paper", doi="10.1/a", source="openalex")],
            "crossref": [SearchResult(title="Paper", doi="10.1/a", source="crossref")],
        }
    )

    assert len(merged) == 1
    assert merged[0].confidence == 0.75
    assert len(merged[0].found_in) == 2


def test_merge_results_by_arxiv_id_when_no_doi():
    merged = merge_results(
        {
            "openalex": [SearchResult(title="Paper", arxiv_id="2411.12345", source="openalex")],
            "arxiv": [SearchResult(title="Paper", arxiv_id="2411.12345", source="arxiv")],
        }
    )

    assert len(merged) == 1
    assert merged[0].found_in == ["openalex", "arxiv"]


def test_merge_results_by_arxiv_id_when_other_backend_also_has_doi():
    arxiv = SearchResult(
        title="Orchestrating LLM Agents for Scientific Research",
        arxiv_id="2602.18891",
        source="arxiv",
    )
    semantic_scholar = SearchResult(
        title="Orchestrating LLM Agents for Scientific Research",
        doi="10.48550/arXiv.2602.18891",
        arxiv_id="2602.18891",
        source="semantic-scholar",
    )

    for per_backend in (
        {"arxiv": [arxiv], "semantic-scholar": [semantic_scholar]},
        {"semantic-scholar": [semantic_scholar], "arxiv": [arxiv]},
        {
            "crossref": [SearchResult(
                title="Orchestrating LLM Agents for Scientific Research",
                doi="10.48550/arXiv.2602.18891",
                source="crossref",
            )],
            "arxiv": [arxiv],
            "semantic-scholar": [semantic_scholar],
        },
    ):
        merged = merge_results(per_backend)

        assert len(merged) == 1
        assert merged[0].doi == "10.48550/arXiv.2602.18891"
        assert set(merged[0].found_in) == set(per_backend)


def test_bridge_merge_preserves_first_seen_backend_and_field_precedence():
    merged = merge_results(
        {
            "arxiv": [SearchResult(
                title="First title",
                arxiv_id="2602.18891",
                abstract="First abstract",
                source="arxiv",
            )],
            "crossref": [SearchResult(
                title="Second title",
                doi="10.48550/arXiv.2602.18891",
                abstract="Second abstract",
                source="crossref",
            )],
            "semantic-scholar": [SearchResult(
                title="Bridge title",
                doi="10.48550/arXiv.2602.18891",
                arxiv_id="2602.18891",
                abstract="Bridge abstract",
                source="semantic-scholar",
            )],
        }
    )

    assert len(merged) == 1
    assert merged[0].title == "First title"
    assert merged[0].abstract == "First abstract"
    assert merged[0].source == "arxiv"
    assert merged[0].doi == "10.48550/arXiv.2602.18891"
    assert merged[0].found_in == ["arxiv", "crossref", "semantic-scholar"]


def test_merge_results_first_backend_wins_non_empty_fields():
    merged = merge_results(
        {
            "openalex": [SearchResult(title="Long", doi="10.1/a", source="openalex")],
            "arxiv": [SearchResult(title="Short", doi="10.1/a", source="arxiv")],
        }
    )

    assert merged[0].title == "Long"


def test_merge_results_fills_empty_fields_from_other_backends():
    merged = merge_results(
        {
            "openalex": [SearchResult(title="Paper", doi="10.1/a", abstract="", source="openalex")],
            "crossref": [SearchResult(title="Paper", doi="10.1/a", source="crossref")],
            "arxiv": [SearchResult(title="Paper", doi="10.1/a", abstract="Abstract", source="arxiv")],
        }
    )

    assert merged[0].abstract == "Abstract"
