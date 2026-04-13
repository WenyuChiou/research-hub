from __future__ import annotations

from unittest.mock import patch

from research_hub.search import SearchResult
from research_hub.search.fallback import _BACKEND_REGISTRY, search_papers


@patch("research_hub.search.fallback.DblpBackend.search")
@patch("research_hub.search.fallback.CrossrefBackend.search")
@patch("research_hub.search.fallback.SemanticScholarClient.search")
@patch("research_hub.search.fallback.ArxivBackend.search")
@patch("research_hub.search.fallback.OpenAlexBackend.search")
def test_fallback_merges_by_doi(mock_openalex, _mock_arxiv, mock_s2, _mock_crossref, _mock_dblp):
    mock_openalex.return_value = [SearchResult(title="Paper", doi="10.1/a", year=2024, source="openalex")]
    mock_s2.return_value = [SearchResult(title="Paper", doi="10.1/a", citation_count=42, source="semantic-scholar")]

    results = search_papers("query")

    assert len(results) == 1
    assert results[0].year == 2024
    assert results[0].citation_count == 42
    assert results[0].found_in == ["openalex", "semantic-scholar"]
    assert results[0].confidence == 0.75


@patch("research_hub.search.fallback.DblpBackend.search")
@patch("research_hub.search.fallback.CrossrefBackend.search")
@patch("research_hub.search.fallback.SemanticScholarClient.search")
@patch("research_hub.search.fallback.ArxivBackend.search")
@patch("research_hub.search.fallback.OpenAlexBackend.search")
def test_fallback_merges_by_arxiv_id_when_no_doi(mock_openalex, mock_arxiv, mock_s2, _mock_crossref, _mock_dblp):
    mock_openalex.return_value = [SearchResult(title="Paper", arxiv_id="2411.12345", source="openalex")]
    mock_arxiv.return_value = [SearchResult(title="Paper", arxiv_id="2411.12345", abstract="Abstract", source="arxiv")]
    mock_s2.return_value = []

    results = search_papers("query")

    assert len(results) == 1
    assert results[0].abstract == "Abstract"


@patch("research_hub.search.fallback.DblpBackend.search")
@patch("research_hub.search.fallback.CrossrefBackend.search")
@patch("research_hub.search.fallback.SemanticScholarClient.search")
@patch("research_hub.search.fallback.ArxivBackend.search")
@patch("research_hub.search.fallback.OpenAlexBackend.search")
def test_fallback_prefers_first_backend_for_non_empty_fields(mock_openalex, mock_arxiv, mock_s2, _mock_crossref, _mock_dblp):
    mock_openalex.return_value = [SearchResult(title="Long title", doi="10.1/a", source="openalex")]
    mock_arxiv.return_value = [SearchResult(title="Short title", doi="10.1/a", source="arxiv")]
    mock_s2.return_value = []

    results = search_papers("query")

    assert results[0].title == "Long title"


@patch("research_hub.search.fallback.DblpBackend.search")
@patch("research_hub.search.fallback.CrossrefBackend.search")
@patch("research_hub.search.fallback.SemanticScholarClient.search")
@patch("research_hub.search.fallback.ArxivBackend.search")
@patch("research_hub.search.fallback.OpenAlexBackend.search")
def test_fallback_skips_failing_backend(mock_openalex, mock_arxiv, mock_s2, _mock_crossref, _mock_dblp):
    mock_openalex.side_effect = ConnectionError("boom")
    mock_arxiv.return_value = [SearchResult(title="Paper", arxiv_id="2411.12345", source="arxiv")]
    mock_s2.return_value = []

    results = search_papers("query")

    assert len(results) == 1
    assert results[0].source == "arxiv"


@patch("research_hub.search.fallback.DblpBackend.search")
@patch("research_hub.search.fallback.CrossrefBackend.search")
@patch("research_hub.search.fallback.SemanticScholarClient.search")
@patch("research_hub.search.fallback.ArxivBackend.search")
@patch("research_hub.search.fallback.OpenAlexBackend.search")
def test_fallback_respects_min_citations_filter(mock_openalex, mock_arxiv, mock_s2, _mock_crossref, _mock_dblp):
    mock_openalex.return_value = [
        SearchResult(title="A", doi="10.1/a", citation_count=0, source="openalex"),
        SearchResult(title="B", doi="10.1/b", citation_count=5, source="openalex"),
        SearchResult(title="C", doi="10.1/c", citation_count=100, source="openalex"),
    ]
    mock_arxiv.return_value = []
    mock_s2.return_value = []

    results = search_papers("query", min_citations=10)

    assert [item.title for item in results] == ["C"]


@patch("research_hub.search.fallback.DblpBackend.search")
@patch("research_hub.search.fallback.CrossrefBackend.search")
@patch("research_hub.search.fallback.SemanticScholarClient.search")
@patch("research_hub.search.fallback.ArxivBackend.search")
@patch("research_hub.search.fallback.OpenAlexBackend.search")
def test_fallback_sorts_by_year_desc_then_citations_desc(mock_openalex, mock_arxiv, mock_s2, _mock_crossref, _mock_dblp):
    mock_openalex.return_value = [
        SearchResult(title="A", doi="10.1/a", year=2023, citation_count=100, source="openalex"),
        SearchResult(title="B", doi="10.1/b", year=2024, citation_count=5, source="openalex"),
        SearchResult(title="C", doi="10.1/c", year=2024, citation_count=50, source="openalex"),
    ]
    mock_arxiv.return_value = []
    mock_s2.return_value = []

    results = search_papers("query", rank_by="year")

    assert [(item.year, item.citation_count) for item in results] == [(2024, 50), (2024, 5), (2023, 100)]


@patch("research_hub.search.fallback.OpenAlexBackend.search")
def test_fallback_unknown_backend_name_logs_warning_and_skips(mock_openalex, caplog):
    mock_openalex.return_value = [SearchResult(title="Paper", doi="10.1/a", source="openalex")]

    results = search_papers("query", backends=("openalex", "nonexistent"))

    assert len(results) == 1
    assert "unknown search backend: nonexistent" in caplog.text


@patch("research_hub.search.fallback.DblpBackend.search")
@patch("research_hub.search.fallback.CrossrefBackend.search")
@patch("research_hub.search.fallback.SemanticScholarClient.search")
@patch("research_hub.search.fallback.ArxivBackend.search")
@patch("research_hub.search.fallback.OpenAlexBackend.search")
def test_fallback_arxiv_skips_min_citations_filter(mock_openalex, mock_arxiv, mock_s2, _mock_crossref, _mock_dblp):
    mock_openalex.return_value = []
    mock_arxiv.return_value = [SearchResult(title="Preprint", arxiv_id="2411.12345", citation_count=0, source="arxiv")]
    mock_s2.return_value = []

    results = search_papers("query", min_citations=5)

    assert [item.title for item in results] == ["Preprint"]


@patch("research_hub.search.fallback.DblpBackend.search")
@patch("research_hub.search.fallback.CrossrefBackend.search")
@patch("research_hub.search.fallback.SemanticScholarClient.search")
@patch("research_hub.search.fallback.ArxivBackend.search")
@patch("research_hub.search.fallback.OpenAlexBackend.search")
def test_fallback_backend_trace_emits_per_backend_counts(mock_openalex, mock_arxiv, mock_s2, mock_crossref, mock_dblp, caplog):
    mock_openalex.return_value = [SearchResult(title="A", doi="10.1/a", source="openalex")]
    mock_arxiv.return_value = []
    mock_s2.return_value = []
    mock_crossref.return_value = []
    mock_dblp.return_value = []

    caplog.set_level("INFO")
    search_papers("query", backend_trace=True)

    assert "backend openalex: 1 hits" in caplog.text


def test_fallback_registers_pubmed_biorxiv_repec_backends():
    assert _BACKEND_REGISTRY["pubmed"].__name__ == "PubMedBackend"
    assert _BACKEND_REGISTRY["biorxiv"].__name__ == "BiorxivBackend"
    assert _BACKEND_REGISTRY["medrxiv"] is _BACKEND_REGISTRY["biorxiv"]
    assert _BACKEND_REGISTRY["repec"].__name__ == "RepecBackend"


def test_fallback_registers_chemrxiv_nasa_ads_eric_backends():
    assert _BACKEND_REGISTRY["chemrxiv"].__name__ == "ChemrxivBackend"
    assert _BACKEND_REGISTRY["nasa-ads"].__name__ == "NasaAdsBackend"
    assert _BACKEND_REGISTRY["eric"].__name__ == "EricBackend"
