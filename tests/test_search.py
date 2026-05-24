from __future__ import annotations

from types import SimpleNamespace

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
    client = SemanticScholarClient(delay_seconds=3.0, api_key="")
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


def test_semantic_scholar_client_retries_429_then_returns_results(monkeypatch):
    from research_hub.search import semantic_scholar as s2_mod

    calls = []
    sleeps = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        if len(calls) == 1:
            return SimpleNamespace(
                status_code=429,
                headers={"Retry-After": "0.25"},
                json=lambda: {},
            )
        return SimpleNamespace(
            status_code=200,
            headers={},
            json=lambda: {
                "data": [
                    {
                        "title": "LLM Irrigation Scheduling",
                        "year": 2026,
                        "authors": [{"name": "A. Researcher"}],
                        "externalIds": {"DOI": "10.1234/irrigation"},
                    }
                ]
            },
            raise_for_status=lambda: None,
        )

    monkeypatch.setattr(s2_mod.requests, "get", fake_get)
    monkeypatch.setattr(s2_mod.time, "sleep", lambda seconds: sleeps.append(seconds))

    client = s2_mod.SemanticScholarClient(api_key="", delay_seconds=0, max_retries=1)
    results = client.search("LLM irrigation", limit=1)

    assert [result.title for result in results] == ["LLM Irrigation Scheduling"]
    assert sleeps == [0.25]
    assert len(calls) == 2


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
