from __future__ import annotations

from unittest.mock import Mock, patch

from research_hub.search.pubmed import PubMedBackend


def _json_response(payload, status_code=200):
    response = Mock()
    response.status_code = status_code
    response.json.return_value = payload
    return response


@patch("research_hub.search.pubmed.requests.get")
def test_pubmed_search_two_step_esearch_then_esummary(mock_get):
    mock_get.side_effect = [
        _json_response({"esearchresult": {"idlist": ["123"]}}),
        _json_response({"result": {"123": {"title": "Paper"}, "uids": ["123"]}}),
    ]

    PubMedBackend(delay_seconds=0).search("cancer")

    assert mock_get.call_args_list[0].args[0].endswith("esearch.fcgi")
    assert mock_get.call_args_list[1].args[0].endswith("esummary.fcgi")


@patch("research_hub.search.pubmed.requests.get")
def test_pubmed_search_extracts_pmid_doi_year_authors_from_esummary(mock_get):
    mock_get.side_effect = [
        _json_response({"esearchresult": {"idlist": ["123"]}}),
        _json_response(
            {
                "result": {
                    "123": {
                        "title": "Biomedical Discovery",
                        "pubdate": "2024 Mar 15",
                        "authors": [{"name": "Jane Doe"}, {"name": "John Roe"}],
                        "articleids": [{"idtype": "doi", "value": "10.1000/ABC"}],
                        "source": "Nature",
                    }
                }
            }
        ),
    ]

    result = PubMedBackend(delay_seconds=0).search("biomed", limit=1)[0]

    assert result.url == "https://pubmed.ncbi.nlm.nih.gov/123/"
    assert result.doi == "10.1000/abc"
    assert result.year == 2024
    assert result.authors == ["Jane Doe", "John Roe"]


@patch("research_hub.search.pubmed.requests.get")
def test_pubmed_search_handles_missing_doi(mock_get):
    mock_get.side_effect = [
        _json_response({"esearchresult": {"idlist": ["123"]}}),
        _json_response({"result": {"123": {"title": "Paper", "articleids": [{"idtype": "pmid", "value": "123"}]}}}),
    ]

    result = PubMedBackend(delay_seconds=0).search("paper", limit=1)[0]

    assert result.doi == ""


@patch("research_hub.search.pubmed.requests.get")
def test_pubmed_year_filter_uses_pdat_in_term(mock_get):
    mock_get.side_effect = [_json_response({"esearchresult": {"idlist": []}})]

    PubMedBackend(delay_seconds=0).search("genomics", year_from=2024, year_to=2025)

    assert "2024:2025[pdat]" in mock_get.call_args.kwargs["params"]["term"]


@patch("research_hub.search.pubmed.requests.get")
def test_pubmed_get_paper_by_doi_uses_doi_tag(mock_get):
    mock_get.side_effect = [_json_response({"esearchresult": {"idlist": []}})]

    PubMedBackend(delay_seconds=0).get_paper("10.1000/example")

    assert mock_get.call_args.kwargs["params"]["term"] == '"10.1000/example"[doi]'


@patch("research_hub.search.pubmed.requests.get")
def test_pubmed_returns_empty_on_404(mock_get):
    mock_get.return_value = _json_response({}, status_code=404)

    assert PubMedBackend(delay_seconds=0).search("paper") == []


@patch("research_hub.search.pubmed.requests.get")
def test_pubmed_returns_empty_on_no_pmids(mock_get):
    mock_get.return_value = _json_response({"esearchresult": {"idlist": []}})

    assert PubMedBackend(delay_seconds=0).search("paper") == []
    assert mock_get.call_count == 1


@patch("research_hub.search.pubmed.requests.get")
def test_pubmed_extracts_journal_from_source_field(mock_get):
    mock_get.side_effect = [
        _json_response({"esearchresult": {"idlist": ["123"]}}),
        _json_response({"result": {"123": {"title": "Paper", "source": "Nature Methods"}}}),
    ]

    result = PubMedBackend(delay_seconds=0).search("paper", limit=1)[0]

    assert result.venue == "Nature Methods"
