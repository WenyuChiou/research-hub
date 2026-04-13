"""NASA Astrophysics Data System (ADS) search backend."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests

from research_hub.search.base import SearchResult

logger = logging.getLogger(__name__)

ADS_BASE = "https://api.adsabs.harvard.edu/v1/search/query"
_USER_AGENT = "research-hub/0.18.0"
_DEFAULT_TIMEOUT = 30
_DEFAULT_DELAY = 0.5
_ENV_KEY = "ADS_DEV_KEY"


class NasaAdsBackend:
    name = "nasa-ads"

    def __init__(self, delay_seconds: float = _DEFAULT_DELAY, timeout: int = _DEFAULT_TIMEOUT) -> None:
        self.delay = delay_seconds
        self.timeout = timeout
        self._last_request: float | None = None
        self._warned_no_key = False

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

    def _api_key(self) -> str | None:
        key = os.environ.get(_ENV_KEY, "").strip()
        if not key:
            if not self._warned_no_key:
                logger.warning(
                    "NASA ADS backend requires %s environment variable. "
                    "Get a free key at https://ui.adsabs.harvard.edu/user/settings/token",
                    _ENV_KEY,
                )
                self._warned_no_key = True
            return None
        return key

    def search(
        self,
        query: str,
        *,
        limit: int = 20,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[SearchResult]:
        key = self._api_key()
        if key is None:
            return []
        self._throttle()
        q = query
        if year_from is not None or year_to is not None:
            yf = year_from or 1900
            yt = year_to or 2099
            q = f"{q} year:[{yf} TO {yt}]"
        params = {
            "q": q,
            "rows": min(limit, 100),
            "fl": "bibcode,title,author,year,pub,doi,abstract,citation_count,doctype",
            "sort": "date desc",
        }
        try:
            response = requests.get(
                ADS_BASE,
                params=params,
                headers={"Authorization": f"Bearer {key}", "User-Agent": _USER_AGENT},
                timeout=self.timeout,
            )
        except requests.exceptions.RequestException as exc:
            logger.debug("NASA ADS search failed: %s", exc)
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
        key = self._api_key()
        if key is None:
            return None
        cleaned = identifier.strip()
        if "/" in cleaned:
            results = self.search(f'doi:"{cleaned}"', limit=1)
        else:
            results = self.search(f'bibcode:"{cleaned}"', limit=1)
        return results[0] if results else None

    def _parse_doc(self, doc: dict[str, Any]) -> SearchResult:
        title_list = doc.get("title") or []
        title = title_list[0] if title_list else ""
        authors = doc.get("author") or []
        year = doc.get("year")
        if isinstance(year, str) and year.isdigit():
            year = int(year)
        elif not isinstance(year, int):
            year = None
        doi_list = doc.get("doi") or []
        doi = (doi_list[0] if doi_list else "").lower()
        venue = doc.get("pub", "") or ""
        bibcode = doc.get("bibcode", "") or ""
        return SearchResult(
            title=title,
            doi=doi,
            arxiv_id="",
            abstract=doc.get("abstract", "") or "",
            year=year,
            authors=authors,
            venue=venue,
            url=f"https://ui.adsabs.harvard.edu/abs/{bibcode}/abstract" if bibcode else "",
            citation_count=int(doc.get("citation_count", 0) or 0),
            pdf_url="",
            source=self.name,
            doc_type=(doc.get("doctype", "") or "").lower(),
        )
