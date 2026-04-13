"""DBLP search backend."""

from __future__ import annotations

import logging
import time

import requests

from research_hub.search.base import SearchResult


logger = logging.getLogger(__name__)

DBLP_BASE = "https://dblp.org/search/publ/api"
_USER_AGENT = "research-hub/0.16.0"
_DEFAULT_TIMEOUT = 20

_TYPE_MAP = {
    "Conference and Workshop Papers": "conference-paper",
    "Journal Articles": "journal-article",
    "Books": "book",
    "Parts in Books or Collections": "book-chapter",
    "Editorship": "editorial",
    "Reference Works": "reference-entry",
    "Informal Publications": "preprint",
}


class DblpBackend:
    """DBLP metadata backend."""

    name = "dblp"

    def __init__(self, delay_seconds: float = 0.5, timeout: int = _DEFAULT_TIMEOUT) -> None:
        self.delay = delay_seconds
        self.timeout = timeout
        self._last_request: float | None = None

    def _throttle(self) -> None:
        current_time = time.time()
        if self._last_request is None:
            self._last_request = current_time
            return
        elapsed = current_time - self._last_request
        if elapsed < self.delay:
            sleep_for = self.delay - elapsed
            time.sleep(sleep_for)
            current_time += sleep_for
        self._last_request = current_time

    def _request(self, params: dict[str, str | int]) -> requests.Response | None:
        self._throttle()
        try:
            return requests.get(
                DBLP_BASE,
                params=params,
                timeout=self.timeout,
                headers={"User-Agent": _USER_AGENT},
            )
        except requests.exceptions.RequestException as exc:
            logger.debug("DBLP request failed: %s", exc)
            return None

    def search(
        self,
        query: str,
        *,
        limit: int = 20,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[SearchResult]:
        response = self._request({"q": query, "format": "json", "h": min(limit, 1000)})
        if response is None:
            return []
        try:
            response.raise_for_status()
            payload = response.json()
        except (ValueError, requests.exceptions.RequestException) as exc:
            logger.debug("DBLP search failed: %s", exc)
            return []
        hits = (((payload.get("result") or {}).get("hits") or {}).get("hit") or [])
        if isinstance(hits, dict):
            hits = [hits]
        results = [self._parse_hit(hit) for hit in hits]
        if year_from is None and year_to is None:
            return results
        filtered: list[SearchResult] = []
        for result in results:
            if result.year is None:
                continue
            if year_from is not None and result.year < year_from:
                continue
            if year_to is not None and result.year > year_to:
                continue
            filtered.append(result)
        return filtered

    def get_paper(self, identifier: str) -> SearchResult | None:
        results = self.search(identifier, limit=1)
        return results[0] if results else None

    def _parse_hit(self, hit: dict) -> SearchResult:
        info = hit.get("info") or {}
        title = (info.get("title", "") or "").rstrip(".")
        authors_field = info.get("authors") or {}
        author_list = authors_field.get("author") or []
        if isinstance(author_list, dict):
            author_list = [author_list]
        authors = [author.get("text", "") if isinstance(author, dict) else str(author) for author in author_list]
        year = int(info["year"]) if str(info.get("year", "")).isdigit() else None
        dblp_type = info.get("type", "") or ""
        return SearchResult(
            title=title,
            doi=(info.get("doi") or "").lower(),
            abstract="",
            year=year,
            authors=[author for author in authors if author],
            venue=info.get("venue", "") or "",
            url=info.get("ee", "") or info.get("url", "") or "",
            citation_count=0,
            source=self.name,
            doc_type=_TYPE_MAP.get(dblp_type, dblp_type.lower().replace(" ", "-")),
        )
