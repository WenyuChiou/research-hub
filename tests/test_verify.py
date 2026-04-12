from __future__ import annotations

import hashlib
import json
from functools import wraps
from datetime import datetime, timedelta, timezone
from http import HTTPStatus

import requests
try:
    import responses
except ImportError:  # pragma: no cover
    class _Call:
        def __init__(self, method: str, url: str) -> None:
            self.request = type("RequestInfo", (), {"method": method, "url": url})()

    class _ShimResponse:
        def __init__(
            self,
            *,
            status: int,
            url: str,
            headers: dict[str, str] | None = None,
            json_data: dict | None = None,
        ) -> None:
            self.status_code = status
            self.url = url
            self.headers = headers or {}
            self._json_data = json_data or {}
            self.reason = HTTPStatus(status).phrase if status in HTTPStatus._value2member_map_ else ""

        def json(self):
            return self._json_data

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise requests.exceptions.HTTPError(f"{self.status_code} {self.reason}")

    class _ResponsesShim:
        HEAD = "HEAD"
        GET = "GET"

        def __init__(self) -> None:
            self.calls: list[_Call] = []
            self._registry: list[dict] = []
            self._original = None

        def add(self, method, url, *, status=200, headers=None, body=None, json=None):
            self._registry.append(
                {
                    "method": method.upper(),
                    "url": url,
                    "status": status,
                    "headers": headers or {},
                    "body": body,
                    "json": json,
                }
            )

        def assert_call_count(self, url: str, count: int) -> None:
            actual = sum(1 for call in self.calls if call.request.url == url)
            assert actual == count

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
                            if isinstance(entry["body"], Exception):
                                raise entry["body"]
                            response = _ShimResponse(
                                status=entry["status"],
                                url=resolved_url,
                                headers=entry["headers"],
                                json_data=entry["json"],
                            )
                            if (
                                request_kwargs.get("allow_redirects")
                                and 300 <= response.status_code < 400
                                and response.headers.get("Location")
                            ):
                                redirected = fake_request(
                                    session,
                                    method,
                                    response.headers["Location"],
                                    **{k: v for k, v in request_kwargs.items() if k != "params"},
                                )
                                redirected.history = [response]
                                return redirected
                            return response
                    raise AssertionError(f"Unexpected HTTP call: {method} {resolved_url}")

                requests.sessions.Session.request = fake_request
                try:
                    return func(*args, **kwargs)
                finally:
                    requests.sessions.Session.request = self._original
                    self._registry = []

            return wrapper

    responses = _ResponsesShim()

from research_hub.verify import VerifyCache, VerificationResult, verify_arxiv, verify_doi, verify_paper


def _cache_key(kind: str, identifier: str) -> str:
    return hashlib.sha1(f"{kind}:{identifier}".encode("utf-8")).hexdigest()


@responses.activate
def test_verify_doi_200_ok():
    doi = "10.1000/example"
    url = f"https://doi.org/{doi}"
    responses.add(responses.HEAD, url, status=200)

    result = verify_doi(doi)

    assert result.ok is True
    assert result.source == "doi.org"
    assert result.resolved_url == url


@responses.activate
def test_verify_doi_follows_redirect():
    doi = "10.1000/example"
    url = f"https://doi.org/{doi}"
    final_url = "https://publisher.example/paper"
    responses.add(
        responses.HEAD,
        url,
        status=302,
        headers={"Location": final_url},
    )
    responses.add(responses.HEAD, final_url, status=200)

    result = verify_doi(doi)

    assert result.ok is True
    assert result.resolved_url == final_url


@responses.activate
def test_verify_doi_404_not_ok():
    doi = "10.1000/missing"
    url = f"https://doi.org/{doi}"
    responses.add(responses.HEAD, url, status=404)

    result = verify_doi(doi)

    assert result.ok is False
    assert "404" in result.reason


@responses.activate
def test_verify_doi_410_not_ok():
    doi = "10.1000/gone"
    url = f"https://doi.org/{doi}"
    responses.add(responses.HEAD, url, status=410)

    result = verify_doi(doi)

    assert result.ok is False
    assert "410" in result.reason


@responses.activate
def test_verify_doi_403_paywall_counts_as_ok():
    doi = "10.1000/paywalled"
    url = f"https://doi.org/{doi}"
    responses.add(responses.HEAD, url, status=403)

    result = verify_doi(doi)

    assert result.ok is True
    assert result.reason.startswith("403")


@responses.activate
def test_verify_doi_connection_error_retries_then_fails(monkeypatch):
    doi = "10.1000/error"
    url = f"https://doi.org/{doi}"
    monkeypatch.setattr("research_hub.verify.time.sleep", lambda seconds: None)
    responses.add(responses.HEAD, url, body=requests.exceptions.ConnectionError("boom"))
    responses.add(responses.HEAD, url, body=requests.exceptions.ConnectionError("boom"))

    result = verify_doi(doi)

    assert result.ok is False
    assert "connection error" in result.reason
    assert len(responses.calls) == 2


@responses.activate
def test_verify_arxiv_happy_path():
    arxiv_id = "2502.10978"
    url = f"https://arxiv.org/abs/{arxiv_id}"
    responses.add(responses.HEAD, url, status=200)

    result = verify_arxiv(arxiv_id)

    assert result.ok is True
    assert result.source == "arxiv.org"


@responses.activate
def test_verify_arxiv_bad_id_404():
    arxiv_id = "2502.10978"
    url = f"https://arxiv.org/abs/{arxiv_id}"
    responses.add(responses.HEAD, url, status=404)

    result = verify_arxiv(arxiv_id)

    assert result.ok is False


@responses.activate
def test_verify_paper_fuzzy_match_happy_path():
    responses.add(
        responses.GET,
        "https://api.semanticscholar.org/graph/v1/paper/search",
        json={
            "data": [
                {
                    "title": "Flood Risk Perception: A Systematic Review",
                    "year": 2024,
                    "authors": [{"name": "Jane Doe"}],
                    "url": "https://www.semanticscholar.org/paper/abc",
                }
            ]
        },
        status=200,
    )

    result = verify_paper("Flood risk perception - a systematic review", year=2024)

    assert result.ok is True
    assert result.source == "semantic-scholar"
    assert result.title_match >= 80


@responses.activate
def test_verify_paper_year_mismatch_rejects():
    responses.add(
        responses.GET,
        "https://api.semanticscholar.org/graph/v1/paper/search",
        json={
            "data": [
                {
                    "title": "Flood Risk Perception: A Systematic Review",
                    "year": 2021,
                    "authors": [{"name": "Jane Doe"}],
                    "url": "https://www.semanticscholar.org/paper/abc",
                }
            ]
        },
        status=200,
    )

    result = verify_paper("Flood risk perception - a systematic review", year=2024)

    assert result.ok is False
    assert "year mismatch" in result.reason


@responses.activate
def test_verify_paper_author_surname_matches():
    responses.add(
        responses.GET,
        "https://api.semanticscholar.org/graph/v1/paper/search",
        json={
            "data": [
                {
                    "title": "Flood Risk Perception: A Systematic Review",
                    "year": 2024,
                    "authors": [{"name": "W. Chang"}],
                    "url": "https://www.semanticscholar.org/paper/abc",
                }
            ]
        },
        status=200,
    )

    result = verify_paper(
        "Flood risk perception - a systematic review",
        authors=["Wen-Yu Chang"],
        year=2024,
    )

    assert result.ok is True


@responses.activate
def test_verify_cache_hit_skips_http(tmp_path):
    doi = "10.1000/cached"
    url = f"https://doi.org/{doi}"
    cache = VerifyCache(tmp_path / "verify_cache.json")
    cache.put(
        _cache_key("doi", doi),
        VerificationResult(
            ok=True,
            source="doi.org",
            resolved_url=url,
            reason="200 OK",
        ),
    )
    responses.add(responses.HEAD, url, status=200)

    result = verify_doi(doi, cache=cache)

    assert result.ok is True
    responses.assert_call_count(url, 0)


@responses.activate
def test_verify_cache_expired_entry_refetches(tmp_path):
    doi = "10.1000/expired"
    url = f"https://doi.org/{doi}"
    cache_path = tmp_path / "verify_cache.json"
    cache = VerifyCache(cache_path)
    key = _cache_key("doi", doi)
    expired_at = (datetime.now(timezone.utc) - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    cache_path.write_text(
        json.dumps(
            {
                key: {
                    "ok": True,
                    "source": "doi.org",
                    "resolved_url": url,
                    "title_match": 0.0,
                    "reason": "stale",
                    "cached_at": expired_at,
                }
            }
        ),
        encoding="utf-8",
    )
    responses.add(responses.HEAD, url, status=200)

    result = verify_doi(doi, cache=cache)

    assert result.ok is True
    assert len(responses.calls) == 1
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    assert payload[key]["reason"].startswith("200")
