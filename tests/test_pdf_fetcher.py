from __future__ import annotations

import urllib.error
from pathlib import Path
from unittest.mock import patch

from research_hub.notebooklm.pdf_fetcher import fetch_paper_pdf


class FakeResponse:
    def __init__(self, data: bytes, content_type: str = "application/pdf") -> None:
        self._data = data
        self.headers = {"Content-Type": content_type}

    def read(self, _size: int = -1) -> bytes:
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_fetch_paper_pdf_prefers_local_doi_cache(tmp_path):
    pdfs_dir = tmp_path / "pdfs"
    pdfs_dir.mkdir()
    cached = pdfs_dir / "10.1_abc.pdf"
    cached.write_bytes(b"pdf")

    result = fetch_paper_pdf("10.1/abc", "paper", pdfs_dir)

    assert result.ok
    assert result.source == "local-doi"
    assert result.path == cached


def test_fetch_paper_pdf_falls_through_to_local_slug_cache(tmp_path):
    pdfs_dir = tmp_path / "pdfs"
    pdfs_dir.mkdir()
    cached = pdfs_dir / "paper-slug.pdf"
    cached.write_bytes(b"pdf")

    result = fetch_paper_pdf("10.1/missing", "paper-slug", pdfs_dir)

    assert result.ok
    assert result.source == "local-slug"
    assert result.path == cached


def test_fetch_paper_pdf_arxiv_success(tmp_path):
    pdfs_dir = tmp_path / "pdfs"
    with patch("research_hub.notebooklm.pdf_fetcher.time.sleep"), patch(
        "urllib.request.urlopen",
        return_value=FakeResponse(b"%PDF-1.4", "application/pdf"),
    ):
        result = fetch_paper_pdf("10.48550/arxiv.2502.10978", "paper", pdfs_dir)

    assert result.ok
    assert result.source == "arxiv"
    assert result.path == pdfs_dir / "10.48550_arxiv.2502.10978.pdf"


def test_fetch_paper_pdf_arxiv_404_falls_through(tmp_path):
    pdfs_dir = tmp_path / "pdfs"

    def fake_urlopen(req, timeout=0):
        url = req.full_url
        if "arxiv.org/pdf" in url:
            raise urllib.error.HTTPError(url, 404, "not found", hdrs=None, fp=None)
        return FakeResponse(b'{"is_oa": false}', "application/json")

    with patch("research_hub.notebooklm.pdf_fetcher.time.sleep"), patch(
        "urllib.request.urlopen",
        side_effect=fake_urlopen,
    ):
        result = fetch_paper_pdf("10.48550/arxiv.2502.10978", "paper", pdfs_dir)

    assert not result.ok
    assert result.source == "not-found"


def test_fetch_paper_pdf_unpaywall_success(tmp_path):
    pdfs_dir = tmp_path / "pdfs"

    def fake_urlopen(req, timeout=0):
        url = req.full_url
        if "api.unpaywall.org" in url:
            return FakeResponse(
                b'{"is_oa": true, "best_oa_location": {"url_for_pdf": "https://example.com/paper.pdf"}}',
                "application/json",
            )
        return FakeResponse(b"%PDF-1.4", "application/pdf")

    with patch("research_hub.notebooklm.pdf_fetcher.time.sleep"), patch(
        "urllib.request.urlopen",
        side_effect=fake_urlopen,
    ):
        result = fetch_paper_pdf("10.1/abc", "paper", pdfs_dir)

    assert result.ok
    assert result.source == "unpaywall"
    assert result.path == pdfs_dir / "10.1_abc.pdf"


def test_fetch_paper_pdf_unpaywall_not_oa_returns_not_found(tmp_path):
    pdfs_dir = tmp_path / "pdfs"
    with patch("research_hub.notebooklm.pdf_fetcher.time.sleep"), patch(
        "urllib.request.urlopen",
        return_value=FakeResponse(b'{"is_oa": false}', "application/json"),
    ):
        result = fetch_paper_pdf("10.1/abc", "paper", pdfs_dir)

    assert not result.ok
    assert result.source == "not-found"


def test_fetch_paper_pdf_unpaywall_no_pdf_location_returns_not_found(tmp_path):
    pdfs_dir = tmp_path / "pdfs"
    with patch("research_hub.notebooklm.pdf_fetcher.time.sleep"), patch(
        "urllib.request.urlopen",
        return_value=FakeResponse(b'{"is_oa": true, "best_oa_location": {}}', "application/json"),
    ):
        result = fetch_paper_pdf("10.1/abc", "paper", pdfs_dir)

    assert not result.ok
    assert result.source == "not-found"


def test_fetch_paper_pdf_no_sources_returns_not_found(tmp_path):
    pdfs_dir = tmp_path / "pdfs"

    result = fetch_paper_pdf("", "", pdfs_dir)

    assert not result.ok
    assert result.source == "not-found"


def test_fetch_paper_pdf_size_cap_rejects_huge_pdf(tmp_path):
    pdfs_dir = tmp_path / "pdfs"
    huge = b"x" * (51 * 1024 * 1024)
    with patch("urllib.request.urlopen", return_value=FakeResponse(huge, "application/pdf")):
        result = fetch_paper_pdf("10.48550/arxiv.2502.10978", "paper", pdfs_dir)

    assert not result.ok
    assert "PDF too large" in result.error


def test_fetch_paper_pdf_non_pdf_content_type_rejected(tmp_path):
    pdfs_dir = tmp_path / "pdfs"
    with patch("urllib.request.urlopen", return_value=FakeResponse(b"<html></html>", "text/html")):
        result = fetch_paper_pdf("10.48550/arxiv.2502.10978", "paper", pdfs_dir)

    assert not result.ok
    assert "non-PDF" in result.error
