from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from research_hub import source_fetch as sf
from research_hub.source_fetch_extraction import _extract_html, _extract_text


class _Response:
    def __init__(self, content: bytes, content_type: str, url: str) -> None:
        self.content = content
        self.status_code = 200
        self.url = url
        self.headers = {"Content-Type": content_type}

    def iter_content(self, chunk_size: int):
        yield self.content

    def close(self) -> None:
        pass


class _Cookies:
    def clear(self) -> None:
        pass


class _Session:
    def __init__(self, response: _Response) -> None:
        self.response = response
        self.cookies = _Cookies()

    def get(self, url: str, **kwargs):
        return self.response

    def close(self) -> None:
        pass


def test_script_configuration_captcha_key_is_not_visible_restriction():
    html = b"""<html><head><meta name="citation_title" content="Public resource">
    <meta name="citation_abstract" content="Public description remains readable.">
    <script>window.config = {"captchaApiKey": "public-site-key"};</script>
    </head><body><main>Public resource page.</main></body></html>"""

    extracted = _extract_html(html, "https://example.org/resources/public")

    assert extracted.observed_title == "Public resource"
    assert extracted.text == "Public description remains readable."


def test_noscript_challenge_text_remains_visible_to_restriction_detector():
    html = b"""<html><head><meta name="citation_title" content="Public resource">
    <meta name="citation_abstract" content="Public description remains readable.">
    </head><body><noscript>Verify you are human with a CAPTCHA.</noscript></body></html>"""

    with pytest.raises(PermissionError, match="login, paywall, or challenge"):
        _extract_html(html, "https://example.org/resources/public")


@pytest.mark.parametrize(
    ("html", "url"),
    [
        (
            "<html><body>Verify you are human with a CAPTCHA.</body></html>",
            "https://example.org/resource",
        ),
        (
            "<html><body>Purchase this article to continue.</body></html>",
            "https://example.org/resource",
        ),
        (
            "<html><form action='/login'><input type='password'></form></html>",
            "https://example.org/resource",
        ),
        (
            "<html><body>Public title</body></html>",
            "https://example.org/challenge/session",
        ),
    ],
)
def test_visible_or_structural_restrictions_remain_inaccessible(html, url):
    with pytest.raises(PermissionError, match="login, paywall, or challenge"):
        _extract_html(html.encode(), url)


def test_markdown_extraction_preserves_exact_text_title_and_heading_locators():
    data = (
        b"---\r\nlicense: apache-2.0\r\n---\r\n\r\n"
        b"# Public Resource Card\r\nIntroductory text.\r\n\r\n"
        b"## Overview\r\nDeclared resource metadata only.\r\n"
    )

    extracted = _extract_text(data, "https://example.org/raw/main/README.md")

    assert extracted.text == data.decode("utf-8")
    assert extracted.observed_title == "Public Resource Card"
    assert extracted.evidence_level == "full-text"
    assert [row["value"] for row in extracted.locators] == [
        "Public Resource Card",
        "Overview",
    ]
    for locator in extracted.locators:
        assert extracted.text[locator["start"] : locator["end"]].startswith("#")


@pytest.mark.parametrize(
    ("data", "error"),
    [
        (b"", "empty"),
        (b" \r\n\t", "empty"),
        (b"# Title\nvalue\x00binary", "NUL"),
        (b"# Title\nvalue\x01binary", "binary control"),
        (b"# Title\ninvalid: \xff", "valid UTF-8"),
    ],
)
def test_plain_text_rejects_blank_or_binary_content(data, error):
    with pytest.raises(ValueError, match=error):
        _extract_text(data, "https://example.org/resource.txt")


def test_plain_text_credential_prompt_remains_inaccessible():
    with pytest.raises(PermissionError, match="login, paywall, or challenge"):
        _extract_text(
            b"Sign in to continue\nUsername: example\nPassword: example",
            "https://example.org/resource.txt",
        )


def test_plain_text_extractor_rejects_mislabeled_html_login_form():
    data = b'<html><form action="/login"><input type="password"></form></html>'

    with pytest.raises(PermissionError, match="login, paywall, or challenge"):
        _extract_text(data, "https://example.org/raw/main/README.md")


@pytest.mark.parametrize(
    "data",
    [
        b'<form action="/login"><input type="password"></form>',
        (
            b"# Public Resource Card\nOrdinary introductory text.\n"
            b'<form action="/signin"><input type="password"></form>'
        ),
    ],
)
def test_plain_text_extractor_rejects_structural_login_form_fragments(data):
    with pytest.raises(PermissionError, match="login, paywall, or challenge"):
        _extract_text(data, "https://example.org/raw/main/README.md")


def test_mislabeled_html_login_form_fetch_remains_inaccessible(tmp_path, monkeypatch):
    data = b'<html><form action="/login"><input type="password"></form></html>'
    url = "https://example.org/resources/raw/main/README.md"
    response = _Response(data, "text/plain; charset=utf-8", url)
    monkeypatch.setattr(sf, "_resolve_host_addresses", lambda host: ("93.184.216.34",))
    monkeypatch.setattr(sf, "_new_public_session", lambda: _Session(response))

    result = sf.fetch_public_source(url=url, output_dir=tmp_path / "login-form")

    assert result.status == "inaccessible"
    assert result.evidence_level == "metadata"
    assert result.attempts[0].outcome == "inaccessible"
    assert result.attempts[0].error == "response is a login, paywall, or challenge page"


def test_prefixed_login_form_fragment_fetch_remains_inaccessible(tmp_path, monkeypatch):
    data = (
        b"# Public Resource Card\nOrdinary introductory text.\n"
        b'<form action="/login"><input type="password"></form>'
    )
    url = "https://example.org/resources/raw/main/README.md"
    response = _Response(data, "text/markdown; charset=utf-8", url)
    monkeypatch.setattr(sf, "_resolve_host_addresses", lambda host: ("93.184.216.34",))
    monkeypatch.setattr(sf, "_new_public_session", lambda: _Session(response))

    result = sf.fetch_public_source(url=url, output_dir=tmp_path / "login-fragment")

    assert result.status == "inaccessible"
    assert result.attempts[0].outcome == "inaccessible"


def test_text_fetch_replays_and_rejects_falsified_raw(tmp_path, monkeypatch):
    data = b"# Public Resource Card\n\n## Overview\nPublic metadata and usage notes.\n"
    url = "https://example.org/resources/raw/main/README.md"
    response = _Response(data, "text/plain; charset=utf-8", url)
    monkeypatch.setattr(sf, "_resolve_host_addresses", lambda host: ("93.184.216.34",))
    monkeypatch.setattr(sf, "_new_public_session", lambda: _Session(response))
    output = tmp_path / "text-resource"

    result = sf.fetch_public_source(
        url=url,
        title="Public Resource Card",
        output_dir=output,
    )

    assert result.status == "available"
    assert result.identity_status == "consistent"
    assert result.evidence_level == "full-text"
    assert result.raw_sha256 == sha256(data).hexdigest()
    assert Path(result.extracted_text_path).read_bytes() == data
    assert sf.validate_source_fetch(output / "source-fetch-result.json")["valid"]

    Path(result.raw_path).write_bytes(data + b"falsified")
    report = sf.validate_source_fetch(output / "source-fetch-result.json")
    assert report["valid"] is False
    assert any("sha-256 mismatch" in error.lower() for error in report["errors"])
