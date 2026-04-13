"""ERIC (Education Resources Information Center) backend."""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

from research_hub.search.base import SearchResult

logger = logging.getLogger(__name__)

ERIC_BASE = "https://api.ies.ed.gov/eric/"
_USER_AGENT = "research-hub/0.18.0"
_DEFAULT_TIMEOUT = 30
_DEFAULT_DELAY = 0.4


class EricBackend:
    name = "eric"

    def __init__(self, delay_seconds: float = _DEFAULT_DELAY, timeout: int = _DEFAULT_TIMEOUT) -> None:
        self.delay = delay_seconds
        self.timeout = timeout
        self._last_request: float | None = None

    def _throttle(self) -> None:
        current = time.time()
        if self._last_request is None:
            self._last_request = current
            return
        elapsed = current - self._last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
            current += self.delay - elapsed
        self._last_request = current

    def search(
        self,
        query: str,
        *,
        limit: int = 20,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[SearchResult]:
        self._throttle()
        q = query
        if year_from is not None or year_to is not None:
            yf = year_from or 1966
            yt = year_to or 2099
            q = f"({q}) AND publicationdateyear:[{yf} TO {yt}]"
        params = {
            "search": q,
            "format": "json",
            "rows": min(limit, 200),
            "fields": "id,title,author,description,publicationdateyear,source,publisher,subject,doi,peerreviewed",
        }
        try:
            response = requests.get(
                ERIC_BASE,
                params=params,
                headers={"User-Agent": _USER_AGENT},
                timeout=self.timeout,
            )
        except requests.exceptions.RequestException as exc:
            logger.debug("ERIC search failed: %s", exc)
            return []
        if response.status_code != 200:
            return []
        try:
            payload = response.json()
        except ValueError:
            return []
        docs = payload.get("response", {}).get("docs", []) or []
        return [self._parse_doc(doc) for doc in docs]

    def get_paper(self, identifier: str) -> SearchResult | None:
        cleaned = identifier.strip()
        if cleaned.startswith("EJ") or cleaned.startswith("ED"):
            results = self.search(f"id:{cleaned}", limit=1)
        elif "/" in cleaned:
            results = self.search(f'doi:"{cleaned}"', limit=1)
        else:
            results = self.search(cleaned, limit=1)
        return results[0] if results else None

    def _parse_doc(self, doc: dict[str, Any]) -> SearchResult:
        title = doc.get("title", "") or ""
        if isinstance(title, list):
            title = title[0] if title else ""
        authors_raw = doc.get("author") or []
        if isinstance(authors_raw, str):
            authors_raw = [authors_raw]
        authors = [author for author in authors_raw if author]
        year = doc.get("publicationdateyear")
        if isinstance(year, str) and year.isdigit():
            year = int(year)
        elif not isinstance(year, int):
            year = None
        venue_raw = doc.get("source") or doc.get("publisher") or ""
        if isinstance(venue_raw, list):
            venue_raw = venue_raw[0] if venue_raw else ""
        doi_raw = doc.get("doi", "") or ""
        if isinstance(doi_raw, list):
            doi_raw = doi_raw[0] if doi_raw else ""
        doi = doi_raw.lower()
        eric_id = doc.get("id", "") or ""
        doc_type = "journal-article" if eric_id.startswith("EJ") else "report"
        return SearchResult(
            title=title,
            doi=doi,
            arxiv_id="",
            abstract=doc.get("description", "") or "",
            year=year,
            authors=authors,
            venue=venue_raw,
            url=f"https://eric.ed.gov/?id={eric_id}" if eric_id else "",
            citation_count=0,
            pdf_url="",
            source=self.name,
            doc_type=doc_type,
        )
