from __future__ import annotations

from unittest.mock import Mock, patch

from research_hub.search.chemrxiv import ChemrxivBackend


def _response(payload=None, *, status_code=200):
    response = Mock()
    response.status_code = status_code
    response.json.return_value = payload
    return response


@patch("research_hub.search.chemrxiv.requests.post")
def test_chemrxiv_search_uses_post_with_json_body(mock_post):
    mock_post.return_value = _response([])

    ChemrxivBackend(delay_seconds=0).search("catalyst")

    assert mock_post.called
    assert mock_post.call_args.kwargs["json"]["search_for"] == "catalyst"


@patch("research_hub.search.chemrxiv.requests.post")
def test_chemrxiv_search_includes_group_id_for_chemrxiv(mock_post):
    mock_post.return_value = _response([])

    ChemrxivBackend(delay_seconds=0).search("organic chemistry")

    assert mock_post.call_args.kwargs["json"]["group"] == 13652


@patch("research_hub.search.chemrxiv.requests.post")
def test_chemrxiv_search_extracts_title_authors_year_doi(mock_post):
    mock_post.return_value = _response(
        [
            {
                "title": "A Chemistry Preprint",
                "authors": [{"full_name": "Jane Doe"}, {"full_name": "John Roe"}],
                "published_date": "2024-03-01",
                "doi": "10.26434/CHEMRXIV-2024-ABCD",
                "description": "Abstract text",
                "url_public_html": "https://chemrxiv.org/engage/chemrxiv/article-details/123",
            }
        ]
    )

    result = ChemrxivBackend(delay_seconds=0).search("chemistry")[0]

    assert result.title == "A Chemistry Preprint"
    assert result.authors == ["Jane Doe", "John Roe"]
    assert result.year == 2024
    assert result.doi == "10.26434/chemrxiv-2024-abcd"


@patch("research_hub.search.chemrxiv.requests.post")
def test_chemrxiv_search_year_filter_uses_published_since(mock_post):
    mock_post.return_value = _response([])

    ChemrxivBackend(delay_seconds=0).search("reaction", year_from=2024)

    assert mock_post.call_args.kwargs["json"]["published_since"] == "2024-01-01"


@patch("research_hub.search.chemrxiv.requests.post")
def test_chemrxiv_search_year_to_filtered_client_side(mock_post):
    mock_post.return_value = _response(
        [
            {"title": "Old", "published_date": "2023-01-01"},
            {"title": "New", "published_date": "2025-01-01"},
        ]
    )

    results = ChemrxivBackend(delay_seconds=0).search("reaction", year_to=2024)

    assert [result.title for result in results] == ["Old"]


@patch("research_hub.search.chemrxiv.requests.post")
def test_chemrxiv_returns_empty_on_404(mock_post):
    mock_post.return_value = _response(status_code=404)

    assert ChemrxivBackend(delay_seconds=0).search("reaction") == []


@patch("research_hub.search.chemrxiv.requests.get")
def test_chemrxiv_get_paper_by_numeric_figshare_id(mock_get):
    mock_get.return_value = _response(
        {
            "title": "Specific ChemRxiv Paper",
            "doi": "10.26434/chemrxiv-2024-xyz",
            "published_date": "2024-04-15",
        }
    )

    result = ChemrxivBackend(delay_seconds=0).get_paper("123456")

    assert result is not None
    assert result.title == "Specific ChemRxiv Paper"
    assert mock_get.call_args.args[0].endswith("/123456")


@patch("research_hub.search.chemrxiv.requests.post")
def test_chemrxiv_doc_type_is_preprint(mock_post):
    mock_post.return_value = _response([{"title": "Preprint"}])

    result = ChemrxivBackend(delay_seconds=0).search("preprint")[0]

    assert result.doc_type == "preprint"
