from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from research_hub.zotero.pdf_attach import (
    PdfAttachPlan,
    _download_pdf_to_temp,
    _upload_local_pdf,
    attach_pdfs,
    upgrade_pdfs_in_cluster,
)


class _Resp:
    def __init__(
        self,
        *,
        ok: bool = True,
        headers: dict | None = None,
        content: bytes = b"",
        status_code: int = 200,
    ) -> None:
        self.is_success = ok
        self.headers = headers or {}
        self.content = content
        self.status_code = status_code


def test_download_pdf_to_temp_accepts_pdf_magic_bytes(monkeypatch):
    monkeypatch.setattr(
        "research_hub.zotero.pdf_attach.httpx.get",
        lambda *args, **kwargs: _Resp(
            headers={"Content-Type": "application/octet-stream"},
            content=b"%PDF-1.4\nfixture\n",
        ),
    )

    path = _download_pdf_to_temp("https://files.example.com/paper.pdf")

    assert path is not None
    assert path.exists()
    assert path.read_bytes().startswith(b"%PDF")
    path.unlink()


def test_download_pdf_to_temp_sends_browser_useragent_header(monkeypatch):
    """Regression: PR #108 ported `requests.get` → `httpx.get` for the PDF
    body download. httpx's default `User-Agent: python-httpx/<ver>` is
    blocked by MDPI, Frontiers, Springer-pdfdirect, IEEE, etc. — coverage
    crashed to 0/30 on production E2E. The fix is to send a real Chrome
    User-Agent. This test pins both that headers are passed AND that the
    UA looks like Chrome on Windows."""
    captured: dict = {}

    def fake_get(url, *args, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs.get("headers", {})
        return _Resp(headers={"Content-Type": "application/pdf"}, content=b"%PDF-1.4\nfx\n")

    monkeypatch.setattr("research_hub.zotero.pdf_attach.httpx.get", fake_get)

    path = _download_pdf_to_temp("https://www.mdpi.com/2673-2688/7/1/14/pdf")
    assert path is not None
    path.unlink()

    headers = captured["headers"]
    assert "User-Agent" in headers, "PDF download must send a User-Agent header"
    ua = headers["User-Agent"]
    assert "Mozilla" in ua and "Chrome" in ua, (
        f"User-Agent must masquerade as a real Chrome browser; got {ua!r}. "
        "Default python-httpx/<ver> is blocked by MDPI/Frontiers/Springer/IEEE."
    )
    assert "Accept" in headers and "pdf" in headers["Accept"].lower()


def test_download_pdf_to_temp_rejects_non_pdf_payload(monkeypatch):
    monkeypatch.setattr(
        "research_hub.zotero.pdf_attach.httpx.get",
        lambda *args, **kwargs: _Resp(
            headers={"Content-Type": "text/html"},
            content=b"<html>not a pdf</html>",
        ),
    )

    assert _download_pdf_to_temp("https://files.example.com/paper.pdf") is None


def test_upload_local_pdf_calls_upload_attachments(tmp_path):
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\nfixture\n")
    zot = MagicMock()
    zot.create_items.return_value = {"successful": {"0": {"key": "ATT1"}}}

    result = _upload_local_pdf(zot, "ITEM1", pdf_path, "crossref-link")

    assert result == "ok:crossref-link"
    zot.item_template.assert_called_once_with("attachment", "imported_file")
    payload = zot.upload_attachments.call_args.args[0][0]
    assert payload["filename"] == str(pdf_path)
    assert payload["key"] == "ATT1"


def test_attach_pdfs_uses_imported_file_upload_by_default(tmp_path, monkeypatch):
    pdf_path = tmp_path / "downloaded.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\nfixture\n")
    monkeypatch.setattr("research_hub.zotero.pdf_attach._download_pdf_to_temp", lambda *args, **kwargs: pdf_path)

    zot = MagicMock()
    zot.create_items.return_value = {"successful": {"0": {"key": "ATT1"}}}

    results = attach_pdfs(
        zot,
        [
            PdfAttachPlan(
                item_key="ITEM1",
                title="Paper",
                doi="10.1000/one",
                arxiv_id="",
                pdf_url="https://files.example.com/full.pdf",
                source="openalex-oa",
            )
        ],
        rate_limit_rps=999.0,
    )

    assert results == {"ITEM1": "ok"}
    zot.item_template.assert_called_once_with("attachment", "imported_file")
    assert zot.upload_attachments.called
    assert not pdf_path.exists()


def test_attach_pdfs_falls_back_to_link_only_when_enabled(monkeypatch):
    monkeypatch.setattr("research_hub.zotero.pdf_attach._download_pdf_to_temp", lambda *args, **kwargs: None)
    zot = MagicMock()
    zot.item_template.side_effect = lambda *args: {"itemType": "attachment"}

    results = attach_pdfs(
        zot,
        [
            PdfAttachPlan(
                item_key="ITEM1",
                title="Paper",
                doi="10.1000/one",
                arxiv_id="",
                pdf_url="https://files.example.com/full.pdf",
                source="crossref-link",
            )
        ],
        rate_limit_rps=999.0,
        keep_url_fallback=True,
    )

    assert results == {"ITEM1": "fallback-url:crossref-link"}
    payload = zot.create_items.call_args.args[0][0]
    assert payload["url"] == "https://files.example.com/full.pdf"
    assert payload["title"] == "Full Text PDF (link only)"


def test_upgrade_pdfs_in_cluster_upgrades_and_deletes_legacy_attachment(tmp_path, monkeypatch):
    pdf_path = tmp_path / "legacy.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\nfixture\n")
    monkeypatch.setattr("research_hub.zotero.pdf_attach._download_pdf_to_temp", lambda *args, **kwargs: pdf_path)
    monkeypatch.setattr("research_hub.zotero.pdf_attach.time.sleep", lambda seconds: None)
    monkeypatch.setattr(
        "research_hub.vault.sync.list_zotero_collection_items",
        lambda zot, key: [{"key": "ITEM1", "data": {"title": "Legacy Paper"}}],
    )

    zot = MagicMock()
    zot.children.return_value = [
        {
            "key": "ATTOLD",
            "data": {
                "itemType": "attachment",
                "linkMode": "imported_url",
                "contentType": "application/pdf",
                "url": "https://files.example.com/legacy.pdf",
            },
        }
    ]
    zot.create_items.return_value = {"successful": {"0": {"key": "ATTNEW"}}}
    zot.item.side_effect = lambda key: {"key": key}

    result = upgrade_pdfs_in_cluster(zot, "COLL1", apply=True)

    assert result == {"plans": 1, "applied": 1, "failed": 0}
    assert zot.upload_attachments.called
    zot.delete_item.assert_called_once_with({"key": "ATTOLD"})
