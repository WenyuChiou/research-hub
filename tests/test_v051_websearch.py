from __future__ import annotations

import json

import requests


class _FakeResponse:
    def __init__(self, *, json_data=None, text="", status_code=200):
        self._json_data = json_data
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status={self.status_code}")

    def json(self):
        return self._json_data


def test_provider_select_prefers_tavily_when_key_set(monkeypatch):
    from research_hub.search.websearch import _select_provider

    monkeypatch.setenv("TAVILY_API_KEY", "tv")
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_CSE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_CSE_CX", raising=False)

    cfg = _select_provider(None)
    assert cfg.name == "tavily"


def test_provider_select_falls_back_to_brave(monkeypatch):
    from research_hub.search.websearch import _select_provider

    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "br")
    monkeypatch.delenv("GOOGLE_CSE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_CSE_CX", raising=False)

    cfg = _select_provider(None)
    assert cfg.name == "brave"


def test_provider_select_falls_back_to_ddg(monkeypatch):
    from research_hub.search.websearch import _select_provider

    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_CSE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_CSE_CX", raising=False)

    cfg = _select_provider(None)
    assert cfg.name == "ddg"


def test_tavily_parser_extracts_results(monkeypatch):
    from research_hub.search.websearch import _fetch_tavily, _ProviderConfig

    monkeypatch.setattr(
        "research_hub.search.websearch.requests.post",
        lambda *a, **k: _FakeResponse(
            json_data={
                "results": [
                    {
                        "title": "Official Docs",
                        "url": "https://docs.example.com/2024/start",
                        "content": "Install guide",
                        "score": 0.91,
                    }
                ]
            }
        ),
    )

    results = _fetch_tavily(_ProviderConfig(name="tavily", api_key="tv"), "docs", 5)
    assert len(results) == 1
    assert results[0].title == "Official Docs"
    assert results[0].venue == "docs.example.com"
    assert results[0].doc_type == "docs"
    assert results[0].year == 2024


def test_brave_parser_extracts_results(monkeypatch):
    from research_hub.search.websearch import _fetch_brave, _ProviderConfig

    monkeypatch.setattr(
        "research_hub.search.websearch.requests.get",
        lambda *a, **k: _FakeResponse(
            json_data={
                "web": {
                    "results": [
                        {
                            "title": "Breaking News",
                            "url": "https://reuters.com/world/story",
                            "description": "Latest update",
                        }
                    ]
                }
            }
        ),
    )

    results = _fetch_brave(_ProviderConfig(name="brave", api_key="br"), "news", 5)
    assert len(results) == 1
    assert results[0].abstract == "Latest update"
    assert results[0].venue == "reuters.com"
    assert results[0].doc_type == "news"


def test_google_cse_parser_extracts_results(monkeypatch):
    from research_hub.search.websearch import _fetch_google_cse, _ProviderConfig

    monkeypatch.setattr(
        "research_hub.search.websearch.requests.get",
        lambda *a, **k: _FakeResponse(
            json_data={
                "items": [
                    {
                        "title": "Engineering Blog",
                        "link": "https://medium.com/team/post",
                        "snippet": "Writeup",
                    }
                ]
            }
        ),
    )

    results = _fetch_google_cse(
        _ProviderConfig(name="google_cse", api_key="gg", extra={"cx": "cx"}),
        "blog",
        5,
    )
    assert len(results) == 1
    assert results[0].title == "Engineering Blog"
    assert results[0].doc_type == "blog"
    assert results[0].venue == "medium.com"


def test_ddg_parser_extracts_results_from_html(monkeypatch):
    from research_hub.search.websearch import _fetch_ddg, _ProviderConfig

    html = """
    <html><body>
      <a class="result__a" href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fgithub.com%2Forg%2Frepo">Repo README</a>
      <a class="result__snippet">Project docs and README</a>
    </body></html>
    """
    monkeypatch.setattr(
        "research_hub.search.websearch.requests.get",
        lambda *a, **k: _FakeResponse(text=html),
    )

    results = _fetch_ddg(_ProviderConfig(name="ddg"), "github", 5)
    assert len(results) == 1
    assert results[0].url == "https://github.com/org/repo"
    assert results[0].doc_type == "docs"
    assert results[0].venue == "github.com"


def test_websearch_backend_empty_query_returns_empty_list():
    from research_hub.search.websearch import WebSearchBackend

    assert WebSearchBackend().search("   ") == []


def test_websearch_backend_network_failure_returns_empty_list(monkeypatch):
    from research_hub.search.websearch import WebSearchBackend

    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_CSE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_CSE_CX", raising=False)

    def _boom(*args, **kwargs):
        raise requests.RequestException("boom")

    monkeypatch.setattr("research_hub.search.websearch.requests.get", _boom)
    results = WebSearchBackend().search("agents", limit=3)
    assert results == []


def test_websearch_registered_in_backend_registry():
    from research_hub.search.fallback import _BACKEND_REGISTRY
    from research_hub.search.websearch import WebSearchBackend

    assert _BACKEND_REGISTRY["websearch"] is WebSearchBackend


def test_cli_websearch_subcommand_emits_json(monkeypatch, capsys):
    from research_hub import cli
    from research_hub.search.base import SearchResult

    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_CSE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_CSE_CX", raising=False)
    monkeypatch.setattr(
        "research_hub.search.websearch.WebSearchBackend.search",
        lambda self, query, limit=10, **kwargs: [
            SearchResult(
                title="GitHub README",
                url="https://github.com/org/repo",
                abstract="README",
                venue="github.com",
                source="web",
                doc_type="docs",
            )
        ],
    )

    rc = cli.main(["websearch", "agent orchestration", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["provider"] == "ddg"
    assert payload["results"][0]["title"] == "GitHub README"


def test_mcp_web_search_tool_returns_structured(monkeypatch):
    from research_hub import mcp_server as m
    from research_hub.search.base import SearchResult
    from tests._mcp_helpers import _get_mcp_tool

    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_CSE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_CSE_CX", raising=False)
    monkeypatch.setattr(
        "research_hub.search.websearch.WebSearchBackend.search",
        lambda self, query, limit=10, **kwargs: [
            SearchResult(
                title="Release Notes",
                url="https://example.com/2025/04/release",
                abstract="Details",
                venue="example.com",
                source="web",
                doc_type="article",
                year=2025,
            )
        ],
    )

    tool = _get_mcp_tool(m.mcp, "web_search")
    result = tool.fn(query="release notes")
    assert result["ok"] is True
    assert result["provider"] == "ddg"
    assert result["results"][0]["year"] == 2025
