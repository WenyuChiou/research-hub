"""Pre-upload URL quality classifier for NotebookLM sources.

Hybrid detector: metadata tier (no network) + active HTTP probe (ambiguous
publisher URLs). Fail-safe: probe errors yield quality="unknown", which is
never skipped (only a positive "likely_error_page" is filtered out).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from urllib.parse import urlparse

# Hosts known to serve open-access content reliably — no probe needed.
_OPEN_HOSTS: frozenset[str] = frozenset(
    [
        "arxiv.org",
        "www.arxiv.org",
        "biorxiv.org",
        "www.biorxiv.org",
        "medrxiv.org",
        "www.medrxiv.org",
        "chemrxiv.org",
        "www.chemrxiv.org",
        "europepmc.org",
        "www.ncbi.nlm.nih.gov",
        "pmc.ncbi.nlm.nih.gov",
        "pubmed.ncbi.nlm.nih.gov",
        "zenodo.org",
        "figshare.com",
        "osf.io",
    ]
)

# Browser-style User-Agent for active probes (matches house pattern in pdf_fetcher.py)
_PROBE_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_BODY_CAP_BYTES = 200_000  # 200 KB body cap for probes


@dataclass
class UrlQuality:
    quality: str  # "ok" | "likely_error_page" | "unknown"
    reason: str
    signal: str


def _probe_url(url: str, *, timeout: int = 8) -> UrlQuality:
    """Active HTTP probe. Kept separate so tests can mock it cleanly.

    Returns UrlQuality. On any exception or timeout → quality="unknown".
    Classification priority:
      1. 403 + Cf-Mitigated: challenge header → cloudflare_block
      2. final URL or body contains /action/cookieAbsent → tf_cookie_wall
      3. <title>~Redirecting and body <5 KB → elsevier_js_redirect
      4. body <10 KB and no abstract/article element → generic_short_body
      5. else → ok
    """
    try:
        import requests  # type: ignore[import-untyped]
    except ImportError:
        return UrlQuality(quality="unknown", reason="requests not available", signal="import_error")

    try:
        resp = requests.get(
            url,
            headers={"User-Agent": _PROBE_USER_AGENT},
            allow_redirects=True,
            timeout=timeout,
            stream=True,
        )
        # Read body up to cap; also enforce a coarse total-deadline guard so a
        # slow-trickle server can't run far past the timeout value.
        chunks = []
        size = 0
        start = time.monotonic()
        for chunk in resp.iter_content(chunk_size=8192):
            chunks.append(chunk)
            size += len(chunk)
            if size >= _BODY_CAP_BYTES:
                break
            if time.monotonic() - start > timeout * 2:
                break
        body_bytes = b"".join(chunks)
        body = body_bytes.decode("utf-8", errors="replace")

        final_url = resp.url if hasattr(resp, "url") else url
        status_code = resp.status_code

        # 1. Cloudflare challenge block
        if status_code == 403 and resp.headers.get("Cf-Mitigated", "").lower() == "challenge":
            return UrlQuality(
                quality="likely_error_page",
                reason="cloudflare_block",
                signal="HTTP 403 + Cf-Mitigated: challenge",
            )

        # 2. Taylor & Francis cookie wall
        if "/action/cookieAbsent" in str(final_url) or "/action/cookieAbsent" in body:
            return UrlQuality(
                quality="likely_error_page",
                reason="tf_cookie_wall",
                signal="/action/cookieAbsent in final URL or body",
            )

        # 3. Elsevier JS redirect (small body + Redirecting title)
        title_match = re.search(r"<title[^>]*>(.*?)</title>", body, re.IGNORECASE | re.DOTALL)
        title_text = title_match.group(1).strip() if title_match else ""
        if re.search(r"redirect", title_text, re.IGNORECASE) and len(body_bytes) < 5_000:
            return UrlQuality(
                quality="likely_error_page",
                reason="elsevier_js_redirect",
                signal=f"<title> contains Redirecting and body {len(body_bytes)} B < 5 KB",
            )

        # 4. Generic short body with no abstract/article element
        has_content = bool(
            re.search(r'class=["\'][^"\']*abstract[^"\']*["\']', body, re.IGNORECASE)
            or re.search(r"<article", body, re.IGNORECASE)
            or re.search(r'id=["\']abstract["\']', body, re.IGNORECASE)
        )
        if len(body_bytes) < 10_000 and not has_content:
            return UrlQuality(
                quality="likely_error_page",
                reason="generic_short_body",
                signal=f"body {len(body_bytes)} B < 10 KB and no abstract/article element",
            )

        return UrlQuality(quality="ok", reason="probe_ok", signal=f"HTTP {status_code}")

    except Exception as exc:  # noqa: BLE001
        return UrlQuality(
            quality="unknown",
            reason="probe_exception",
            signal=str(exc)[:200],
        )


def classify_url_source(
    url: str,
    summarize_status: str | None,
    *,
    probe: bool = True,
    timeout: int = 8,
    abstract_usable: bool | None = None,
) -> UrlQuality:
    """Classify a URL source for upload quality before sending to NotebookLM.

    Tier ordering:

    Tier 2 FIRST (no network): host is in the open-access allowlist (arxiv.org
        etc.) → quality=ok immediately. Cheapest check, always reliable.

    Tier 1 (abstract prior): a separately observed unusable saved abstract, or
        the legacy summarize_status == "failed_no_abstract" signal, retains
        the conservative guard. Summary completion cannot clear this prior.
        If the probe returns ok (HTTP 200), the entry is still classified as
        likely_error_page with reason no_usable_abstract (or the legacy
        probe_cleared_failed_no_abstract reason).
        HTTP 200 alone is not sufficient evidence of accessible content.
        Springer/Wiley skeleton paywall pages return 200 but contain no body;
        NLM also cannot bypass the paywall, so uploading such a URL would
        silently produce zero indexed content. The abstract text fallback is
        preferred when available.
        If probe is unavailable, returns likely_error_page immediately.
        If probe returns non-ok, returns likely_error_page.

    Tier 3 (probe): ambiguous publisher URL → active HTTP GET, body
        classification. probe=False → quality=unknown (safe for tests).

    Fail-safe: any probe exception/timeout → quality="unknown" (never
    skipped downstream; only "likely_error_page" is filtered).

    ``abstract_usable`` observes only the saved Abstract section under the
    caller's content heuristic. It does not establish URL access or full-text
    acquisition. None preserves legacy callers; True cannot clear a legacy
    failed_no_abstract prior.
    """
    # Tier 2 FIRST: open-access host allowlist — cheapest, always reliable
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:  # noqa: BLE001
        host = ""
    if host in _OPEN_HOSTS:
        return UrlQuality("ok", "open_host", f"host {host} in open allowlist")

    can_probe = probe and url.startswith(("http://", "https://"))
    status = (summarize_status or "").strip()

    # Keep the access-quality prior independent of summary completion.
    legacy_missing = status == "failed_no_abstract"
    if legacy_missing or abstract_usable is False:
        reason = "failed_no_abstract" if legacy_missing else "no_usable_abstract"
        if not can_probe:
            return UrlQuality("likely_error_page", reason,
                              "metadata tier, probe unavailable")
        probed = _probe_url(url, timeout=timeout)
        if probed.quality == "ok":
            # A supplied summary and HTTP 200 do not establish accessible paper
            # content on a publisher shell. Preserve the prior and fallback.
            reason = "probe_cleared_failed_no_abstract" if legacy_missing else reason
            return UrlQuality("likely_error_page", reason, probed.signal)
        return UrlQuality("likely_error_page", reason,
                          f"metadata+probe={probed.quality}:{probed.signal}")

    # Tier 3: ambiguous publisher without a negative abstract prior -> probe
    if not can_probe:
        return UrlQuality("unknown", "no_probe", "probe disabled or no URL")
    return _probe_url(url, timeout=timeout)
