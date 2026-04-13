from __future__ import annotations

from unittest.mock import Mock, patch

from research_hub.search.biorxiv import BiorxivBackend


def _response(payload, status_code=200):
    response = Mock()
    response.status_code = status_code
    response.json.return_value = payload
    return response


@patch("research_hub.search.biorxiv.requests.get")
def test_biorxiv_search_queries_both_servers(mock_get):
    mock_get.side_effect = [_response({"collection": []}), _response({"collection": []})]

    BiorxivBackend(delay_seconds=0).search("genomics")

    urls = [call.args[0] for call in mock_get.call_args_list]
    assert any("/details/biorxiv/" in url for url in urls)
    assert any("/details/medrxiv/" in url for url in urls)


@patch("research_hub.search.biorxiv.requests.get")
def test_biorxiv_get_paper_by_doi_with_server_prefix(mock_get):
    mock_get.side_effect = [
        _response({"collection": []}),
        _response({"collection": [{"title": "Preprint", "doi": "10.1101/foo"}]}),
    ]

    result = BiorxivBackend(delay_seconds=0).get_paper("10.1101/foo")

    assert mock_get.call_count == 2
    assert result is not None
    assert result.doi == "10.1101/foo"


@patch("research_hub.search.biorxiv.requests.get")
def test_biorxiv_year_filter_translates_to_date_range(mock_get):
    mock_get.side_effect = [_response({"collection": []}), _response({"collection": []})]

    BiorxivBackend(delay_seconds=0).search("cancer", year_from=2024)

    assert "/2024-01-01/" in mock_get.call_args_list[0].args[0]


@patch("research_hub.search.biorxiv.requests.get")
def test_biorxiv_extracts_authors_from_semicolon_separated(mock_get):
    payload = {
        "collection": [
            {
                "title": "Gene Models",
                "authors": "Jane Doe; John Roe",
                "doi": "10.1101/foo",
                "abstract": "gene models in biology",
            }
        ]
    }
    mock_get.side_effect = [_response(payload), _response({"collection": []})]

    result = BiorxivBackend(delay_seconds=0).search("gene", limit=1)[0]

    assert result.authors == ["Jane Doe", "John Roe"]


@patch("research_hub.search.biorxiv.requests.get")
def test_biorxiv_doc_type_is_preprint(mock_get):
    payload = {"collection": [{"title": "Gene Models", "doi": "10.1101/foo", "abstract": "gene models"}]}
    mock_get.side_effect = [_response(payload), _response({"collection": []})]

    result = BiorxivBackend(delay_seconds=0).search("gene", limit=1)[0]

    assert result.doc_type == "preprint"


@patch("research_hub.search.biorxiv.requests.get")
def test_biorxiv_query_filter_drops_irrelevant_papers(mock_get):
    payload = {"collection": [{"title": "Completely unrelated paper", "abstract": "nothing matching here", "doi": "10.1101/foo"}]}

    def fake_get(url, **kwargs):
        if "/details/biorxiv/" in url and url.endswith("/0"):
            return _response(payload)
        return _response({"collection": []})

    mock_get.side_effect = fake_get

    results = BiorxivBackend(delay_seconds=0).search("genomics", limit=1)

    assert results == []


def test_biorxiv_matches_query_requires_all_terms():
    """Regression: the filter was `any` which accepted any paper containing
    at least one query word. bioRxiv has no server-side text search, so
    client-side filtering must be strict AND — otherwise common words like
    "protein" and "structure" match the entire bio literature and dilute
    results beyond usability. Live test on 'protein structure prediction
    AlphaFold' returned heavy-metal-adaptation papers."""
    from research_hub.search.base import SearchResult
    from research_hub.search.biorxiv import BiorxivBackend

    backend = BiorxivBackend()
    terms = {"protein", "structure", "alphafold", "prediction"}

    # All 4 terms present — passes
    r_full = SearchResult(
        title="AlphaFold protein structure prediction benchmarks",
        abstract="We evaluate methods for protein structure prediction.",
    )
    assert backend._matches_query(r_full, terms) is True

    # 3/4 terms (missing "alphafold") — strict AND rejects
    r_three = SearchResult(
        title="Fast protein structure prediction using transformers",
        abstract="",
    )
    assert backend._matches_query(r_three, terms) is False

    # 2/4 terms (just "protein" + "structure") — rejects
    r_two = SearchResult(
        title="Protein structure stability in extreme environments",
        abstract="",
    )
    assert backend._matches_query(r_two, terms) is False

    # 1/4 terms — rejects (previously `any` accepted this)
    r_one = SearchResult(
        title="Heavy metal environment adaptation in bacteria",
        abstract="We study how populations adapt. Mentions protein once.",
    )
    assert backend._matches_query(r_one, terms) is False
