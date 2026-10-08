from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from research_hub import cli
from research_hub import mcp_server
from research_hub import source_fetch as sf


class FakeResponse:
    def __init__(
        self,
        content: bytes,
        *,
        status: int = 200,
        content_type: str = "text/html; charset=utf-8",
        url: str = "https://example.org/article",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.content = content
        self.status_code = status
        self.url = url
        self.headers = {"Content-Type": content_type, **(headers or {})}
        self.closed = False

    def iter_content(self, chunk_size: int):
        yield self.content

    def close(self) -> None:
        self.closed = True


class FakeCookies:
    def __init__(self) -> None:
        self.clear_count = 0

    def clear(self) -> None:
        self.clear_count += 1


class FakeSession:
    def __init__(self, responses) -> None:
        self.responses = responses
        self.cookies = FakeCookies()
        self.closed = False

    def get(self, url: str, **kwargs):
        if callable(self.responses):
            return self.responses(url, **kwargs)
        return next(self.responses)

    def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def _public_dns(monkeypatch):
    monkeypatch.setattr(sf, "_resolve_host_addresses", lambda host: ("93.184.216.34",))


def _one_response(monkeypatch, response: FakeResponse) -> None:
    monkeypatch.setattr(
        sf, "_new_public_session", lambda: FakeSession(iter([response]))
    )


def _response_callback(monkeypatch, callback) -> None:
    monkeypatch.setattr(sf, "_new_public_session", lambda: FakeSession(callback))


def test_html_full_text_hashes_locators_and_output_containment(tmp_path, monkeypatch):
    html = (
        b"""<html><head><meta name="citation_doi" content="10.1000/example">
    <meta name="citation_title" content="A public study"></head>
    <body><article><h1>A public study</h1><h2>Introduction</h2>
    <p>This is public article text with enough material to be extracted. """
        + (b"Detailed context and evidence for the public article. " * 12)
        + b"""</p><h2>Methods</h2><p>Deterministic methods describe sampling,
    measurement, comparison, validation, and reproducible analysis in enough
    detail to establish a substantive section.</p>
    <h2>Results</h2><p>Reported findings include complete estimates, uncertainty,
    sensitivity checks, and comparisons that form another substantive section.</p>
    </article></body></html>"""
    )
    _one_response(monkeypatch, FakeResponse(html))
    output = tmp_path / "run"

    result = sf.fetch_public_source(
        url="https://example.org/article",
        doi="10.1000/example",
        title="A public study",
        output_dir=output,
    )

    assert result.status == "available"
    assert result.evidence_level == "full-text"
    assert result.identity_status == "verified"
    assert {item["value"] for item in result.locators} >= {"Introduction", "Methods"}
    extracted_text = Path(result.extracted_text_path).read_text(encoding="utf-8")
    for locator in result.locators:
        assert extracted_text[locator["start"] : locator["end"]].strip()
    for value in (result.raw_path, result.extracted_text_path):
        assert value is not None
        Path(value).resolve().relative_to(output.resolve())
    assert Path(result.raw_path).read_bytes() == html
    assert result.raw_sha256 == sha256(html).hexdigest()
    text_bytes = Path(result.extracted_text_path).read_bytes()
    assert result.extracted_text_sha256 == sha256(text_bytes).hexdigest()
    persisted = json.loads(
        (output / "source-fetch-result.json").read_text(encoding="utf-8")
    )
    assert persisted["schema_version"] == "source-fetch-result/v1"
    assert persisted["request"]["operation"] == "source fetch"
    assert persisted["request"]["public_only"] is True
    assert persisted["receipt_sha256"] == sf._receipt_hash(
        persisted["request"],
        result.attempts,
        result.extracted_text_sha256,
        sf._receipt_result_fields(persisted),
    )


def test_pdf_full_text_records_page_locators(tmp_path, monkeypatch):
    pdf = b"%PDF-1.4 synthetic"
    _one_response(
        monkeypatch,
        FakeResponse(
            pdf, content_type="application/pdf", url="https://example.org/paper.pdf"
        ),
    )
    monkeypatch.setattr(
        sf,
        "_extract_pdf",
        lambda data: sf._Extracted(
            "Page one\n\nPage two",
            "full-text",
            "10.1000/example",
            "A public study",
            [
                {"type": "pdf-page", "value": 1, "start": 0, "end": 8},
                {"type": "pdf-page", "value": 2, "start": 10, "end": 18},
            ],
        ),
    )

    result = sf.fetch_public_source(
        url="https://example.org/paper.pdf",
        doi="10.1000/example",
        output_dir=tmp_path / "pdf-run",
    )

    assert result.status == "available"
    assert result.evidence_level == "full-text"
    assert result.locators[-1] == {
        "type": "pdf-page",
        "value": 2,
        "start": 10,
        "end": 18,
    }
    assert result.raw_sha256 == sha256(pdf).hexdigest()


def _selection_pdf(text, doi="", title=""):
    return sf._Extracted(
        text,
        "full-text",
        doi,
        title,
        [{"type": "pdf-page", "value": 1, "start": 0, "end": len(text)}],
    )


def _proposal_pdf(text, doi="", title="American Journal of Public Health"):
    extracted = _selection_pdf(text, doi, title)
    extracted.diagnostics = {
        "observed_title": {
            "value": title,
            "page": 1,
            "provenance": "conservative-first-page-line",
            "proposal": True,
            "rejected_metadata_title": "internal.dvi",
            "rejected_metadata_title_status": "filename-like",
        }
    }
    return extracted


@pytest.mark.parametrize(
    ("expected_doi", "expected_title", "observed_doi", "expected_status"),
    [
        ("", "American Journal of Public Health", "", "unverified"),
        ("", "A distinct expected study", "", "unverified"),
        (
            "10.1000/example",
            "A distinct expected study",
            "10.1000/example",
            "verified",
        ),
    ],
)
def test_source_identity_does_not_promote_first_page_title_proposal(
    expected_doi, expected_title, observed_doi, expected_status
):
    extracted = _proposal_pdf("Substantive body text", observed_doi)

    assert sf._source_identity(expected_doi, expected_title, extracted) == expected_status


@pytest.mark.parametrize("with_matching_doi", [False, True])
def test_fetch_retains_title_proposal_without_using_it_for_identity(
    tmp_path, monkeypatch, with_matching_doi
):
    from research_hub import source_fetch_validation as replay_module

    doi = "10.1000/example" if with_matching_doi else ""
    responses = []
    if doi:
        responses.append(
            FakeResponse(b'{"is_oa": false}', content_type="application/json")
        )
    responses.append(
        FakeResponse(b"%PDF-1.4 proposal", content_type="application/pdf")
    )
    response_iter = iter(responses)
    monkeypatch.setattr(sf, "_new_public_session", lambda: FakeSession(response_iter))
    extracted = _proposal_pdf("Substantive body text", doi)
    monkeypatch.setattr(sf, "_extract_pdf", lambda data: extracted)
    monkeypatch.setattr(replay_module, "_extract_pdf", lambda data: extracted)

    result = sf.fetch_public_source(
        url="https://example.org/paper.pdf",
        doi=doi,
        title="American Journal of Public Health",
        output_dir=tmp_path / ("matching-doi" if doi else "no-doi"),
    )

    assert result.observed_identity["title"] == "American Journal of Public Health"
    assert result.identity_status == ("verified" if doi else "unverified")
    assert sf.validate_source_fetch(
        Path(result.output_dir) / "source-fetch-result.json"
    )["valid"]


def test_receipt_validation_preserves_authoritative_title_mismatch(
    tmp_path, monkeypatch
):
    from research_hub import source_fetch_validation as replay_module

    extracted = _selection_pdf(
        "Substantive body text", title="Authoritative unrelated publication"
    )
    _one_response(
        monkeypatch,
        FakeResponse(b"%PDF-1.4 mismatch", content_type="application/pdf"),
    )
    monkeypatch.setattr(sf, "_extract_pdf", lambda data: extracted)
    monkeypatch.setattr(replay_module, "_extract_pdf", lambda data: extracted)

    result = sf.fetch_public_source(
        url="https://example.org/paper.pdf",
        title="Expected longitudinal cohort study",
        output_dir=tmp_path / "authoritative-mismatch",
    )

    assert result.identity_status == "mismatch"
    assert result.status == "identity-mismatch"
    assert sf.validate_source_fetch(
        Path(result.output_dir) / "source-fetch-result.json"
    )["valid"]


def test_visible_abstract_is_retained_without_page_chrome(tmp_path, monkeypatch):
    html = b"""<html><head><meta name="citation_doi" content="10.1000/example">
    <meta name="citation_title" content="Expected study"></head><body>
    <form><div class="abstract">Not the published abstract in this form.</div></form>
    <div class="card acl-abstract"><h5>Abstract</h5><span>
    Published household consumption findings from the study.<br>Second sentence.
    <script>not evidence</script><img src="icon.png"></span></div>
    <div>Unrelated page footer and references.</div></body></html>"""
    _one_response(monkeypatch, FakeResponse(html))
    output = tmp_path / "visible-abstract"
    result = sf.fetch_public_source(
        url="https://example.org/study", title="Expected study", output_dir=output
    )
    assert result.evidence_level == "abstract"
    extracted = Path(result.extracted_text_path).read_text(encoding="utf-8")
    assert (
        extracted
        == "Published household consumption findings from the study. Second sentence."
    )
    assert result.locators == [
        {"type": "html-section", "value": "Abstract", "start": 0, "end": len(extracted)}
    ]
    assert sf.validate_source_fetch(output / "source-fetch-result.json")["valid"]


@pytest.mark.parametrize(
    "marker", ['class="abstract"', 'id="abstract-content"', 'itemprop="abstract"']
)
def test_explicit_abstract_marker_supported(marker):
    html = f"<title>Expected study</title><section {marker}>Published abstract with enough content to identify the section.</section>"
    extracted = sf._extract_html(html.encode(), "https://example.org/study")
    assert extracted.evidence_level == "abstract"


def test_abstract_word_in_unrelated_identifier_is_not_evidence():
    html = b'<title>Expected study</title><div id="abstractTitleHelp">Instructions for correcting the abstract, not research findings.</div>'
    assert (
        sf._extract_html(html, "https://example.org/study").evidence_level == "metadata"
    )


def test_explicit_visible_abstract_precedes_generic_page_description():
    html = b"""<title>Expected study</title>
    <meta name="description" content="Browse this publisher article page.">
    <div class="abstract">Published household consumption findings from the study.</div>"""
    extracted = sf._extract_html(html, "https://example.org/study")
    assert extracted.evidence_level == "abstract"
    assert extracted.text == "Published household consumption findings from the study."


def _landing_pdf_responder(pdf_extracted):
    landing = b"""<html><head>
    <meta name="citation_doi" content="10.1000/example">
    <meta name="citation_title" content="Expected study">
    <meta name="citation_abstract" content="Verified landing abstract.">
    </head><body><article>Landing page.</article></body></html>"""
    pdf = b"%PDF-1.4 synthetic candidate"

    def respond(url, **_kwargs):
        if "api.unpaywall.org" in url:
            return FakeResponse(
                json.dumps(
                    {
                        "best_oa_location": {
                            "url_for_pdf": "https://example.org/candidate.pdf"
                        }
                    }
                ).encode(),
                content_type="application/json",
                url=url,
            )
        if url == "https://example.org/landing":
            return FakeResponse(landing, url=url)
        if url == "https://example.org/candidate.pdf":
            return FakeResponse(pdf, content_type="application/pdf", url=url)
        if "api.crossref.org" in url:
            return FakeResponse(b"denied", status=403, url=url)
        raise AssertionError(f"unexpected URL: {url}")

    return respond, landing, pdf, pdf_extracted


def test_verified_html_abstract_beats_anonymous_full_text_pdf(tmp_path, monkeypatch):
    responder, landing, pdf, extracted = _landing_pdf_responder(
        _selection_pdf("anonymous full text")
    )
    _response_callback(monkeypatch, responder)
    monkeypatch.setattr(sf, "_extract_pdf", lambda data: extracted)

    result = sf.fetch_public_source(
        doi="10.1000/example",
        url="https://example.org/landing",
        title="Expected study",
        output_dir=tmp_path / "verified-landing",
    )

    assert result.identity_status == "verified"
    assert result.evidence_level == "abstract"
    assert Path(result.raw_path).read_bytes() == landing
    assert any(
        Path(a.raw_path).read_bytes() == pdf for a in result.attempts if a.raw_path
    )


def test_replay_rejects_rehashed_selection_of_anonymous_candidate(
    tmp_path, monkeypatch
):
    from research_hub import source_fetch_validation as replay_module

    responder, _landing, _pdf, extracted = _landing_pdf_responder(
        _selection_pdf("anonymous full text")
    )
    _response_callback(monkeypatch, responder)
    monkeypatch.setattr(sf, "_extract_pdf", lambda data: extracted)
    monkeypatch.setattr(replay_module, "_extract_pdf", lambda data: extracted)
    output = tmp_path / "selection-tamper"
    result = sf.fetch_public_source(
        doi="10.1000/example",
        url="https://example.org/landing",
        title="Expected study",
        output_dir=output,
    )
    anonymous = next(a for a in result.attempts if a.purpose == "unpaywall-oa")
    result_path = output / "source-fetch-result.json"
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload.update(
        source_url=anonymous.url,
        final_url=anonymous.final_url,
        raw_path=anonymous.raw_path,
        raw_sha256=anonymous.raw_sha256,
        source_version="sha256:" + anonymous.raw_sha256,
    )
    attempts = [sf.FetchAttempt(**item) for item in payload["attempts"]]
    payload["receipt_sha256"] = sf._receipt_hash(
        payload["request"],
        attempts,
        payload["extracted_text_sha256"],
        sf._receipt_result_fields(payload),
    )
    result_path.write_text(json.dumps(payload), encoding="utf-8")

    report = sf.validate_source_fetch(result_path)

    assert report["valid"] is False
    assert "recomputed identity status differs from result" in report["errors"]
    assert not any(error.startswith("re-extraction:") for error in report["errors"])


@pytest.mark.parametrize("crossref_path", [False, True])
def test_title_consistent_pdf_does_not_skip_later_doi_verified_pdf(
    tmp_path, monkeypatch, crossref_path
):
    first = b"%PDF-1.4 title-only"
    second = b"%PDF-1.4 verified"

    def respond(url, **_kwargs):
        if "api.unpaywall.org" in url:
            payload = (
                {}
                if crossref_path
                else {
                    "best_oa_location": {
                        "url_for_pdf": "https://example.org/verified.pdf"
                    }
                }
            )
            return FakeResponse(
                json.dumps(payload).encode(), content_type="application/json", url=url
            )
        if "api.crossref.org" in url:
            payload = {
                "message": {
                    "DOI": "10.1000/example",
                    "title": ["Expected study"],
                    "abstract": "Verified abstract retained until a better candidate.",
                    "link": [
                        {
                            "URL": "https://example.org/" + name + ".pdf",
                            "content-type": "application/pdf",
                        }
                        for name in ("title", "verified")
                    ],
                }
            }
            return FakeResponse(
                json.dumps(payload).encode(), content_type="application/json", url=url
            )
        if url.endswith("title.pdf"):
            return FakeResponse(first, content_type="application/pdf", url=url)
        if url.endswith("verified.pdf"):
            return FakeResponse(second, content_type="application/pdf", url=url)
        raise AssertionError(url)

    _response_callback(monkeypatch, respond)
    monkeypatch.setattr(
        sf,
        "_extract_pdf",
        lambda data: _selection_pdf(
            "Full text " + data.decode(),
            doi="10.1000/example" if data == second else "",
            title="Expected study",
        ),
    )
    result = sf.fetch_public_source(
        doi="10.1000/example",
        title="Expected study",
        url="" if crossref_path else "https://example.org/title.pdf",
        output_dir=tmp_path / "selection",
    )
    assert result.identity_status == "verified"
    assert result.evidence_level == "full-text"
    assert Path(result.raw_path).read_bytes() == second
    assert any(a.url.endswith("title.pdf") for a in result.attempts)


def test_identified_full_text_pdf_upgrades_verified_abstract(tmp_path, monkeypatch):
    responder, _landing, pdf, extracted = _landing_pdf_responder(
        _selection_pdf(
            "identified full text", doi="10.1000/example", title="Expected study"
        )
    )
    _response_callback(monkeypatch, responder)
    monkeypatch.setattr(sf, "_extract_pdf", lambda data: extracted)

    result = sf.fetch_public_source(
        doi="10.1000/example",
        url="https://example.org/landing",
        title="Expected study",
        output_dir=tmp_path / "identified-pdf",
    )

    assert result.identity_status == "verified"
    assert result.evidence_level == "full-text"
    assert Path(result.raw_path).read_bytes() == pdf


def test_wrong_paper_pdf_cannot_inherit_landing_identity(tmp_path, monkeypatch):
    responder, landing, _pdf, extracted = _landing_pdf_responder(
        _selection_pdf(
            "wrong paper full text", doi="10.9999/wrong", title="Different study"
        )
    )
    _response_callback(monkeypatch, responder)
    monkeypatch.setattr(sf, "_extract_pdf", lambda data: extracted)

    result = sf.fetch_public_source(
        doi="10.1000/example",
        url="https://example.org/landing",
        title="Expected study",
        output_dir=tmp_path / "wrong-pdf",
    )

    assert result.identity_status == "verified"
    assert result.evidence_level == "abstract"
    assert Path(result.raw_path).read_bytes() == landing


def test_crossref_anonymous_pdf_cannot_replace_verified_metadata(tmp_path, monkeypatch):
    landing = b"""<html><head>
    <meta name="citation_doi" content="10.1000/example">
    <meta name="citation_title" content="Expected study">
    <meta name="citation_abstract" content="Verified landing abstract.">
    </head><body><article>Landing page.</article></body></html>"""
    crossref = json.dumps(
        {
            "message": {
                "DOI": "10.1000/example",
                "title": ["Expected study"],
                "abstract": "Crossref abstract.",
                "link": [
                    {
                        "URL": "https://example.org/crossref.pdf",
                        "content-type": "application/pdf",
                    }
                ],
            }
        }
    ).encode()

    def respond(url, **_kwargs):
        if "api.unpaywall.org" in url:
            return FakeResponse(
                b'{"is_oa": false}', content_type="application/json", url=url
            )
        if url == "https://example.org/landing":
            return FakeResponse(landing, url=url)
        if "api.crossref.org" in url:
            return FakeResponse(crossref, content_type="application/json", url=url)
        if url == "https://example.org/crossref.pdf":
            return FakeResponse(
                b"%PDF-1.4 anonymous", content_type="application/pdf", url=url
            )
        raise AssertionError(f"unexpected URL: {url}")

    _response_callback(monkeypatch, respond)
    monkeypatch.setattr(
        sf, "_extract_pdf", lambda data: _selection_pdf("anonymous Crossref PDF")
    )

    result = sf.fetch_public_source(
        doi="10.1000/example",
        url="https://example.org/landing",
        title="Expected study",
        output_dir=tmp_path / "crossref-anonymous-pdf",
    )

    assert result.identity_status == "verified"
    assert result.evidence_level == "abstract"
    assert Path(result.raw_path).read_bytes() == landing
    assert any(a.purpose == "crossref-public-pdf" for a in result.attempts)


@pytest.mark.parametrize(
    ("observed_doi", "observed_title", "expected_status", "expected_identity"),
    [
        ("", "", "available", "unverified"),
        (
            "10.9999/wrong",
            "Unrelated experimental report",
            "identity-mismatch",
            "mismatch",
        ),
    ],
)
def test_anonymous_and_mismatched_pdf_identity_remain_explicit(
    tmp_path,
    monkeypatch,
    observed_doi,
    observed_title,
    expected_status,
    expected_identity,
):
    _one_response(
        monkeypatch,
        FakeResponse(b"%PDF-1.4 identity", content_type="application/pdf"),
    )
    monkeypatch.setattr(
        sf,
        "_extract_pdf",
        lambda data: _selection_pdf("PDF text", observed_doi, observed_title),
    )

    result = sf.fetch_public_source(
        url="https://example.org/paper.pdf",
        title="Expected study",
        output_dir=tmp_path / expected_identity,
    )

    assert result.status == expected_status
    assert result.identity_status == expected_identity


def test_arxiv_doi_fetches_public_arxiv_pdf(tmp_path, monkeypatch):
    requested: list[str] = []

    def fake_get(url, **kwargs):
        requested.append(url)
        if "api.unpaywall.org" in url:
            return FakeResponse(
                b'{"is_oa": false}', content_type="application/json", url=url
            )
        assert url == "https://arxiv.org/pdf/2502.10978.pdf"
        return FakeResponse(b"%PDF-1.4 arxiv", content_type="application/pdf", url=url)

    _response_callback(monkeypatch, fake_get)
    monkeypatch.setattr(
        sf,
        "_extract_pdf",
        lambda data: sf._Extracted(
            "arXiv full text",
            "full-text",
            "10.48550/arxiv.2502.10978",
            "ArXiv work",
            [{"type": "pdf-page", "value": 1, "start": 0, "end": 15}],
        ),
    )

    result = sf.fetch_public_source(
        doi="10.48550/arxiv.2502.10978",
        output_dir=tmp_path / "arxiv-run",
    )

    assert result.status == "available"
    assert result.identity_status == "verified"
    assert result.source_url == "https://arxiv.org/pdf/2502.10978.pdf"
    assert requested[-1] == result.source_url


@pytest.mark.parametrize(
    ("http_status", "expected_status", "expected_outcome"),
    [(429, "rate-limited", "rate-limited"), (403, "inaccessible", "inaccessible")],
)
def test_http_failures_are_explicit(
    tmp_path, monkeypatch, http_status, expected_status, expected_outcome
):
    _one_response(monkeypatch, FakeResponse(b"denied", status=http_status))

    result = sf.fetch_public_source(
        url="https://example.org/article",
        output_dir=tmp_path / f"run-{http_status}",
    )

    assert result.status == expected_status
    assert result.attempts[0].outcome == expected_outcome
    assert result.attempts[0].http_status == http_status
    assert result.attempts[0].raw_path
    assert result.extracted_text_path is None
    assert result.errors


def test_public_session_ignores_netrc_and_environment_proxy(tmp_path, monkeypatch):
    netrc_path = tmp_path / "netrc"
    netrc_path.write_text(
        "machine example.org login user password secret\n", encoding="utf-8"
    )
    monkeypatch.setenv("NETRC", str(netrc_path))
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:9999")
    captured = {}

    class CaptureAdapter(sf.requests.adapters.BaseAdapter):
        def send(self, request, **kwargs):
            captured["headers"] = dict(request.headers)
            captured["proxies"] = kwargs.get("proxies")
            response = sf.requests.Response()
            response.status_code = 200
            response.url = request.url
            response.headers["Content-Type"] = "text/html"
            response._content = (
                b"<html><head><title>Public record</title></head></html>"
            )
            response._content_consumed = True
            response.request = request
            return response

        def close(self):
            return None

    session = sf._new_public_session()
    session.mount("https://", CaptureAdapter())
    output = tmp_path / "session-run"
    output.mkdir()
    attempts = []
    try:
        data, attempt = sf._request_in_session(
            "https://example.org/article",
            purpose="provided-url",
            output_dir=output.resolve(),
            attempts=attempts,
            timeout=1,
            session=session,
        )
    finally:
        session.close()

    assert data is not None
    assert attempt.http_status == 200
    assert session.trust_env is False
    assert "Authorization" not in captured["headers"]
    assert captured["proxies"] == {}


def test_response_stream_is_bounded_saved_and_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(sf, "_MAX_RESPONSE_BYTES", 8)

    class StreamingResponse(FakeResponse):
        @property
        def content(self):
            raise AssertionError("response.content must never be read")

        @content.setter
        def content(self, value):
            self._stream_data = value

        def iter_content(self, chunk_size: int):
            yield b"12345678"
            yield b"90"
            raise AssertionError("stream must stop after max+1 bytes")

    response = StreamingResponse(b"unused")
    _one_response(monkeypatch, response)

    result = sf.fetch_public_source(
        url="https://example.org/huge",
        output_dir=tmp_path / "bounded-run",
    )

    attempt = result.attempts[0]
    assert result.status == "inaccessible"
    assert attempt.outcome == "response-too-large"
    assert attempt.response_truncated is True
    assert attempt.response_bytes == 9
    assert Path(attempt.raw_path).read_bytes() == b"123456789"
    assert response.closed is True


def test_short_single_section_html_teaser_is_not_full_text(tmp_path, monkeypatch):
    html = b"""<html><head><meta name="citation_title" content="Teaser paper">
    <meta name="citation_abstract" content="A public abstract only."></head>
    <body><article><h2>Introduction</h2><p>Read the full article after purchase.</p></article></body></html>"""
    _one_response(monkeypatch, FakeResponse(html))

    result = sf.fetch_public_source(
        url="https://example.org/teaser",
        title="Teaser paper",
        output_dir=tmp_path / "teaser-run",
    )

    assert result.status == "available"
    assert result.evidence_level == "abstract"
    assert (
        Path(result.extracted_text_path).read_text(encoding="utf-8")
        == "A public abstract only."
    )


def test_reference_doi_does_not_verify_html_identity(tmp_path, monkeypatch):
    html = b"""<html><head><meta name="citation_title" content="Expected paper"></head>
    <body><article><h2>References</h2><p>Unrelated DOI 10.9999/reference.</p></article></body></html>"""
    _one_response(monkeypatch, FakeResponse(html))

    result = sf.fetch_public_source(
        url="https://example.org/article",
        doi="10.9999/reference",
        title="Expected paper",
        output_dir=tmp_path / "reference-doi-run",
    )

    assert result.observed_identity["doi"] == ""
    assert result.identity_status == "consistent"


def test_exact_doi_with_contradictory_title_is_mismatch():
    assert (
        sf._identity(
            "10.1000/example",
            "Completely expected title",
            "10.1000/example",
            "Unrelated experimental report",
        )
        == "mismatch"
    )


def test_pdf_abstract_only_is_not_promoted_to_full_text(monkeypatch):
    class FakePdf:
        metadata = {"Title": "Abstract handout", "DOI": "10.1000/example"}
        pages = [
            SimpleNamespace(
                extract_text=lambda: "Abstract\nA short conference abstract."
            )
        ]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setitem(
        sys.modules, "pdfplumber", SimpleNamespace(open=lambda value: FakePdf())
    )

    extracted = sf._extract_pdf(b"%PDF-1.4 synthetic")

    assert extracted.evidence_level == "abstract"
    assert extracted.observed_doi == "10.1000/example"


def test_crossref_abstract_is_abstract_evidence(tmp_path, monkeypatch):
    responses = iter(
        [
            FakeResponse(
                b'{"is_oa": false}',
                content_type="application/json",
                url="https://api.unpaywall.org/v2/10.1000%2Fexample",
            ),
            FakeResponse(
                json.dumps(
                    {
                        "message": {
                            "DOI": "10.1000/example",
                            "title": ["Expected title"],
                            "abstract": "<jats:p>Public abstract text.</jats:p>",
                        }
                    }
                ).encode(),
                content_type="application/json",
                url="https://api.crossref.org/works/10.1000%2Fexample",
            ),
        ]
    )
    monkeypatch.setattr(sf, "_new_public_session", lambda: FakeSession(responses))

    result = sf.fetch_public_source(
        doi="10.1000/example",
        title="Expected title",
        output_dir=tmp_path / "abstract-run",
    )

    assert result.status == "available"
    assert result.evidence_level == "abstract"
    assert result.identity_status == "verified"
    assert (
        Path(result.extracted_text_path).read_text(encoding="utf-8")
        == "Public abstract text."
    )
    assert result.locators == [
        {"type": "metadata-field", "value": "abstract", "start": 0, "end": 21}
    ]


def test_login_page_is_never_full_text(tmp_path, monkeypatch):
    html = b"<html><body><article><h1>Sign in to continue</h1><p>Institutional login</p></article></body></html>"
    _one_response(monkeypatch, FakeResponse(html, url="https://example.org/login"))

    result = sf.fetch_public_source(
        url="https://example.org/article",
        output_dir=tmp_path / "login-run",
    )

    assert result.status == "inaccessible"
    assert result.attempts[0].outcome == "inaccessible"
    assert result.extracted_text_path is None
    assert result.errors


def test_identity_mismatch_is_not_available_success(tmp_path, monkeypatch):
    html = b"""<html><head><meta name="citation_doi" content="10.9999/other">
    <meta name="citation_title" content="A different work"></head>
    <body><article><h2>Introduction</h2><p>Public content for another paper,
    with enough substantive article text to qualify as extracted full text.</p></article></body></html>"""
    _one_response(monkeypatch, FakeResponse(html))

    result = sf.fetch_public_source(
        url="https://example.org/article",
        doi="10.1000/expected",
        title="Expected work",
        output_dir=tmp_path / "mismatch-run",
    )

    assert result.status == "identity-mismatch"
    assert result.identity_status == "mismatch"
    assert result.evidence_level == "metadata"


def test_parse_failure_has_nonempty_failure_and_preserves_raw(tmp_path, monkeypatch):
    raw = b"not scholarly content"
    _one_response(
        monkeypatch, FakeResponse(raw, content_type="application/octet-stream")
    )

    result = sf.fetch_public_source(
        url="https://example.org/blob",
        output_dir=tmp_path / "parse-run",
    )

    assert result.status == "parse-error"
    assert result.attempts[0].outcome == "parse-error"
    assert Path(result.attempts[0].raw_path).read_bytes() == raw
    assert result.errors


def test_existing_output_and_nonpublic_url_are_rejected(tmp_path):
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(FileExistsError):
        sf.fetch_public_source(url="https://example.org/a", output_dir=existing)
    with pytest.raises(ValueError, match="public http"):
        sf.fetch_public_source(
            url="http://127.0.0.1/private", output_dir=tmp_path / "private"
        )


def test_dns_resolution_to_private_address_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(sf, "_resolve_host_addresses", lambda host: ("127.0.0.1",))
    called = False

    def must_not_get(url, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("private DNS target must be rejected before HTTP")

    _response_callback(monkeypatch, must_not_get)

    result = sf.fetch_public_source(
        url="https://public-name.example/article",
        output_dir=tmp_path / "dns-private-run",
    )

    assert called is False
    assert result.status == "inaccessible"
    assert result.attempts[0].outcome == "unsafe-url"


def test_validator_replays_saved_html_and_rejects_rehashed_changed_text(
    tmp_path, monkeypatch
):
    html = b"""<html><head><meta name="citation_doi" content="10.1000/example">
    <meta name="citation_title" content="A public study"></head><body><article>
    <h2>Introduction</h2><p>This public article has enough stable source text
    for deterministic extraction and validation replay.</p></article></body></html>"""
    _one_response(monkeypatch, FakeResponse(html))
    output = tmp_path / "validated-run"
    result = sf.fetch_public_source(
        url="https://example.org/article",
        doi="10.1000/example",
        output_dir=output,
    )
    result_path = output / "source-fetch-result.json"

    report = sf.validate_source_fetch(result_path)
    assert report["valid"] is True
    assert report["errors"] == []

    payload = json.loads(result_path.read_text(encoding="utf-8"))
    changed = (
        Path(result.extracted_text_path).read_text(encoding="utf-8") + " altered"
    ).encode()
    Path(result.extracted_text_path).write_bytes(changed)
    payload["extracted_text_sha256"] = sha256(changed).hexdigest()
    attempts = [sf.FetchAttempt(**item) for item in payload["attempts"]]
    payload["receipt_sha256"] = sf._receipt_hash(
        payload["request"],
        attempts,
        payload["extracted_text_sha256"],
        sf._receipt_result_fields(payload),
    )
    result_path.write_text(json.dumps(payload), encoding="utf-8")

    report = sf.validate_source_fetch(result_path)
    assert report["valid"] is False
    assert "re-extracted text differs" in " ".join(report["errors"])


def test_validator_rejects_artifact_path_escape(tmp_path, monkeypatch):
    html = b"<html><head><title>Public abstract</title></head><body>Metadata only</body></html>"
    _one_response(monkeypatch, FakeResponse(html))
    output = tmp_path / "contained-run"
    sf.fetch_public_source(url="https://example.org/article", output_dir=output)
    result_path = output / "source-fetch-result.json"
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    outside = tmp_path / "outside.html"
    outside.write_bytes(html)
    payload["attempts"][0]["raw_path"] = str(outside)
    payload["attempts"][0]["raw_sha256"] = sha256(html).hexdigest()
    attempts = [sf.FetchAttempt(**item) for item in payload["attempts"]]
    payload["receipt_sha256"] = sf._receipt_hash(
        payload["request"],
        attempts,
        payload["extracted_text_sha256"],
        sf._receipt_result_fields(payload),
    )
    result_path.write_text(json.dumps(payload), encoding="utf-8")

    report = sf.validate_source_fetch(result_path)

    assert report["valid"] is False
    assert "escapes output directory" in " ".join(report["errors"])


def test_source_fetch_cli_is_described_and_dispatches_json(
    tmp_path, monkeypatch, capsys
):
    parser = cli.build_parser()
    from research_hub.describe import build_manifest

    item = next(
        x for x in build_manifest(parser)["subcommands"] if x["name"] == "source fetch"
    )
    assert item["supports_json"] is True
    validate_item = next(
        x
        for x in build_manifest(parser)["subcommands"]
        if x["name"] == "source validate"
    )
    assert validate_item["supports_json"] is True
    fake = SimpleNamespace(
        status="available",
        evidence_level="abstract",
        identity_status="consistent",
        output_dir=str(tmp_path / "cli-run"),
        to_dict=lambda: {"schema_version": sf.SCHEMA_VERSION, "status": "available"},
    )
    monkeypatch.setattr(
        "research_hub.cli_source.fetch_public_source", lambda **kwargs: fake
    )

    rc = cli.main(
        [
            "source",
            "fetch",
            "--url",
            "https://example.org/article",
            "--output-dir",
            str(tmp_path / "cli-run"),
            "--json",
        ]
    )

    assert rc == 0
    assert json.loads(capsys.readouterr().out)["status"] == "available"


def test_source_validate_cli_emits_replay_report(tmp_path, monkeypatch, capsys):
    expected = {
        "schema_version": sf.VALIDATION_SCHEMA_VERSION,
        "valid": True,
        "receipt_sha256": "abc",
        "errors": [],
    }
    monkeypatch.setattr(
        "research_hub.cli_source.validate_source_fetch",
        lambda *args, **kwargs: expected,
    )

    rc = cli.main(
        ["source", "validate", str(tmp_path / "source-fetch-result.json"), "--json"]
    )

    assert rc == 0
    assert json.loads(capsys.readouterr().out) == expected


def test_source_fetch_mcp_delegates_and_reports_unavailable(tmp_path, monkeypatch):
    calls = []

    def fake_fetch(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            to_dict=lambda: {
                "status": "rate-limited",
                "errors": ["HTTP 429"],
            }
        )

    monkeypatch.setattr("research_hub.source_fetch.fetch_public_source", fake_fetch)

    response = mcp_server.source_fetch(
        str(tmp_path / "source"),
        doi="10.1234/example",
        url="https://example.org/article",
        title="Expected title",
        timeout=12.5,
    )

    assert calls == [
        {
            "output_dir": tmp_path / "source",
            "doi": "10.1234/example",
            "url": "https://example.org/article",
            "title": "Expected title",
            "timeout": 12.5,
        }
    ]
    assert response["ok"] is False
    assert response["status"] == "rate-limited"
    assert response["result"]["errors"] == ["HTTP 429"]


def test_source_fetch_mcp_returns_structured_exception(monkeypatch, tmp_path):
    def fail(**_kwargs):
        raise FileExistsError("immutable output exists")

    monkeypatch.setattr("research_hub.source_fetch.fetch_public_source", fail)

    response = mcp_server.source_fetch(str(tmp_path), url="https://example.org")

    assert response == {
        "ok": False,
        "error": "immutable output exists",
        "error_type": "FileExistsError",
    }


def test_source_validate_mcp_delegates_and_reports_invalid(tmp_path, monkeypatch):
    result_path = tmp_path / "source-fetch-result.json"
    output_dir = tmp_path / "source"
    calls = []

    def fake_validate(path, *, output_dir=None):
        calls.append((path, output_dir))
        return {"valid": False, "errors": ["raw SHA-256 mismatch"]}

    monkeypatch.setattr(
        "research_hub.source_fetch.validate_source_fetch", fake_validate
    )

    response = mcp_server.source_validate(str(result_path), str(output_dir))

    assert calls == [(result_path, output_dir)]
    assert response == {
        "ok": False,
        "error": "source validation failed",
        "errors": ["raw SHA-256 mismatch"],
        "report": {"valid": False, "errors": ["raw SHA-256 mismatch"]},
    }


def test_source_validate_mcp_returns_structured_exception(monkeypatch, tmp_path):
    def fail(*_args, **_kwargs):
        raise ValueError("result path is invalid")

    monkeypatch.setattr("research_hub.source_fetch.validate_source_fetch", fail)

    response = mcp_server.source_validate(str(tmp_path / "missing.json"))

    assert response == {
        "ok": False,
        "error": "result path is invalid",
        "error_type": "ValueError",
    }


# Independent-review regressions: each test below falsified the reviewed
# fingerprint before its corresponding fix.
def test_userinfo_and_shared_address_space_are_not_public():
    assert sf._is_public_url("https://user:secret@example.org/article") is False
    assert sf._address_is_public("100.64.0.1") is False


def test_redirect_to_userinfo_is_rejected_before_second_request(tmp_path, monkeypatch):
    calls = []

    def redirect_once(url, **kwargs):
        calls.append(url)
        return FakeResponse(
            b"redirect",
            status=302,
            url=url,
            headers={"Location": "https://user:secret@example.org/private"},
        )

    _response_callback(monkeypatch, redirect_once)

    result = sf.fetch_public_source(
        url="https://example.org/start",
        output_dir=tmp_path / "userinfo-redirect-run",
    )

    assert calls == ["https://example.org/start"]
    assert result.status == "inaccessible"
    assert [attempt.outcome for attempt in result.attempts] == [
        "redirect",
        "unsafe-url",
    ]


def test_non_arxiv_url_number_does_not_create_arxiv_candidate():
    candidates = sf._candidate_urls("", "https://example.org/papers/2025.12345")
    assert candidates == [("provided-url", "https://example.org/papers/2025.12345")]


def test_script_and_empty_headings_do_not_create_full_text():
    html = (
        b'<html><head><meta name="citation_title" content="Teaser"></head>'
        b"<body><article><h2>Introduction</h2><h2>Results</h2><script>"
        + b"x" * 700
        + b"</script></article></body></html>"
    )

    extracted = sf._extract_html(html, "https://example.org/teaser")

    assert extracted.evidence_level == "metadata"
    assert "xxx" not in extracted.text


def test_validator_rejects_rehashed_result_url_provenance_tamper(tmp_path, monkeypatch):
    html = b"""<html><head><meta name="citation_title" content="Public record"></head>
    <body><article><h2>Introduction</h2><p>Metadata page.</p></article></body></html>"""
    _one_response(monkeypatch, FakeResponse(html))
    output = tmp_path / "url-tamper-run"
    sf.fetch_public_source(url="https://example.org/article", output_dir=output)
    result_path = output / "source-fetch-result.json"
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload["source_url"] = "http://localhost/source"
    payload["final_url"] = "http://localhost/final"
    attempts = [sf.FetchAttempt(**item) for item in payload["attempts"]]
    payload["receipt_sha256"] = sf._receipt_hash(
        payload["request"],
        attempts,
        payload["extracted_text_sha256"],
        sf._receipt_result_fields(payload),
    )
    result_path.write_text(json.dumps(payload), encoding="utf-8")

    report = sf.validate_source_fetch(result_path)

    assert report["valid"] is False
    assert "provenance" in " ".join(report["errors"]).lower()


def test_pdf_parser_exception_becomes_persisted_parse_error(tmp_path, monkeypatch):
    PDFSyntaxError = pytest.importorskip("pdfminer.pdfparser").PDFSyntaxError

    response = FakeResponse(b"%PDF-broken", content_type="application/pdf")
    _one_response(monkeypatch, response)

    def fail_pdf(data):
        raise PDFSyntaxError("broken xref")

    monkeypatch.setattr(sf, "_extract_pdf", fail_pdf)

    result = sf.fetch_public_source(
        url="https://example.org/broken.pdf",
        output_dir=tmp_path / "broken-pdf-run",
    )

    assert result.status == "parse-error"
    assert result.attempts[0].outcome == "parse-error"
    assert Path(result.attempts[0].raw_path).read_bytes() == b"%PDF-broken"


def test_crossref_root_list_is_parse_error_shape():
    with pytest.raises(ValueError, match="object"):
        sf._crossref_metadata([])


def test_crossref_root_list_is_saved_as_parse_error(tmp_path, monkeypatch):
    responses = iter(
        [
            FakeResponse(b'{"is_oa": false}', content_type="application/json"),
            FakeResponse(b"[]", content_type="application/json"),
            FakeResponse(b"denied", status=403),
        ]
    )
    monkeypatch.setattr(sf, "_new_public_session", lambda: FakeSession(responses))

    result = sf.fetch_public_source(
        doi="10.1000/example",
        output_dir=tmp_path / "crossref-list-run",
    )

    crossref_attempt = next(
        attempt for attempt in result.attempts if attempt.purpose == "crossref-metadata"
    )
    assert crossref_attempt.outcome == "parse-error"
    assert Path(crossref_attempt.raw_path).read_bytes() == b"[]"


@pytest.mark.parametrize("bad_payload", [[], None])
def test_validator_invalid_root_shapes_return_report(tmp_path, bad_payload):
    result_path = tmp_path / "source-fetch-result.json"
    result_path.write_text(json.dumps(bad_payload), encoding="utf-8")

    report = sf.validate_source_fetch(result_path)

    assert report["valid"] is False
    assert report["errors"]


def test_validator_null_locators_return_invalid_report(tmp_path, monkeypatch):
    html = b'<html><head><meta name="citation_title" content="Record"></head></html>'
    _one_response(monkeypatch, FakeResponse(html))
    output = tmp_path / "null-locators-run"
    sf.fetch_public_source(url="https://example.org/record", output_dir=output)
    result_path = output / "source-fetch-result.json"
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload["locators"] = None
    result_path.write_text(json.dumps(payload), encoding="utf-8")

    report = sf.validate_source_fetch(result_path)

    assert report["valid"] is False
    assert "locators" in " ".join(report["errors"]).lower()
