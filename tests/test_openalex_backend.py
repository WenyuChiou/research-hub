from __future__ import annotations

from unittest.mock import patch

from research_hub.search.openalex import OpenAlexBackend


class _Response:
    def __init__(self, payload: dict | None = None, status_code: int = 200) -> None:
        self._payload = payload or {}
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            from requests.exceptions import HTTPError

            raise HTTPError(f"{self.status_code}")


def _work(**overrides):
    work = {
        "id": "https://openalex.org/W123",
        "doi": "https://doi.org/10.1234/foo",
        "title": "LLM agent benchmark",
        "publication_year": 2024,
        "authorships": [{"author": {"display_name": "Jane Doe"}}],
        "primary_location": {"source": {"display_name": "Conf X"}},
        "locations": [],
        "cited_by_count": 17,
        "abstract_inverted_index": {"LLM": [0], "agents": [1], "benchmark": [2]},
        "open_access": {"is_oa": True, "oa_url": "https://example.org/paper.pdf"},
    }
    work.update(overrides)
    return work


@patch("research_hub.search.openalex.time.sleep")
@patch("research_hub.search.openalex.requests.get")
def test_openalex_search_parses_basic_response(mock_get, _mock_sleep):
    mock_get.return_value = _Response({"results": [_work()]})

    result = OpenAlexBackend().search("llm")

    assert len(result) == 1
    assert result[0].title == "LLM agent benchmark"
    assert result[0].doi == "10.1234/foo"
    assert result[0].year == 2024
    assert result[0].authors == ["Jane Doe"]


@patch("research_hub.search.openalex.time.sleep")
@patch("research_hub.search.openalex.requests.get")
def test_openalex_reconstructs_abstract_from_inverted_index(mock_get, _mock_sleep):
    mock_get.return_value = _Response({"results": [_work()]})

    result = OpenAlexBackend().search("llm")

    assert result[0].abstract == "LLM agents benchmark"


@patch("research_hub.search.openalex.time.sleep")
@patch("research_hub.search.openalex.requests.get")
def test_openalex_extracts_arxiv_id_from_location(mock_get, _mock_sleep):
    mock_get.return_value = _Response(
        {
            "results": [
                _work(
                    locations=[
                        {
                            "source": {"display_name": "arXiv"},
                            "landing_page_url": "https://arxiv.org/abs/2411.12345",
                        }
                    ]
                )
            ]
        }
    )

    result = OpenAlexBackend().search("llm")

    assert result[0].arxiv_id == "2411.12345"


@patch("research_hub.search.openalex.time.sleep")
@patch("research_hub.search.openalex.requests.get")
def test_openalex_strips_doi_url_prefix(mock_get, _mock_sleep):
    mock_get.return_value = _Response({"results": [_work(doi="https://doi.org/10.1234/foo")]})

    result = OpenAlexBackend().search("llm")

    assert result[0].doi == "10.1234/foo"


@patch("research_hub.search.openalex.time.sleep")
@patch("research_hub.search.openalex.requests.get")
def test_openalex_year_filter_builds_correct_url(mock_get, _mock_sleep):
    mock_get.return_value = _Response({"results": []})

    OpenAlexBackend().search("llm", year_from=2024, year_to=2025)

    assert mock_get.call_args.kwargs["params"]["filter"] == "publication_year:2024-2025"


@patch("research_hub.search.openalex.time.sleep")
@patch("research_hub.search.openalex.requests.get")
def test_openalex_empty_abstract_index_returns_empty_string(mock_get, _mock_sleep):
    mock_get.return_value = _Response({"results": [_work(abstract_inverted_index=None)]})

    result = OpenAlexBackend().search("llm")

    assert result[0].abstract == ""


@patch("research_hub.search.openalex.time.sleep")
@patch("research_hub.search.openalex.requests.get")
def test_openalex_get_paper_by_doi_returns_none_on_404(mock_get, _mock_sleep):
    mock_get.return_value = _Response(status_code=404)

    assert OpenAlexBackend().get_paper("10.1234/bad") is None


@patch("research_hub.search.openalex.time.sleep")
@patch("research_hub.search.openalex.requests.get")
def test_openalex_populates_doc_type(mock_get, _mock_sleep):
    mock_get.return_value = _Response({"results": [_work(type="journal-article")]})

    result = OpenAlexBackend().search("llm")

    assert result[0].doc_type == "journal-article"
