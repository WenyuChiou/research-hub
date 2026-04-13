"""ChemRxiv search backend via the Figshare API."""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

from research_hub.search.base import SearchResult

logger = logging.getLogger(__name__)

FIGSHARE_SEARCH = "https://api.figshare.com/v2/articles/search"
FIGSHARE_DETAILS = "https://api.figshare.com/v2/articles"
_CHEMRXIV_GROUP_ID = 13652
_USER_AGENT = "research-hub/0.18.0"
_DEFAULT_TIMEOUT = 30
_DEFAULT_DELAY = 0.5


class ChemrxivBackend:
    name = "chemrxiv"

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
        body: dict[str, Any] = {
            "search_for": query,
            "group": _CHEMRXIV_GROUP_ID,
            "page_size": min(limit, 100),
            "order": "published_date",
            "order_direction": "desc",
        }
        if year_from is not None:
            body["published_since"] = f"{year_from}-01-01"
        try:
            response = requests.post(
                FIGSHARE_SEARCH,
                json=body,
                headers={"User-Agent": _USER_AGENT, "Content-Type": "application/json"},
                timeout=self.timeout,
            )
        except requests.exceptions.RequestException as exc:
            logger.debug("chemrxiv search failed: %s", exc)
            return []
        if response.status_code != 200:
            return []
        try:
            articles = response.json() or []
        except ValueError:
            return []

        results: list[SearchResult] = []
        for article in articles:
            result = self._parse_article(article)
            if year_to is not None and result.year and result.year > year_to:
                continue
            if year_from is not None and result.year and result.year < year_from:
                continue
            results.append(result)
        return results

    def get_paper(self, identifier: str) -> SearchResult | None:
        cleaned = identifier.strip()
        if not cleaned.isdigit():
            results = self.search(cleaned, limit=1)
            return results[0] if results else None

        self._throttle()
        try:
            response = requests.get(
                f"{FIGSHARE_DETAILS}/{cleaned}",
                headers={"User-Agent": _USER_AGENT},
                timeout=self.timeout,
            )
        except requests.exceptions.RequestException:
            return None
        if response.status_code != 200:
            return None
        try:
            return self._parse_article(response.json())
        except ValueError:
            return None

    def _parse_article(self, article: dict[str, Any]) -> SearchResult:
        title = article.get("title", "") or ""
        authors_raw = article.get("authors") or []
        authors = [author.get("full_name", "") for author in authors_raw if isinstance(author, dict)]
        published = article.get("published_date") or article.get("created_date") or ""
        year = None
        if published and len(published) >= 4 and published[:4].isdigit():
            year = int(published[:4])
        doi = (article.get("doi") or "").lower()
        url = article.get("url_public_html") or article.get("url") or ""
        return SearchResult(
            title=title,
            doi=doi,
            arxiv_id="",
            abstract=article.get("description", "") or "",
            year=year,
            authors=authors,
            venue="ChemRxiv",
            url=url,
            citation_count=0,
            pdf_url="",
            source=self.name,
            doc_type="preprint",
        )
