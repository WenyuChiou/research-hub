from __future__ import annotations

import logging
from unittest.mock import Mock, patch

from research_hub.search.nasa_ads import NasaAdsBackend


def _response(payload=None, *, status_code=200):
    response = Mock()
    response.status_code = status_code
    response.json.return_value = payload
    return response


@patch("research_hub.search.nasa_ads.requests.get")
def test_nasa_ads_search_returns_empty_when_no_api_key(mock_get, monkeypatch, caplog):
    monkeypatch.delenv("ADS_DEV_KEY", raising=False)
    backend = NasaAdsBackend(delay_seconds=0)
    caplog.set_level(logging.WARNING)

    assert backend.search("galaxy") == []
    assert backend.search("galaxy") == []
    assert mock_get.call_count == 0
    assert caplog.text.count("NASA ADS backend requires ADS_DEV_KEY environment variable") == 1


@patch("research_hub.search.nasa_ads.requests.get")
def test_nasa_ads_search_uses_bearer_auth_header_when_key_present(mock_get, monkeypatch):
    monkeypatch.setenv("ADS_DEV_KEY", "fake-key")
    mock_get.return_value = _response({"response": {"docs": []}})

    NasaAdsBackend(delay_seconds=0).search("black holes")

    assert mock_get.call_args.kwargs["headers"]["Authorization"] == "Bearer fake-key"


@patch("research_hub.search.nasa_ads.requests.get")
def test_nasa_ads_search_extracts_bibcode_title_doi_year(mock_get, monkeypatch):
    monkeypatch.setenv("ADS_DEV_KEY", "fake-key")
    mock_get.return_value = _response(
        {
            "response": {
                "docs": [
                    {
                        "bibcode": "2024ApJ...123..456A",
                        "title": ["An Astrophysics Paper"],
                        "author": ["Jane Doe"],
                        "year": "2024",
                        "doi": ["10.1234/ADS.TEST"],
                        "pub": "Astrophysical Journal",
                        "abstract": "Abstract text",
                        "citation_count": 17,
                        "doctype": "article",
                    }
                ]
            }
        }
    )

    result = NasaAdsBackend(delay_seconds=0).search("astrophysics")[0]

    assert result.title == "An Astrophysics Paper"
    assert result.year == 2024
    assert result.doi == "10.1234/ads.test"
    assert result.url.endswith("/2024ApJ...123..456A/abstract")


@patch("research_hub.search.nasa_ads.requests.get")
def test_nasa_ads_year_filter_uses_year_range_in_query(mock_get, monkeypatch):
    monkeypatch.setenv("ADS_DEV_KEY", "fake-key")
    mock_get.return_value = _response({"response": {"docs": []}})

    NasaAdsBackend(delay_seconds=0).search("planet formation", year_from=2024, year_to=2025)

    assert "year:[2024 TO 2025]" in mock_get.call_args.kwargs["params"]["q"]


@patch("research_hub.search.nasa_ads.requests.get")
def test_nasa_ads_doi_in_response_is_lowercased(mock_get, monkeypatch):
    monkeypatch.setenv("ADS_DEV_KEY", "fake-key")
    mock_get.return_value = _response({"response": {"docs": [{"title": ["t"], "doi": ["10.9999/UPPER.CASE"]}]}})

    result = NasaAdsBackend(delay_seconds=0).search("stars")[0]

    assert result.doi == "10.9999/upper.case"


@patch.object(NasaAdsBackend, "search")
def test_nasa_ads_get_paper_by_doi_uses_doi_query(mock_search, monkeypatch):
    monkeypatch.setenv("ADS_DEV_KEY", "fake-key")
    mock_search.return_value = []

    NasaAdsBackend(delay_seconds=0).get_paper("10.1234/example")

    assert mock_search.call_args.args[0] == 'doi:"10.1234/example"'


@patch.object(NasaAdsBackend, "search")
def test_nasa_ads_get_paper_by_bibcode_uses_bibcode_query(mock_search, monkeypatch):
    monkeypatch.setenv("ADS_DEV_KEY", "fake-key")
    mock_search.return_value = []

    NasaAdsBackend(delay_seconds=0).get_paper("2024ApJ...123..456A")

    assert mock_search.call_args.args[0] == 'bibcode:"2024ApJ...123..456A"'


@patch("research_hub.search.nasa_ads.requests.get")
def test_nasa_ads_returns_empty_on_401_unauthorized(mock_get, monkeypatch):
    monkeypatch.setenv("ADS_DEV_KEY", "fake-key")
    mock_get.return_value = _response(status_code=401)

    assert NasaAdsBackend(delay_seconds=0).search("cosmology") == []
