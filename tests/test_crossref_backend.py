from __future__ import annotations

from unittest.mock import patch

from research_hub.search.crossref import CrossrefBackend


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
        "DOI": "10.1234/Foo",
        "title": ["Paper title"],
        "author": [{"family": "Doe", "given": "Jane"}],
        "issued": {"date-parts": [[2024, 6, 15]]},
        "container-title": ["Journal Name"],
        "type": "journal-article",
        "is-referenced-by-count": 42,
    }
    work.update(overrides)
    return work


@patch("research_hub.search.crossref.time.sleep")
@patch("research_hub.search.crossref.requests.get")
def test_crossref_search_parses_journal_article(mock_get, _mock_sleep):
    mock_get.return_value = _Response({"message": {"items": [_work()]}})

    result = CrossrefBackend().search("agents")

    assert result[0].title == "Paper title"
    assert result[0].authors == ["Jane Doe"]
    assert result[0].year == 2024
    assert result[0].doi == "10.1234/foo"
    assert result[0].doc_type == "journal-article"


@patch("research_hub.search.crossref.time.sleep")
@patch("research_hub.search.crossref.requests.get")
def test_crossref_search_extracts_authors_from_family_given(mock_get, _mock_sleep):
    mock_get.return_value = _Response({"message": {"items": [_work(author=[{"family": "Smith", "given": "Jane"}])]}})

    result = CrossrefBackend().search("agents")

    assert result[0].authors == ["Jane Smith"]


@patch("research_hub.search.crossref.time.sleep")
@patch("research_hub.search.crossref.requests.get")
def test_crossref_search_year_from_issued_date_parts(mock_get, _mock_sleep):
    mock_get.return_value = _Response({"message": {"items": [_work(issued={"date-parts": [[2024, 6, 15]]})]}})

    result = CrossrefBackend().search("agents")

    assert result[0].year == 2024


@patch("research_hub.search.crossref.time.sleep")
@patch("research_hub.search.crossref.requests.get")
def test_crossref_search_filter_year_range_in_url(mock_get, _mock_sleep):
    mock_get.return_value = _Response({"message": {"items": []}})

    CrossrefBackend().search("agents", year_from=2024, year_to=2025)

    filter_value = mock_get.call_args.kwargs["params"]["filter"]
    assert "from-pub-date:2024-01-01" in filter_value
    assert "until-pub-date:2025-12-31" in filter_value


@patch("research_hub.search.crossref.time.sleep")
@patch("research_hub.search.crossref.requests.get")
def test_crossref_search_returns_empty_on_404(mock_get, _mock_sleep):
    mock_get.return_value = _Response(status_code=404)

    assert CrossrefBackend().search("agents") == []


@patch("research_hub.search.crossref.time.sleep")
@patch("research_hub.search.crossref.requests.get")
def test_crossref_get_paper_by_doi_uses_works_endpoint(mock_get, _mock_sleep):
    mock_get.return_value = _Response({"message": _work()})

    CrossrefBackend().get_paper("10.1234/foo")

    assert mock_get.call_args.args[0].endswith("/works/10.1234%2Ffoo")
