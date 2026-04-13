from __future__ import annotations

from research_hub.search import SearchResult, SemanticScholarClient, iter_new_results


def test_search_result_from_s2_json():
    result = SearchResult.from_s2_json(
        {
            "title": "Paper",
            "abstract": "Abstract",
            "year": 2024,
            "authors": [{"name": "Jane Doe"}],
            "externalIds": {"DOI": "10.1/example"},
            "venue": "Venue",
            "citationCount": 7,
            "url": "https://example.com",
            "openAccessPdf": {"url": "https://example.com/paper.pdf"},
        }
    )

    assert result.title == "Paper"
    assert result.doi == "10.1/example"
    assert result.authors == ["Jane Doe"]


def test_semantic_scholar_client_throttle_delays(monkeypatch):
    client = SemanticScholarClient(delay_seconds=3.0)
    timeline = iter([0.0, 1.0, 4.0])
    sleeps = []

    monkeypatch.setattr("research_hub.search.semantic_scholar.time.time", lambda: next(timeline))
    monkeypatch.setattr(
        "research_hub.search.semantic_scholar.time.sleep",
        lambda seconds: sleeps.append(seconds),
    )

    client._throttle()
    client._throttle()

    assert sleeps == [2.0]


def test_search_filters_already_ingested_by_doi():
    class StubClient:
        def search(self, query: str, limit: int = 20):
            return [
                SearchResult(title="Old", doi="10.1/old"),
                SearchResult(title="New", doi="10.1/new"),
            ]

    results = iter_new_results(StubClient(), "query", already_ingested=["10.1/old"], limit=2)

    assert [result.title for result in results] == ["New"]


def test_get_paper_returns_none_on_404(monkeypatch):
    class Response:
        status_code = 404

    monkeypatch.setattr(
        "research_hub.search.semantic_scholar.requests.get",
        lambda *args, **kwargs: Response(),
    )

    assert SemanticScholarClient().get_paper("missing") is None


def test_iter_new_results_legacy_client_signature_still_works():
    class StubClient:
        def search(self, query: str, limit: int = 20):
            assert query == "query"
            assert limit == 2
            return [
                SearchResult(title="Old", doi="10.1/old"),
                SearchResult(title="New", doi="10.1/new"),
            ]

    results = iter_new_results(StubClient(), "query", already_ingested=["10.1/old"], limit=2)

    assert [result.title for result in results] == ["New"]


def test_search_result_dedup_key_uses_normalized_doi():
    result = SearchResult(title="Paper", doi="https://doi.org/10.1234/FOO")
    assert result.dedup_key == "10.1234/foo"


def test_search_result_dedup_key_falls_back_to_arxiv_id():
    result = SearchResult(title="Paper", arxiv_id="2411.12345")
    assert result.dedup_key == "arxiv:2411.12345"


def test_search_result_dedup_key_falls_back_to_title():
    result = SearchResult(title="  Mixed Case Title  ")
    assert result.dedup_key == "title:mixed case title"
