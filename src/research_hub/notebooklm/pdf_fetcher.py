"""Attempt to acquire a local PDF for a paper."""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from research_hub.utils.doi import extract_arxiv_id, normalize_doi

logger = logging.getLogger(__name__)

FetchSource = Literal["local-doi", "local-slug", "arxiv", "unpaywall", "not-found"]
_UNPAYWALL_EMAIL = "research-hub@example.invalid"
_USER_AGENT = "research-hub/0.12.0 (https://github.com/WenyuChiou/research-hub)"
_DEFAULT_TIMEOUT = 15.0
_MAX_PDF_SIZE_MB = 50


@dataclass
class FetchResult:
    source: FetchSource
    path: Path | None = None
    size_bytes: int = 0
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.source != "not-found" and self.path is not None and self.path.exists()


def fetch_paper_pdf(
    doi: str,
    slug: str,
    pdfs_dir: Path,
    *,
    timeout: float = _DEFAULT_TIMEOUT,
) -> FetchResult:
    """Try the full fallback chain. Returns FetchResult."""
    pdfs_dir.mkdir(parents=True, exist_ok=True)
    normalized = normalize_doi(doi) if doi else ""
    target = pdfs_dir / f"{_filename_from_doi(normalized)}.pdf" if normalized else None
    last_error = ""

    if target and target.exists():
        return FetchResult(source="local-doi", path=target, size_bytes=target.stat().st_size)

    if slug:
        slug_path = pdfs_dir / f"{slug}.pdf"
        if slug_path.exists():
            return FetchResult(source="local-slug", path=slug_path, size_bytes=slug_path.stat().st_size)

    arxiv_id = extract_arxiv_id(doi) if doi else ""
    if arxiv_id:
        result = _download(
            f"https://arxiv.org/pdf/{arxiv_id}.pdf",
            target or pdfs_dir / f"arxiv_{arxiv_id}.pdf",
            timeout,
            source="arxiv",
        )
        if result.ok:
            return result
        last_error = result.error or last_error

    if normalized:
        oa_url = _query_unpaywall(normalized, timeout)
        if oa_url:
            result = _download(
                oa_url,
                target or pdfs_dir / f"{_filename_from_doi(normalized)}.pdf",
                timeout,
                source="unpaywall",
            )
            if result.ok:
                return result
            last_error = result.error or last_error

    return FetchResult(
        source="not-found",
        error=last_error or "no local cache, no arxiv, no unpaywall OA",
    )


def _filename_from_doi(normalized_doi: str) -> str:
    return re.sub(r"[^a-z0-9._-]", "_", normalized_doi)


def _download(url: str, dest: Path, timeout: float, *, source: FetchSource) -> FetchResult:
    """HTTP GET with size cap + content-type sanity check."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "").lower()
            if content_type and "pdf" not in content_type:
                return FetchResult(source="not-found", error=f"non-PDF content-type: {content_type}")
            if not content_type and not url.lower().endswith(".pdf"):
                return FetchResult(source="not-found", error=f"non-PDF content-type: {content_type}")
            data = resp.read(_MAX_PDF_SIZE_MB * 1024 * 1024 + 1)
            if len(data) > _MAX_PDF_SIZE_MB * 1024 * 1024:
                return FetchResult(source="not-found", error=f"PDF too large (> {_MAX_PDF_SIZE_MB} MB)")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        time.sleep(1.0)
        return FetchResult(source=source, path=dest, size_bytes=len(data))
    except Exception as exc:
        return FetchResult(source="not-found", error=f"{type(exc).__name__}: {exc}")


def _query_unpaywall(doi: str, timeout: float) -> str:
    """Return the best open-access PDF URL for the DOI, or '' if none."""
    query = urllib.parse.urlencode({"email": _UNPAYWALL_EMAIL})
    url = f"https://api.unpaywall.org/v2/{urllib.parse.quote(doi)}?{query}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        time.sleep(1.0)
        if not payload.get("is_oa"):
            return ""
        best = payload.get("best_oa_location") or {}
        return best.get("url_for_pdf") or ""
    except Exception as exc:
        logger.debug("unpaywall query failed for %s: %s", doi, exc)
        return ""
