from __future__ import annotations

from unittest.mock import patch

import requests

from research_hub.search.dblp import DblpBackend


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


def _hit(**info_overrides):
    info = {
        "title": "LLM agent benchmark.",
        "authors": {"author": [{"text": "Jane Doe"}, {"text": "John Roe"}]},
        "year": "2024",
        "venue": "Conf X",
        "type": "Conference and Workshop Papers",
        "doi": "10.1234/foo",
        "ee": "https://example.org/paper",
    }
    info.update(info_overrides)
    return {"info": info}


@patch("research_hub.search.dblp.time.sleep")
@patch("research_hub.search.dblp.requests.get")
def test_dblp_search_parses_hit_list(mock_get, _mock_sleep):
    mock_get.return_value = _Response({"result": {"hits": {"hit": [_hit()]}}})

    result = DblpBackend().search("agents")

    assert result[0].title == "LLM agent benchmark"
    assert result[0].authors == ["Jane Doe", "John Roe"]
    assert result[0].year == 2024


@patch("research_hub.search.dblp.time.sleep")
@patch("research_hub.search.dblp.requests.get")
def test_dblp_extracts_authors_from_dict_or_list(mock_get, _mock_sleep):
    mock_get.return_value = _Response(
        {"result": {"hits": {"hit": [_hit(authors={"author": {"text": "Solo Author"}}), _hit()]}}}
    )

    result = DblpBackend().search("agents")

    assert result[0].authors == ["Solo Author"]
    assert result[1].authors == ["Jane Doe", "John Roe"]


@patch("research_hub.search.dblp.time.sleep")
@patch("research_hub.search.dblp.requests.get")
def test_dblp_maps_dblp_type_to_doc_type(mock_get, _mock_sleep):
    mock_get.return_value = _Response({"result": {"hits": {"hit": [_hit(type="Conference and Workshop Papers")]}}})

    result = DblpBackend().search("agents")

    assert result[0].doc_type == "conference-paper"


@patch("research_hub.search.dblp.time.sleep")
@patch("research_hub.search.dblp.requests.get")
def test_dblp_year_filter_applied_client_side(mock_get, _mock_sleep):
    mock_get.return_value = _Response(
        {"result": {"hits": {"hit": [_hit(year="2023"), _hit(year="2024"), _hit(year="2025")]}}}
    )

    result = DblpBackend().search("agents", year_from=2024, year_to=2024)

    assert [item.year for item in result] == [2024]


@patch("research_hub.search.dblp.time.sleep")
@patch("research_hub.search.dblp.requests.get")
def test_dblp_handles_missing_doi_gracefully(mock_get, _mock_sleep):
    mock_get.return_value = _Response({"result": {"hits": {"hit": [_hit(doi="")]}}})

    result = DblpBackend().search("agents")

    assert result[0].doi == ""


@patch("research_hub.search.dblp.time.sleep")
@patch("research_hub.search.dblp.requests.get")
def test_dblp_returns_empty_on_network_error(mock_get, _mock_sleep):
    mock_get.side_effect = requests.exceptions.RequestException("boom")

    assert DblpBackend().search("agents") == []
