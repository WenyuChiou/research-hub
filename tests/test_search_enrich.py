from __future__ import annotations

from unittest.mock import patch

from research_hub.search import SearchResult
from research_hub.search.enrich import classify_candidate, enrich_candidates


def test_classify_candidate_detects_doi():
    assert classify_candidate("10.1234/foo") == "doi"


def test_classify_candidate_detects_arxiv_id():
    assert classify_candidate("2411.12345v2") == "arxiv"


def test_classify_candidate_defaults_to_title():
    assert classify_candidate("A Great Paper Title") == "title"


@patch("research_hub.search.enrich.SemanticScholarClient.get_paper")
@patch("research_hub.search.enrich.ArxivBackend.get_paper")
@patch("research_hub.search.enrich.OpenAlexBackend.get_paper")
def test_enrich_candidates_uses_first_backend_that_resolves_doi(mock_openalex, mock_arxiv, mock_s2):
    mock_openalex.return_value = SearchResult(title="Paper", doi="10.1234/foo", source="openalex")
    mock_arxiv.side_effect = RuntimeError("should not be used")
    mock_s2.side_effect = RuntimeError("should not be used")

    result = enrich_candidates(["10.1234/foo"])

    assert result[0] is not None
    assert result[0].source == "openalex"


@patch("research_hub.search.enrich.SemanticScholarClient.search")
@patch("research_hub.search.enrich.ArxivBackend.search")
@patch("research_hub.search.enrich.OpenAlexBackend.search")
def test_enrich_candidates_falls_through_on_low_title_similarity(mock_openalex, mock_arxiv, mock_s2):
    mock_openalex.return_value = [SearchResult(title="Totally Different", source="openalex")]
    mock_arxiv.return_value = []
    mock_s2.return_value = []

    result = enrich_candidates(["LLM agent benchmark"])

    assert result == [None]
