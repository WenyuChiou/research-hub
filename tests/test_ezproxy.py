from __future__ import annotations

import json
from types import SimpleNamespace
from urllib.parse import quote

from research_hub.ezproxy import EZproxyConfig, load_cookies, resolve_config, wrap_url
from research_hub.zotero import pdf_attach


def test_wrap_url_substitutes_encoded_url():
    url = "https://ieeexplore.ieee.org/document/9"
    template = "https://prox/login?qurl={encoded_url}"

    assert wrap_url(url, template) == f"https://prox/login?qurl={quote(url, safe='')}"


def test_wrap_url_empty_template_returns_original():
    assert wrap_url("https://example.com/paper", "") == "https://example.com/paper"


def test_wrap_url_missing_placeholder_returns_original():
    assert wrap_url("https://example.com/paper", "https://prox/login") == "https://example.com/paper"


def test_load_cookies_from_storage_state_json(tmp_path):
    cookies_path = tmp_path / "state.json"
    cookies_path.write_text(
        json.dumps(
            {
                "cookies": [
                    {"name": "ezproxy", "value": "abc", "domain": ".example.edu", "path": "/"},
                    {"name": "session", "value": "xyz", "domain": ".example.edu", "path": "/"},
                ]
            }
        ),
        encoding="utf-8",
    )

    assert load_cookies(cookies_path) == {"ezproxy": "abc", "session": "xyz"}


def test_load_cookies_missing_file_returns_empty(tmp_path):
    assert load_cookies(tmp_path / "missing.json") == {}


def test_load_cookies_bad_json_returns_empty(tmp_path):
    cookies_path = tmp_path / "bad.json"
    cookies_path.write_text("{not json", encoding="utf-8")

    assert load_cookies(cookies_path) == {}


def test_resolve_config_uses_defaults_when_fields_missing(tmp_path):
    cfg = SimpleNamespace(research_hub_dir=tmp_path / ".research_hub")

    ezcfg = resolve_config(cfg)

    assert ezcfg.url_template == ""
    assert ezcfg.cookies_path == tmp_path / ".research_hub" / "ezproxy_cookies.json"


def test_enabled_requires_template_and_file(tmp_path):
    cookies_path = tmp_path / "ezproxy_cookies.json"

    assert not EZproxyConfig("", cookies_path).enabled
    assert not EZproxyConfig("https://prox/login?qurl={encoded_url}", cookies_path).enabled

    cookies_path.write_text('{"cookies": []}', encoding="utf-8")
    assert EZproxyConfig("https://prox/login?qurl={encoded_url}", cookies_path).enabled


def test_pdf_attach_falls_back_to_original_url_when_proxy_404s(tmp_path, monkeypatch):
    """Exercises the LIVE `_download_pdf_bytes_with_ezproxy_result` path —
    the one actually invoked by `_download_pdf_to_temp_result` in
    production. Earlier draft of this test hit a duplicate
    `_download_pdf_with_ezproxy_fallback` shim that was never wired in;
    that shim was removed and this test now monkeypatches the live
    result-returning helper instead."""
    cookies_path = tmp_path / "ezproxy_cookies.json"
    cookies_path.write_text('{"cookies": [{"name": "ez", "value": "cookie"}]}', encoding="utf-8")
    cfg = SimpleNamespace(
        ezproxy_url_template="https://prox/login?qurl={encoded_url}",
        ezproxy_cookies_path=str(cookies_path),
    )
    calls: list[str] = []

    def fake_download_result(url, *, cookies=None, timeout=60, max_size_mb=25):
        calls.append(url)
        # Live function name is _PdfBytesResult; importing locally to
        # avoid coupling the test to the private dataclass at module top.
        from research_hub.zotero.pdf_attach import _PdfBytesResult
        if url.startswith("https://prox/"):
            return _PdfBytesResult(None, status=404, reason="not_found_404")
        return _PdfBytesResult(b"%PDF-1.4\nfixture\n", status=200)

    monkeypatch.setattr(pdf_attach, "_download_via_httpx_result", fake_download_result)

    result = pdf_attach._download_pdf_bytes_with_ezproxy_result(
        "https://ieeexplore.ieee.org/document/9",
        cfg=cfg,
        timeout=60,
        max_size_mb=25,
    )

    assert result.content == b"%PDF-1.4\nfixture\n"
    assert calls == [
        "https://prox/login?qurl=https%3A%2F%2Fieeexplore.ieee.org%2Fdocument%2F9",
        "https://ieeexplore.ieee.org/document/9",
    ]
