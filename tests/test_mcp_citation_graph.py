from __future__ import annotations

from http import HTTPStatus
from functools import wraps

import requests
from tests._mcp_helpers import _list_mcp_tool_names

try:
    import responses
except ImportError:  # pragma: no cover
    class _Call:
        def __init__(self, method: str, url: str) -> None:
            self.request = type("RequestInfo", (), {"method": method, "url": url})()

    class _ShimResponse:
        def __init__(self, *, status: int, url: str, json_data: dict | None = None) -> None:
            self.status_code = status
            self.url = url
            self._json_data = json_data or {}
            self.reason = HTTPStatus(status).phrase if status in HTTPStatus._value2member_map_ else ""

        def json(self):
            return self._json_data

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise requests.exceptions.HTTPError(f"{self.status_code} {self.reason}")

    class _ResponsesShim:
        GET = "GET"

        def __init__(self) -> None:
            self._registry: list[dict] = []
            self._original = None

        def add(self, method, url, *, status=200, json=None):
            self._registry.append(
                {
                    "method": method.upper(),
                    "url": url,
                    "status": status,
                    "json": json,
                }
            )

        def activate(self, func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                self._original = requests.sessions.Session.request

                def fake_request(session, method, url, **request_kwargs):
                    prepared = requests.Request(
                        method=method.upper(),
                        url=url,
                        params=request_kwargs.get("params"),
                    ).prepare()
                    resolved_url = prepared.url
                    for index, entry in enumerate(self._registry):
                        if entry["method"] == method.upper() and (
                            entry["url"] == resolved_url or resolved_url.startswith(f"{entry['url']}?")
                        ):
                            self._registry.pop(index)
                            return _ShimResponse(
                                status=entry["status"],
                                url=resolved_url,
                                json_data=entry["json"],
                            )
                    raise AssertionError(f"Unexpected HTTP call: {method} {resolved_url}")

                requests.sessions.Session.request = fake_request
                try:
                    return func(*args, **kwargs)
                finally:
                    requests.sessions.Session.request = self._original
                    self._registry = []

            return wrapper

    responses = _ResponsesShim()

from research_hub.mcp_server import get_citations, get_references, mcp


def _payload(paper_id: str, doi: str) -> dict:
    return {
        "paperId": paper_id,
        "title": f"Paper {paper_id}",
        "year": 2023,
        "authors": [{"name": "Jane Doe"}],
        "externalIds": {"DOI": doi},
        "venue": "Venue",
        "citationCount": 7,
        "url": f"https://example.org/{paper_id}",
        "openAccessPdf": {"url": f"https://example.org/{paper_id}.pdf"},
    }


@responses.activate
def test_get_references_tool_returns_dicts():
    responses.add(
        responses.GET,
        "https://api.semanticscholar.org/graph/v1/paper/DOI:10.1000/example/references",
        json={"data": [{"citedPaper": _payload("ref-1", "10.1000/ref-1")}]},
        status=200,
    )

    result = get_references("10.1000/example", limit=1)

    assert result == [
        {
            "paper_id": "ref-1",
            "title": "Paper ref-1",
            "doi": "10.1000/ref-1",
            "year": 2023,
            "authors": ["Jane Doe"],
            "venue": "Venue",
            "citation_count": 7,
            "url": "https://example.org/ref-1",
            "pdf_url": "https://example.org/ref-1.pdf",
        }
    ]


@responses.activate
def test_get_citations_tool_returns_dicts():
    responses.add(
        responses.GET,
        "https://api.semanticscholar.org/graph/v1/paper/paper-abc/citations",
        json={"data": [{"citingPaper": _payload("cite-1", "10.1000/cite-1")}]},
        status=200,
    )

    result = get_citations("paper-abc", limit=1)

    assert result[0]["paper_id"] == "cite-1"
    assert result[0]["doi"] == "10.1000/cite-1"


def test_citation_graph_tools_are_registered():
    assert "get_references" in _list_mcp_tool_names(mcp)
    assert "get_citations" in _list_mcp_tool_names(mcp)
