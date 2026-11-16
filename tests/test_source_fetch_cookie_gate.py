"""Offline gate regression from a captured response shape, without its tokens."""
from hashlib import sha256
import json
from pathlib import Path

import pytest

from research_hub import source_fetch as sf
from research_hub.source_fetch_extraction import _extract_html
from research_hub.source_fetch_saved import import_saved_public_source
from tests.test_source_fetch import FakeResponse, FakeSession


COOKIE_GATE = b"""<!doctype html><html><head><title>example.org</title>
<style>body { visibility: hidden; }</style></head><body>
<div id="cookie-required" hidden><h1>Cookies must be enabled</h1>
<p>Enable cookies for <span>example.org</span> and reload this page to continue.</p>
</div><script>const challengeId = 'synthetic-not-a-token';</script>
</body></html>"""


@pytest.mark.parametrize("status", [200, 203])
def test_cookie_gate_is_inaccessible_and_keeps_raw_receipt(tmp_path, monkeypatch, status):
    response = FakeResponse(COOKIE_GATE, status=status)
    session = FakeSession(iter([response]))
    monkeypatch.setattr(sf, "_resolve_host_addresses", lambda host: ("93.184.216.34",))
    monkeypatch.setattr(sf, "_new_public_session", lambda: session)
    result = sf.fetch_public_source(url="https://example.org/article", output_dir=tmp_path / "fetch")

    assert result.status == "inaccessible"
    assert result.evidence_level == "metadata"
    assert result.identity_status == "unverified"
    assert result.observed_identity == {"doi": "", "title": ""}
    assert result.extracted_text_path is None
    assert len(result.attempts) == 1
    attempt = result.attempts[0]
    assert attempt.http_status == status
    assert attempt.outcome == "inaccessible"
    assert Path(attempt.raw_path).read_bytes() == COOKIE_GATE
    assert attempt.raw_sha256 == sha256(COOKIE_GATE).hexdigest()
    assert response.closed and session.closed
    assert sf.validate_source_fetch(tmp_path / "fetch/source-fetch-result.json")["valid"]


def test_saved_cookie_gate_is_inaccessible_without_network(tmp_path, monkeypatch):
    monkeypatch.setattr("requests.Session", lambda: pytest.fail("unexpected network"))
    (tmp_path / "gate.html").write_bytes(COOKIE_GATE)
    manifest = {"schema_version": "saved-public-source-input/v1",
                "url": "https://example.org/article", "final_url": "https://example.org/article",
                "doi": "", "title": "", "raw_path": "gate.html",
                "raw_sha256": sha256(COOKIE_GATE).hexdigest(), "content_type": "text/html",
                "original_acquired_at": None}
    raw = json.dumps(manifest).encode()
    (tmp_path / "manifest.json").write_bytes(raw)
    result = import_saved_public_source(input_manifest=tmp_path / "manifest.json",
                                       expected_manifest_sha256=sha256(raw).hexdigest(),
                                       output_dir=tmp_path / "saved")
    assert result.status == "inaccessible"
    assert result.extracted_text_path is None
    assert result.attempts[-1].outcome == "inaccessible"
    assert Path(result.attempts[-1].raw_path).read_bytes() == COOKIE_GATE
    assert sf.validate_source_fetch(tmp_path / "saved/source-fetch-result.json")["valid"]


@pytest.mark.parametrize("heading", [b"<h1>Cookies must be enabled</h1>",
                                   b"<h2>COOKIES must be <em>enabled</em>!</h2>",
                                   b"<title>Cookies must be enabled</title>"])
def test_cookie_gate_heading_normalization(heading):
    body = heading + b"<p>Enable cookies for example.org and reload this page to continue.</p>"
    with pytest.raises(PermissionError):
        _extract_html(body, "https://example.org/article")


@pytest.mark.parametrize("instruction", [
    b"Enable cookies for example.org and reload\nthis page to continue.",
    b"Enable\n cookies for example.org and reload this page to continue.",
    b"Enable cookies for example.org and reload&nbsp;this page to continue.",
])
def test_cookie_gate_instruction_whitespace_normalization(instruction):
    body = b"<h1>Cookies must be enabled</h1><p>" + instruction + b"</p>"
    with pytest.raises(PermissionError):
        _extract_html(body, "https://example.org/article")


@pytest.mark.parametrize("extra", [
    b"<p>Cookies must be enabled. Enable cookies for example.org and reload this page to continue.</p>",
    b"<script>const prompt = '<h1>Cookies must be enabled</h1>Enable cookies for example.org and reload this page to continue.';</script>",
    b"<template><h1>Cookies must be enabled</h1><p>Enable cookies for example.org and reload this page to continue.</p></template>",
    b"<h2>Cookie preferences</h2><p>Enable cookies to save your settings.</p>",
    b"<h2>Cookies must be enabled</h2><p>This is a discussion of cookie mechanisms.</p>",
])
def test_cookie_discussion_banner_or_inert_config_is_not_a_gate(extra):
    html = (b'<html><head><meta name="citation_title" content="Browser resource">'
            b'<meta name="citation_abstract" content="A public description of browser behavior.">'
            b'</head><body>' + extra + b'</body></html>')
    extracted = _extract_html(html, "https://example.org/article")
    assert extracted.evidence_level == "abstract"
    assert extracted.text == "A public description of browser behavior."


@pytest.mark.parametrize("status", [200, 203])
def test_success_status_alone_is_not_rejected(tmp_path, monkeypatch, status):
    body = b'<html><head><meta name="citation_title" content="Ordinary metadata"></head></html>'
    response = FakeResponse(body, status=status)
    monkeypatch.setattr(sf, "_resolve_host_addresses", lambda host: ("93.184.216.34",))
    monkeypatch.setattr(sf, "_new_public_session", lambda: FakeSession(iter([response])))
    result = sf.fetch_public_source(url="https://example.org/article", output_dir=tmp_path / "ordinary")
    assert result.status == "available"
    assert result.evidence_level == "metadata"
    assert result.observed_identity["title"] == "Ordinary metadata"


def test_public_full_text_with_cookie_preferences_is_unchanged():
    article = (b'<article><h1>Public study</h1><h2>Introduction</h2><p>'
               + b'Public evidence and context. ' * 30
               + b'</p><h2>Methods</h2><p>' + b'Measurements and sampling. ' * 12
               + b'</p><h2>Results</h2><p>' + b'Reported estimates and uncertainty. ' * 12
               + b'</p></article>')
    banner = b'<aside><h2>Cookie preferences</h2>Enable cookies to remember settings.</aside>'
    plain = _extract_html(article, "https://example.org/article")
    with_banner = _extract_html(article + banner, "https://example.org/article")
    assert plain.evidence_level == with_banner.evidence_level == "full-text"
    assert plain.text == with_banner.text


def test_old_misclassified_receipt_fails_replay_without_rewriting(tmp_path, monkeypatch):
    response = FakeResponse(COOKIE_GATE, status=203)
    monkeypatch.setattr(sf, "_resolve_host_addresses", lambda host: ("93.184.216.34",))
    monkeypatch.setattr(sf, "_new_public_session", lambda: FakeSession(iter([response])))
    # Simulate the old extractor's exact mistake to exercise receipt validation,
    # not a current acquisition or a real network response.
    with monkeypatch.context() as old:
        old.setattr(sf, "_extract_html", lambda *_: sf._Extracted(
            "example.org", "metadata", observed_title="example.org"))
        sf.fetch_public_source(url="https://example.org/article", output_dir=tmp_path / "old")
    receipt = tmp_path / "old/source-fetch-result.json"
    before = receipt.read_bytes()
    report = sf.validate_source_fetch(receipt)
    assert report["valid"] is False
    assert receipt.read_bytes() == before
