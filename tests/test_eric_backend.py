from __future__ import annotations

from unittest.mock import Mock, patch

from research_hub.search.eric import EricBackend


def _response(payload=None, *, status_code=200):
    response = Mock()
    response.status_code = status_code
    response.json.return_value = payload
    return response


@patch("research_hub.search.eric.requests.get")
def test_eric_search_uses_format_json_param(mock_get):
    mock_get.return_value = _response({"response": {"docs": []}})

    EricBackend(delay_seconds=0).search("literacy")

    assert mock_get.call_args.kwargs["params"]["format"] == "json"


@patch("research_hub.search.eric.requests.get")
def test_eric_search_year_filter_uses_publicationdateyear(mock_get):
    mock_get.return_value = _response({"response": {"docs": []}})

    EricBackend(delay_seconds=0).search("literacy", year_from=2024, year_to=2025)

    assert "publicationdateyear:[2024 TO 2025]" in mock_get.call_args.kwargs["params"]["search"]


@patch("research_hub.search.eric.requests.get")
def test_eric_search_extracts_title_authors_year_description(mock_get):
    mock_get.return_value = _response(
        {
            "response": {
                "docs": [
                    {
                        "id": "EJ123456",
                        "title": "Education Study",
                        "author": ["Jane Doe", "John Roe"],
                        "description": "Abstract text",
                        "publicationdateyear": "2023",
                        "source": "Journal of Education",
                        "doi": "10.1000/ERIC.TEST",
                    }
                ]
            }
        }
    )

    result = EricBackend(delay_seconds=0).search("education")[0]

    assert result.title == "Education Study"
    assert result.authors == ["Jane Doe", "John Roe"]
    assert result.year == 2023
    assert result.abstract == "Abstract text"


@patch("research_hub.search.eric.requests.get")
def test_eric_search_handles_authors_as_string_or_list(mock_get):
    mock_get.return_value = _response(
        {
            "response": {
                "docs": [
                    {"id": "EJ1", "title": "One", "author": "Single Author"},
                    {"id": "EJ2", "title": "Two", "author": ["A", "B"]},
                ]
            }
        }
    )

    results = EricBackend(delay_seconds=0).search("education")

    assert results[0].authors == ["Single Author"]
    assert results[1].authors == ["A", "B"]


@patch("research_hub.search.eric.requests.get")
def test_eric_doc_type_journal_article_for_ej_id(mock_get):
    mock_get.return_value = _response({"response": {"docs": [{"id": "EJ123", "title": "Article"}]}})

    result = EricBackend(delay_seconds=0).search("article")[0]

    assert result.doc_type == "journal-article"


@patch("research_hub.search.eric.requests.get")
def test_eric_doc_type_report_for_ed_id(mock_get):
    mock_get.return_value = _response({"response": {"docs": [{"id": "ED123", "title": "Report"}]}})

    result = EricBackend(delay_seconds=0).search("report")[0]

    assert result.doc_type == "report"


@patch.object(EricBackend, "search")
def test_eric_get_paper_by_eric_id_uses_id_field(mock_search):
    mock_search.return_value = []

    EricBackend(delay_seconds=0).get_paper("EJ123456")

    assert mock_search.call_args.args[0] == "id:EJ123456"


@patch("research_hub.search.eric.requests.get")
def test_eric_returns_empty_on_500(mock_get):
    mock_get.return_value = _response(status_code=500)

    assert EricBackend(delay_seconds=0).search("education") == []
