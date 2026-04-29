from __future__ import annotations

from unittest.mock import MagicMock

import requests

from research_hub.discover import _to_papers_input
from research_hub.search.abstract_recovery import RecoveredAbstract, recover_abstract
from research_hub.search.base import SearchResult
from research_hub.search.crossref import _extract_crossref_abstract
from research_hub.search.enrich import enrich_candidates


def test_extract_crossref_abstract_strips_jats_tags():
    work = {"abstract": "<jats:p>Hello <jats:i>world</jats:i></jats:p>"}
    assert _extract_crossref_abstract(work) == "Hello world"


def test_extract_crossref_abstract_returns_empty_when_missing():
    assert _extract_crossref_abstract({}) == ""


def test_recover_abstract_uses_crossref_first(monkeypatch):
    crossref_response = MagicMock()
    crossref_response.status_code = 200
    crossref_response.json.return_value = {
        "message": {"abstract": "<jats:p>Recovered abstract</jats:p>"}
    }

    def fake_get(url, **kwargs):
        assert kwargs["timeout"] == 10
        assert "crossref" in url
        return crossref_response

    monkeypatch.setattr("research_hub.search.abstract_recovery.requests.get", fake_get)

    recovered = recover_abstract("10.1/example")
    assert recovered.source == "crossref"
    assert recovered.text == "Recovered abstract"
    assert recovered.oa_url == ""


def test_recover_abstract_falls_back_to_unpaywall_oa_url_when_crossref_empty(monkeypatch):
    crossref_response = MagicMock()
    crossref_response.status_code = 200
    crossref_response.json.return_value = {"message": {}}

    unpaywall_response = MagicMock()
    unpaywall_response.status_code = 200
    unpaywall_response.json.return_value = {
        "best_oa_location": {"url": "https://example.org/paper.pdf"}
    }

    responses = [crossref_response, unpaywall_response]

    def fake_get(url, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr("research_hub.search.abstract_recovery.requests.get", fake_get)

    recovered = recover_abstract("10.1/example")
    assert recovered.source == "unpaywall"
    assert recovered.text == ""
    assert recovered.oa_url == "https://example.org/paper.pdf"


def test_recover_abstract_returns_empty_when_both_fail(monkeypatch):
    not_found = MagicMock()
    not_found.status_code = 404
    not_found.json.return_value = {}
    responses = [not_found, not_found]

    def fake_get(url, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr("research_hub.search.abstract_recovery.requests.get", fake_get)

    recovered = recover_abstract("10.1/example")
    assert recovered == RecoveredAbstract(text="", source="", oa_url="")


def test_recover_abstract_handles_network_timeout_gracefully(monkeypatch):
    def fake_get(url, **kwargs):
        raise requests.exceptions.Timeout("boom")

    monkeypatch.setattr("research_hub.search.abstract_recovery.requests.get", fake_get)

    recovered = recover_abstract("10.1/example")
    assert recovered == RecoveredAbstract(text="", source="", oa_url="")


def test_enrich_candidates_recovers_missing_abstract_for_doi_results(monkeypatch):
    result = SearchResult(
        title="Test Paper",
        doi="10.1234/x",
        abstract="",
        source="openalex",
    )

    class FakeBackend:
        def get_paper(self, identifier):
            return result

    monkeypatch.setattr("research_hub.search.enrich.OpenAlexBackend", lambda: FakeBackend())
    monkeypatch.setattr("research_hub.search.enrich.recover_abstract", lambda doi: RecoveredAbstract(text="Filled abstract", source="crossref"))

    enriched = enrich_candidates(["10.1234/x"], backends=("openalex",))
    assert enriched[0] is not None
    assert enriched[0].abstract == "Filled abstract"
    assert enriched[0].abstract_source == "crossref"


def test_to_papers_input_emits_year_drift_warning_when_years_differ():
    papers = _to_papers_input(
        [
            {
                "title": "Title",
                "authors": ["Jane Doe"],
                "year": 2026,
                "metadata_year": 2025,
                "doi": "10.1/x",
                "abstract": "Abstract",
                "venue": "Venue",
            }
        ],
        "cluster-a",
    )
    assert papers[0]["year_drift_warning"] == "ingest_year=2026 differs from doi_lookup_year=2025"


def test_to_papers_input_no_year_drift_warning_when_years_match():
    papers = _to_papers_input(
        [
            {
                "title": "Title",
                "authors": ["Jane Doe"],
                "year": 2025,
                "metadata_year": 2025,
                "doi": "10.1/x",
                "abstract": "Abstract",
                "venue": "Venue",
            }
        ],
        "cluster-a",
    )
    assert "year_drift_warning" not in papers[0]


def test_searchresult_dataclass_has_metadata_year_and_abstract_source():
    result = SearchResult(title="Title", metadata_year=2025, abstract_source="openalex")
    assert result.metadata_year == 2025
    assert result.abstract_source == "openalex"
