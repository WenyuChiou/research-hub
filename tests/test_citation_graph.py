from __future__ import annotations

from http import HTTPStatus
from functools import wraps

import requests

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
            self.calls: list[_Call] = []
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
                self.calls = []
                self._original = requests.sessions.Session.request

                def fake_request(session, method, url, **request_kwargs):
                    prepared = requests.Request(
                        method=method.upper(),
                        url=url,
                        params=request_kwargs.get("params"),
                    ).prepare()
                    resolved_url = prepared.url
                    self.calls.append(_Call(method.upper(), resolved_url))
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

from research_hub.citation_graph import CitationGraphClient, CitationNode


def _paper_payload(**overrides):
    payload = {
        "paperId": "paper-1",
        "title": "Paper Title",
        "year": 2024,
        "authors": [{"name": "Jane Doe"}, {"name": "John Roe"}],
        "externalIds": {"DOI": "10.1000/example"},
        "venue": "TestConf",
        "citationCount": 42,
        "url": "https://example.org/paper",
        "openAccessPdf": {"url": "https://example.org/paper.pdf"},
    }
    payload.update(overrides)
    return payload


def test_normalize_id_bare_doi():
    assert CitationGraphClient()._normalize_id("10.1234/xxx") == "DOI:10.1234/xxx"


def test_normalize_id_arxiv():
    assert CitationGraphClient()._normalize_id("2502.10978") == "ARXIV:2502.10978"


def test_normalize_id_already_prefixed():
    assert CitationGraphClient()._normalize_id("DOI:10.x") == "DOI:10.x"


@responses.activate
def test_get_references_happy_path():
    responses.add(
        responses.GET,
        "https://api.semanticscholar.org/graph/v1/paper/DOI:10.1000/example/references",
        json={"data": [{"citedPaper": _paper_payload(paperId=f"paper-{i}")} for i in range(3)]},
        status=200,
    )

    nodes = CitationGraphClient(delay=0).get_references("10.1000/example", limit=3)

    assert len(nodes) == 3
    assert nodes[0].paper_id == "paper-0"


@responses.activate
def test_get_references_handles_404():
    responses.add(
        responses.GET,
        "https://api.semanticscholar.org/graph/v1/paper/DOI:10.404/missing/references",
        status=404,
        json={},
    )

    assert CitationGraphClient(delay=0).get_references("10.404/missing") == []


@responses.activate
def test_get_references_handles_429():
    responses.add(
        responses.GET,
        "https://api.semanticscholar.org/graph/v1/paper/DOI:10.429/rate/references",
        status=429,
        json={},
    )

    assert CitationGraphClient(delay=0).get_references("10.429/rate") == []


@responses.activate
def test_get_citations_happy_path():
    responses.add(
        responses.GET,
        "https://api.semanticscholar.org/graph/v1/paper/ARXIV:2502.10978/citations",
        json={"data": [{"citingPaper": _paper_payload(paperId=f"paper-{i}")} for i in range(5)]},
        status=200,
    )

    nodes = CitationGraphClient(delay=0).get_citations("2502.10978", limit=5)

    assert len(nodes) == 5
    assert nodes[-1].paper_id == "paper-4"


@responses.activate
def test_get_citations_extracts_doi_from_external_ids():
    responses.add(
        responses.GET,
        "https://api.semanticscholar.org/graph/v1/paper/paper-123/citations",
        json={"data": [{"citingPaper": _paper_payload(externalIds={"DOI": "10.2000/citing"})}]},
        status=200,
    )

    nodes = CitationGraphClient(delay=0).get_citations("paper-123", limit=1)

    assert nodes[0].doi == "10.2000/citing"


@responses.activate
def test_get_citations_extracts_pdf_url():
    responses.add(
        responses.GET,
        "https://api.semanticscholar.org/graph/v1/paper/paper-123/citations",
        json={"data": [{"citingPaper": _paper_payload(openAccessPdf={"url": "https://pdf.example/test.pdf"})}]},
        status=200,
    )

    nodes = CitationGraphClient(delay=0).get_citations("paper-123", limit=1)

    assert nodes[0].pdf_url == "https://pdf.example/test.pdf"


def test_citation_node_from_s2_json_handles_citing_paper_wrapper():
    citing = CitationNode.from_s2_json({"citingPaper": _paper_payload(paperId="citing-1")})
    cited = CitationNode.from_s2_json({"citedPaper": _paper_payload(paperId="cited-1")})

    assert citing.paper_id == "citing-1"
    assert cited.paper_id == "cited-1"
    assert citing.title == cited.title == "Paper Title"
