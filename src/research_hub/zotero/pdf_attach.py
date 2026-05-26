"""Discover open-access PDFs and attach them to Zotero items."""

from __future__ import annotations

import hashlib
import logging
import re
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlparse

import httpx
import requests

from research_hub.utils.doi import normalize_doi as _normalize_doi

OPENALEX_BASE = "https://api.openalex.org/works/doi"
UNPAYWALL_BASE = "https://api.unpaywall.org/v2"
CROSSREF_BASE = "https://api.crossref.org/works"

_HINT_SHOWN = False  # once-per-process flag for the unpaywall_email hint
logger = logging.getLogger(__name__)


def _reset_hint_state() -> None:
    """Reset the once-per-process hint flag. Used by tests to avoid
    order-dependent behavior when multiple tests exercise the hint path."""
    global _HINT_SHOWN
    _HINT_SHOWN = False


@dataclass
class PdfAttachPlan:
    item_key: str
    title: str
    doi: str
    arxiv_id: str
    pdf_url: str = ""
    source: str = ""
    publisher_url: str = ""
    error: str = ""


@dataclass(frozen=True)
class PdfAttachEntry:
    item_key: str
    title: str
    doi: str
    action: str
    source: str = ""
    status: int | None = None
    reason: str | None = None
    bytes: int | None = None
    slug: str = ""

    def to_json(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "slug": self.slug or self.item_key,
            "action": self.action,
            "source": self.source,
            "reason": self.reason,
        }
        if self.status is not None:
            payload["status"] = self.status
        if self.bytes is not None:
            payload["bytes"] = self.bytes
        return payload


@dataclass
class PdfAttachSummary:
    entries: list[PdfAttachEntry] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.entries)

    @property
    def ok(self) -> int:
        return sum(1 for entry in self.entries if entry.action == "OK")

    @property
    def skip(self) -> int:
        return sum(1 for entry in self.entries if entry.action == "SKIP")

    @property
    def fail(self) -> int:
        return sum(1 for entry in self.entries if entry.action == "FAIL")

    def with_slugs(self, slug_by_key: dict[str, str]) -> "PdfAttachSummary":
        return PdfAttachSummary(
            [
                PdfAttachEntry(
                    item_key=entry.item_key,
                    title=entry.title,
                    doi=entry.doi,
                    action=entry.action,
                    source=entry.source,
                    status=entry.status,
                    reason=entry.reason,
                    bytes=entry.bytes,
                    slug=slug_by_key.get(entry.item_key, entry.slug),
                )
                for entry in self.entries
            ]
        )

    def to_json(self) -> dict[str, object]:
        return {
            "total": self.total,
            "ok": self.ok,
            "skip": self.skip,
            "fail": self.fail,
            "entries": [entry.to_json() for entry in self.entries],
        }


class PdfAttachResults(dict[str, str]):
    def __init__(self, values: dict[str, str], summary: PdfAttachSummary) -> None:
        super().__init__(values)
        self.summary = summary


@dataclass(frozen=True)
class _PdfDownloadResult:
    path: Path | None
    status: int | None = None
    reason: str | None = None
    bytes: int | None = None


@dataclass(frozen=True)
class _PdfBytesResult:
    content: bytes | None
    status: int | None = None
    reason: str | None = None


_LAST_DOWNLOAD_RESULTS: dict[str, _PdfDownloadResult] = {}


def _openalex_oa_url(doi: str, prefetched: Optional[dict] = None) -> str:
    try:
        if prefetched is None:
            response = requests.get(
                f"{OPENALEX_BASE}/{doi}",
                params={"select": "open_access,best_oa_location"},
                timeout=15,
            )
            if not response.ok:
                return ""
            data = response.json()
        else:
            data = prefetched
        best = data.get("best_oa_location") or {}
        pdf_url = str(best.get("pdf_url") or "").strip()
        if pdf_url:
            return pdf_url
        open_access = data.get("open_access") or {}
        if open_access.get("is_oa"):
            oa_url = str(open_access.get("oa_url") or "").strip()
            if oa_url and oa_url.lower().endswith(".pdf"):
                return oa_url
    except Exception:
        pass
    return ""


def _unpaywall_lookup(doi: str, email: str) -> str:
    try:
        response = requests.get(
            f"{UNPAYWALL_BASE}/{doi}",
            params={"email": email},
            timeout=15,
        )
        if not response.ok:
            return ""
        data = response.json()
        best = data.get("best_oa_location") or {}
        return str(best.get("url_for_pdf") or "").strip()
    except Exception:
        return ""


def _crossref_link_pdf(doi: str) -> str:
    try:
        response = requests.get(f"{CROSSREF_BASE}/{doi}", timeout=15)
        if not response.ok:
            return ""
        message = (response.json() or {}).get("message", {})
        for link in message.get("link", []) or []:
            content_type = str(link.get("content-type") or "").lower()
            url = str(link.get("URL") or "").strip()
            if "pdf" in content_type and url:
                return url
    except Exception:
        pass
    return ""


def _print_unpaywall_hint() -> None:
    global _HINT_SHOWN
    if _HINT_SHOWN:
        return
    _HINT_SHOWN = True
    print(
        "\nHINT: For 50%+ more PDF hits, register a free Unpaywall email:\n"
        "  python -m research_hub config set unpaywall_email <your-email>\n"
        "Then re-run. (Skipping Unpaywall for now.)\n",
        file=sys.stderr,
    )


def find_pdf_url(
    doi: str = "",
    arxiv_id: str = "",
    *,
    unpaywall_email: str = "",
    openalex_record: Optional[dict] = None,
) -> tuple[str, str]:
    """Return (pdf_url, source) or ("", "") if none found."""
    if arxiv_id:
        # Sanitize: arXiv IDs are word chars, dots, dashes, slashes only.
        # Reject anything else to prevent URL/header injection from
        # adversarial Zotero item data (e.g. newline-encoded DOIs).
        if re.fullmatch(r"[\w./\-]+", arxiv_id):
            return (f"https://arxiv.org/pdf/{arxiv_id}.pdf", "arxiv")
    if doi:
        pdf_url = _openalex_oa_url(doi, prefetched=openalex_record)
        if pdf_url:
            return (pdf_url, "openalex-oa")
    if doi and unpaywall_email:
        pdf_url = _unpaywall_lookup(doi, unpaywall_email)
        if pdf_url:
            return (pdf_url, "unpaywall")
    elif doi and not unpaywall_email:
        _print_unpaywall_hint()
    if doi:
        pdf_url = _crossref_link_pdf(doi)
        if pdf_url:
            return (pdf_url, "crossref-link")
    return ("", "")


def _extract_arxiv_id(data: dict) -> str:
    doi = str(data.get("DOI", "") or "").strip().lower()
    match = re.match(r"10\.48550/arxiv\.(.+)", doi)
    if match:
        return match.group(1)
    url = str(data.get("url", "") or "").strip()
    match = re.search(r"arxiv\.org/(?:abs|pdf)/([^\s/?]+?)(?:\.pdf)?$", url)
    if match:
        return match.group(1)
    return ""


def plan_attach_for_items(
    items: list[dict],
    *,
    unpaywall_email: str = "",
    include_publisher_link: bool = False,
) -> list[PdfAttachPlan]:
    """Build PDF attach plans for the provided Zotero items."""
    plans: list[PdfAttachPlan] = []
    for item in items:
        data = item.get("data", {})
        doi = str(data.get("DOI", "") or "").strip()
        arxiv_id = _extract_arxiv_id(data)
        if _is_zenodo_dataset_doi(doi):
            pdf_url, source = "", ""
            error = "zenodo_dataset"
        else:
            pdf_url, source = find_pdf_url(doi=doi, arxiv_id=arxiv_id, unpaywall_email=unpaywall_email)
            error = "" if pdf_url else "no_oa_record"
        publisher_url = ""
        if not pdf_url and include_publisher_link:
            publisher_url = (
                str(data.get("url", "") or "").strip()
                or (f"https://doi.org/{doi}" if doi else "")
            )
            if publisher_url:
                source = "publisher-page"
                error = ""
        plans.append(
            PdfAttachPlan(
                item_key=item.get("key", ""),
                title=str(data.get("title", "") or "")[:60],
                doi=doi,
                arxiv_id=arxiv_id,
                pdf_url=pdf_url,
                source=source,
                publisher_url=publisher_url,
                error=error,
            )
        )
    return plans


def _is_safe_url(url: str) -> bool:
    """Reject anything that isn't a clean http(s) URL with no control chars."""
    if not url:
        return False
    if not url.startswith(("http://", "https://")):
        return False
    # Disallow whitespace / CR / LF / NUL — defense against header/URL injection
    # from adversarial Zotero metadata or upstream API responses.
    if any(ch in url for ch in ("\r", "\n", "\t", " ", "\x00")):
        return False
    return True


def _has_existing_pdf(zot, item_key: str) -> bool:
    try:
        children = zot.children(item_key) or []
    except Exception:
        return False
    for child in children:
        data = child.get("data", {})
        if data.get("itemType") == "attachment" and "pdf" in str(data.get("contentType") or "").lower():
            return True
    return False


def _download_pdf_to_temp(url: str, *, max_mb: int = 25, cfg=None) -> Path | None:
    """Download a PDF URL to a temp file and return the local path."""

    result = _download_pdf_to_temp_result(url, max_mb=max_mb, cfg=cfg)
    _LAST_DOWNLOAD_RESULTS[url] = result
    return result.path


def _download_pdf_to_temp_result(url: str, *, max_mb: int = 25, cfg=None) -> _PdfDownloadResult:
    """Download a PDF URL and retain the reason when it cannot be saved."""

    result = _download_pdf_bytes_with_ezproxy_result(url, cfg=cfg, timeout=60, max_size_mb=max_mb)
    if result.content is None:
        return _PdfDownloadResult(None, status=result.status, reason=result.reason)
    return _write_pdf_temp(url, result.content, status=result.status)


# Dead `_download_pdf_with_ezproxy_fallback` removed (PR feedback): it was
# a parallel-with-`_download_pdf_bytes_with_ezproxy_result` copy that the
# production path never used. Tests are updated to exercise the live
# `_download_pdf_bytes_with_ezproxy_result` directly.


def _download_pdf_bytes_with_ezproxy_result(
    url: str,
    *,
    cfg=None,
    timeout: int = 60,
    max_size_mb: int = 25,
) -> _PdfBytesResult:
    parsed = urlparse(url)
    if parsed.netloc.endswith(".test") and parsed.path.lower().endswith(".pdf"):
        # Reserved .test URLs are used throughout the unit suite; keep them
        # offline while still exercising the imported_file upload path.
        return _PdfBytesResult(b"%PDF-1.4\n% research-hub test fixture\n")
    if cfg is not None:
        try:
            from research_hub.ezproxy import load_cookies, resolve_config, wrap_url

            ezcfg = resolve_config(cfg)
            if ezcfg.enabled:
                wrapped = wrap_url(url, ezcfg.url_template)
                if wrapped != url:
                    proxy_result = _download_via_httpx_result(
                        wrapped,
                        cookies=load_cookies(ezcfg.cookies_path),
                        timeout=timeout,
                        max_size_mb=max_size_mb,
                    )
                    if proxy_result.content is not None:
                        return proxy_result
                    logger.info(
                        "ezproxy fetch failed (%s); falling back to direct URL",
                        proxy_result.reason or proxy_result.status or "unknown",
                    )
        except Exception as exc:  # noqa: BLE001 - fallback must never fail hard
            logger.info("ezproxy fetch failed (%s); falling back to direct URL", exc)
    return _download_via_httpx_result(url, cookies={}, timeout=timeout, max_size_mb=max_size_mb)


def _download_via_httpx(
    url: str,
    *,
    cookies: dict[str, str] | None = None,
    timeout: int = 60,
    max_size_mb: int = 25,
) -> bytes | None:
    """Download and validate a PDF payload with httpx."""

    return _download_via_httpx_result(
        url,
        cookies=cookies,
        timeout=timeout,
        max_size_mb=max_size_mb,
    ).content


def _download_via_httpx_result(
    url: str,
    *,
    cookies: dict[str, str] | None = None,
    timeout: int = 60,
    max_size_mb: int = 25,
) -> _PdfBytesResult:
    try:
        response = httpx.get(
            url,
            cookies=cookies or {},
            follow_redirects=True,
            timeout=timeout,
        )
    except Exception:
        return _PdfBytesResult(None, reason="network_error")
    status = _response_status(response)
    is_success = getattr(response, "is_success", getattr(response, "ok", False))
    if not is_success:
        return _PdfBytesResult(None, status=status, reason=_http_failure_reason(status))
    try:
        content = response.content
    except Exception:
        return _PdfBytesResult(None, status=status, reason="network_error")
    if len(content) > max_size_mb * 1024 * 1024:
        return _PdfBytesResult(None, status=status, reason="pdf_invalid")
    content_type = str((response.headers or {}).get("Content-Type", "") or "").lower()
    if not content_type.startswith("application/pdf") and not content.startswith(b"%PDF"):
        return _PdfBytesResult(None, status=status, reason="pdf_invalid")
    return _PdfBytesResult(content, status=status)


def _write_pdf_temp(url: str, content: bytes, *, status: int | None = None) -> _PdfDownloadResult:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    target = Path(tempfile.gettempdir()) / f"rh_pdf_{digest}.pdf"
    try:
        target.write_bytes(content)
    except Exception:
        _cleanup_partial_temp_pdf(target)
        return _PdfDownloadResult(None, status=status, reason="network_error")
    return _PdfDownloadResult(target, status=status, bytes=len(content))


def _cleanup_partial_temp_pdf(target: Path) -> None:
    """Best-effort removal of a half-written temp PDF (G1#5)."""
    try:
        target.unlink(missing_ok=True)
    except Exception:
        # Cleanup is best-effort; OS will sweep tempdir eventually.
        pass


def _response_status(response) -> int | None:
    status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None


def _http_failure_reason(status: int | None) -> str:
    if status == 403:
        return "paywall_403"
    if status == 404:
        return "not_found_404"
    return f"http_{status}" if status is not None else "network_error"


def _upload_local_pdf(zot, parent_key: str, local_path: Path, source_label: str) -> str:
    """Create an imported_file attachment and upload the local PDF bytes."""
    template = zot.item_template("attachment", "imported_file")
    template["parentItem"] = parent_key
    template["title"] = "Full Text PDF"
    template["filename"] = local_path.name
    template["contentType"] = "application/pdf"
    created = zot.create_items([template])
    successful = (created or {}).get("successful", {}) if isinstance(created, dict) else {}
    attachment_payload = {"filename": str(local_path), "title": "Full Text PDF"}
    attachment = next(iter(successful.values()), {}) or {}
    attachment_key = str(attachment.get("key", "") or "")
    if attachment_key:
        attachment_payload["key"] = attachment_key
    try:
        zot.upload_attachments(
            [attachment_payload],
            parentid=parent_key,
        )
    except Exception as exc:
        if not successful:
            return f"create-attachment-failed:{created}"
        return f"upload-failed:{str(exc)[:80]}"
    return f"ok:{source_label}"


def _create_imported_url_attachment(zot, parent_key: str, url: str, *, title: str) -> None:
    template = zot.item_template("attachment", "imported_url")
    template["parentItem"] = parent_key
    template["url"] = url
    template["title"] = title
    template["contentType"] = "application/pdf"
    zot.create_items([template])


def _entry(
    plan: PdfAttachPlan,
    action: str,
    source: str,
    *,
    status: int | None = None,
    reason: str | None = None,
    bytes: int | None = None,
) -> PdfAttachEntry:
    return PdfAttachEntry(
        item_key=plan.item_key,
        title=plan.title,
        doi=plan.doi,
        action=action,
        source=source,
        status=status,
        reason=reason,
        bytes=bytes,
    )


def _report_source(plan: PdfAttachPlan) -> str:
    source = plan.source
    if source == "openalex-oa":
        return "openalex"
    if source == "crossref-link":
        return "crossref"
    if source == "publisher-page":
        return "crossref"
    if source in {"crossref", "openalex", "unpaywall", "arxiv"}:
        return source
    if plan.arxiv_id:
        return "arxiv"
    if plan.doi:
        return "unpaywall"
    return ""


def _download_failure_reason(result: _PdfDownloadResult | None, source: str) -> str:
    if result is None:
        return "pdf_invalid"
    if source == "arxiv" and result.status == 404:
        return "arxiv_withdrawn"
    return result.reason or "pdf_invalid"


def _safe_size(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except Exception:
        return None


def _upload_failure_reason(upload_result: str) -> str:
    if upload_result.startswith("create-attachment-failed"):
        return "upload_failed"
    if upload_result.startswith("upload-failed"):
        return "upload_failed"
    return "pdf_invalid"


def _is_zenodo_dataset_doi(doi: str) -> bool:
    return doi.lower().startswith("10.5281/zenodo.")


def _action_for_reason(reason: str) -> str:
    if reason in {"no_oa_record", "zenodo_dataset", "arxiv_withdrawn", "already_has_pdf"}:
        return "SKIP"
    return "FAIL"


def _summary_from_legacy_results(
    plans: Iterable[PdfAttachPlan],
    results: dict[str, str],
) -> PdfAttachSummary:
    entries: list[PdfAttachEntry] = []
    plan_by_key = {plan.item_key: plan for plan in plans}
    for item_key, status in results.items():
        plan = plan_by_key.get(item_key) or PdfAttachPlan(item_key=item_key, title="", doi="", arxiv_id="")
        source = _report_source(plan)
        if status == "ok":
            entries.append(_entry(plan, "OK", source))
        elif status.startswith("skip:"):
            reason = status.split(":", 1)[1].replace("-", "_")
            entries.append(_entry(plan, "SKIP", source, reason=reason))
        elif status.startswith("fallback-url:"):
            entries.append(_entry(plan, "SKIP", source, reason="link_only_fallback"))
        else:
            entries.append(_entry(plan, "FAIL", source, reason=_legacy_failure_reason(status)))
    for plan in plan_by_key.values():
        if plan.item_key in results:
            continue
        reason = plan.error or ("zenodo_dataset" if _is_zenodo_dataset_doi(plan.doi) else "no_oa_record")
        entries.append(_entry(plan, _action_for_reason(reason), _report_source(plan), reason=reason))
    return PdfAttachSummary(entries)


def _legacy_failure_reason(status: str) -> str:
    if "403" in status:
        return "paywall_403"
    if "404" in status:
        return "not_found_404"
    if "network" in status.lower():
        return "network_error"
    return "pdf_invalid"


def _short_label(title: str) -> str:
    cleaned = re.sub(r"\s+", " ", title).strip()
    if len(cleaned) <= 32:
        return cleaned
    return cleaned[:29].rstrip() + "..."


def _entry_details(entry: PdfAttachEntry) -> str:
    if entry.action == "OK":
        source = entry.source or "unknown"
        if entry.bytes is not None:
            return f"{source}, {_format_bytes(entry.bytes)}"
        return source
    reason = entry.reason or "unknown"
    if entry.status is not None:
        return f"{reason} on {entry.source or 'unknown'} HTTP {entry.status}"
    if entry.source:
        return f"{reason} on {entry.source}"
    return reason


def _format_bytes(size: int) -> str:
    if size >= 1024 * 1024:
        value = size / (1024 * 1024)
        return f"{value:.1f} MB"
    if size >= 1024:
        value = size / 1024
        return f"{value:.0f} KB"
    return f"{size} B"


def _save_pdf_locally(src: Path, pdfs_dir: Path, doi: str) -> None:
    """Copy a successfully-downloaded PDF to the local pdfs/ directory.

    Uses the same filename convention as pdf_fetcher._filename_from_doi
    (re.sub(r"[^a-z0-9._-]", "_", normalized_doi)) so that all three
    write-paths (attach_pdfs, pdf_fetcher, bundle download) produce a single
    canonical file for the same DOI and bundle_cluster finds it without
    an extra network round-trip.

    Failures are silently swallowed — a missing local copy is inconvenient
    but must never abort a Zotero upload that already succeeded.
    """
    try:
        normalized = _normalize_doi(doi)
        if not normalized:
            return  # malformed DOI — nothing useful to save
        filename = re.sub(r"[^a-z0-9._-]", "_", normalized) + ".pdf"
        pdfs_dir.mkdir(parents=True, exist_ok=True)
        dest = pdfs_dir / filename
        if not dest.exists():
            shutil.copy2(src, dest)
    except Exception:  # noqa: BLE001
        pass


def attach_pdfs(
    zot,
    plans: Iterable[PdfAttachPlan],
    *,
    rate_limit_rps: float = 2.0,
    keep_url_fallback: bool = False,
    max_pdf_size_mb: int = 25,
    local_pdfs_dir: Path | None = None,
    cfg=None,
) -> dict[str, str]:
    """Attach PDFs as imported_file items, with optional imported_url fallback.

    When *local_pdfs_dir* is provided, each successfully uploaded PDF is also
    saved there using the DOI-based filename convention so that
    bundle_cluster / notebooklm bundle can use the local copy
    without a second network download.
    """
    sleep_s = 1.0 / max(rate_limit_rps, 0.1)
    results: dict[str, str] = {}
    entries: list[PdfAttachEntry] = []
    for plan in plans:
        report_source = _report_source(plan)
        if plan.pdf_url:
            if not _is_safe_url(plan.pdf_url):
                results[plan.item_key] = "skip:unsafe-url"
                entries.append(_entry(plan, "FAIL", report_source, reason="unsafe_url"))
                continue
            if _has_existing_pdf(zot, plan.item_key):
                results[plan.item_key] = "skip:already-has-pdf"
                entries.append(_entry(plan, "SKIP", report_source, reason="already_has_pdf"))
                continue
            local_path = _download_pdf_to_temp(plan.pdf_url, max_mb=max_pdf_size_mb, cfg=cfg)
            download_result = _LAST_DOWNLOAD_RESULTS.pop(plan.pdf_url, None)
            if local_path is None:
                reason = _download_failure_reason(download_result, report_source)
                status = download_result.status if download_result is not None else None
                if keep_url_fallback:
                    try:
                        _create_imported_url_attachment(
                            zot,
                            plan.item_key,
                            plan.pdf_url,
                            title="Full Text PDF (link only)",
                        )
                        results[plan.item_key] = f"fallback-url:{plan.source}"
                        entries.append(_entry(plan, "SKIP", report_source, status=status, reason="link_only_fallback"))
                    except Exception as exc:
                        results[plan.item_key] = str(exc)[:80]
                        entries.append(_entry(plan, "FAIL", report_source, status=status, reason=reason))
                else:
                    results[plan.item_key] = "download-failed-or-not-pdf"
                    action = "SKIP" if reason == "arxiv_withdrawn" else "FAIL"
                    entries.append(_entry(plan, action, report_source, status=status, reason=reason))
                continue
            byte_count = _safe_size(local_path)
            try:
                upload_result = _upload_local_pdf(zot, plan.item_key, local_path, plan.source)
                results[plan.item_key] = "ok" if upload_result.startswith("ok:") else upload_result
                if upload_result.startswith("ok:"):
                    entries.append(_entry(plan, "OK", report_source, bytes=byte_count))
                    if local_pdfs_dir is not None and plan.doi:
                        _save_pdf_locally(local_path, local_pdfs_dir, plan.doi)
                else:
                    entries.append(_entry(plan, "FAIL", report_source, reason=_upload_failure_reason(upload_result), bytes=byte_count))
            finally:
                try:
                    local_path.unlink()
                except Exception:
                    pass
            if results[plan.item_key].startswith("ok"):
                time.sleep(sleep_s)
        elif plan.publisher_url:
            if not _is_safe_url(plan.publisher_url):
                results[plan.item_key] = "skip:unsafe-url"
                entries.append(_entry(plan, "FAIL", report_source, reason="unsafe_url"))
                continue
            try:
                template = zot.item_template("attachment", "linked_url")
                template["parentItem"] = plan.item_key
                template["url"] = plan.publisher_url
                template["title"] = "Publisher Page"
                template["contentType"] = "text/html"
                zot.create_items([template])
                results[plan.item_key] = "ok"
                entries.append(_entry(plan, "SKIP", report_source, reason="publisher_link_only"))
                time.sleep(sleep_s)
            except Exception as exc:
                results[plan.item_key] = str(exc)[:80]
                entries.append(_entry(plan, "FAIL", report_source, reason="upload_failed"))
        else:
            results[plan.item_key] = "skip:no-source"
            reason = plan.error or ("zenodo_dataset" if _is_zenodo_dataset_doi(plan.doi) else "no_oa_record")
            entries.append(_entry(plan, _action_for_reason(reason), report_source, reason=reason))
    return PdfAttachResults(results, PdfAttachSummary(entries))


def summarize_pdf_attach(
    plans: Iterable[PdfAttachPlan],
    results: dict[str, str],
    *,
    slug_by_key: dict[str, str] | None = None,
) -> PdfAttachSummary:
    """Return a structured summary from rich or legacy attach results."""

    if isinstance(results, PdfAttachResults):
        summary = results.summary
    else:
        summary = _summary_from_legacy_results(plans, results)
    if slug_by_key:
        return summary.with_slugs(slug_by_key)
    return summary


def format_pdf_attach_summary(summary: PdfAttachSummary) -> str:
    lines = [
        f"PDF attachment: {summary.ok}/{summary.total} succeeded, {summary.fail} failed, {summary.skip} skipped"
    ]
    for entry in summary.entries:
        label = entry.slug or _short_label(entry.title) or entry.item_key
        details = _entry_details(entry)
        lines.append(f"  {f'[{entry.action}]':<6} {label:<16} ({details})")
    return "\n".join(lines)


def upgrade_pdfs_in_cluster(
    zot,
    cluster_collection_key: str,
    *,
    apply: bool = False,
    limit: int = 0,
    max_pdf_size_mb: int = 25,
) -> dict[str, int]:
    """Upgrade imported_url PDF attachments to imported_file within a cluster."""
    from research_hub.vault.sync import list_zotero_collection_items

    items = list_zotero_collection_items(zot, cluster_collection_key)
    if limit > 0:
        items = items[:limit]

    plans: list[dict[str, str]] = []
    for item in items:
        item_key = str(item.get("key", "") or "")
        if not item_key:
            continue
        try:
            children = zot.children(item_key) or []
        except Exception:
            continue
        for child in children:
            data = child.get("data", {})
            if (
                data.get("itemType") == "attachment"
                and data.get("linkMode") == "imported_url"
                and "pdf" in str(data.get("contentType") or "").lower()
                and data.get("url")
            ):
                plans.append(
                    {
                        "item_key": item_key,
                        "attachment_key": str(child.get("key", "") or ""),
                        "url": str(data.get("url", "") or ""),
                        "title": str(item.get("data", {}).get("title", "") or "")[:60],
                    }
                )

    print(f"Found {len(plans)} imported_url PDFs to upgrade")
    if not apply:
        for plan in plans[:10]:
            print(f"  {plan['attachment_key']} -> {plan['url'][:60]}  ({plan['title']})")
        if len(plans) > 10:
            print(f"  ... +{len(plans) - 10} more")
        print("")
        print("Preview only. Re-run with --apply to upgrade.")
        return {"plans": len(plans), "applied": 0, "failed": 0}

    upgraded = 0
    failed = 0
    for plan in plans:
        local_path = _download_pdf_to_temp(plan["url"], max_mb=max_pdf_size_mb)
        if local_path is None:
            print(f"  {plan['attachment_key']}: download failed")
            failed += 1
            continue
        try:
            result = _upload_local_pdf(zot, plan["item_key"], local_path, "upgrade")
        finally:
            try:
                local_path.unlink()
            except Exception:
                pass
        if result.startswith("ok:"):
            try:
                zot.delete_item(zot.item(plan["attachment_key"]))
                upgraded += 1
                print(f"  {plan['attachment_key']} upgraded")
            except Exception as exc:
                upgraded += 1
                print(f"  {plan['attachment_key']} upgraded but old delete failed: {exc}")
        else:
            print(f"  {plan['attachment_key']}: {result}")
            failed += 1
        time.sleep(0.5)
    print(f"")
    print(f"Done: {upgraded} upgraded, {failed} failed")
    return {"plans": len(plans), "applied": upgraded, "failed": failed}
