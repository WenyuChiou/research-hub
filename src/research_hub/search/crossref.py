"""Crossref REST API backend."""

from __future__ import annotations

import logging
import time
from urllib.parse import quote

import requests

from research_hub.search.base import SearchResult


logger = logging.getLogger(__name__)

CROSSREF_BASE = "https://api.crossref.org/works"
_USER_AGENT = "research-hub/0.16.0 (mailto:research-hub@example.invalid)"
_DEFAULT_TIMEOUT = 20


class CrossrefBackend:
    """Crossref metadata backend."""

    name = "crossref"

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

    def _request(self, url: str, *, params: dict[str, str | int] | None = None) -> requests.Response | None:
        self._throttle()
        try:
            return requests.get(
                url,
                params=params,
                timeout=self.timeout,
                headers={"User-Agent": _USER_AGENT},
            )
        except requests.exceptions.RequestException as exc:
            logger.debug("Crossref request failed: %s", exc)
            return None

    def search(
        self,
        query: str,
        *,
        limit: int = 20,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[SearchResult]:
        params: dict[str, str | int] = {
            "query": query,
            "rows": min(limit, 100),
            "select": (
                "DOI,title,author,issued,container-title,type,is-referenced-by-count,"
                "volume,issue,page"
            ),
        }
        filters = []
        if year_from is not None:
            filters.append(f"from-pub-date:{year_from}-01-01")
        if year_to is not None:
            filters.append(f"until-pub-date:{year_to}-12-31")
        filters.append("type:journal-article")
        if filters:
            params["filter"] = ",".join(filters)

        response = self._request(CROSSREF_BASE, params=params)
        if response is None or response.status_code == 404:
            return []
        try:
            response.raise_for_status()
            payload = response.json()
        except (ValueError, requests.exceptions.RequestException) as exc:
            logger.debug("Crossref search failed: %s", exc)
            return []
        items = ((payload.get("message") or {}).get("items") or [])
        return [self._parse_work(work) for work in items]

    def get_paper(self, identifier: str) -> SearchResult | None:
        response = self._request(f"{CROSSREF_BASE}/{quote(identifier.strip(), safe='')}")
        if response is None or response.status_code == 404:
            return None
        try:
            response.raise_for_status()
            payload = response.json()
        except (ValueError, requests.exceptions.RequestException) as exc:
            logger.debug("Crossref DOI lookup failed: %s", exc)
            return None
        work = (payload.get("message") or {})
        return self._parse_work(work) if work else None

    def _parse_work(self, work: dict) -> SearchResult:
        title_list = work.get("title") or []
        title = title_list[0] if title_list else ""
        authors: list[str] = []
        for author in work.get("author") or []:
            family = author.get("family", "")
            given = author.get("given", "")
            if family and given:
                authors.append(f"{given} {family}")
            elif family:
                authors.append(family)
        issued = work.get("issued") or {}
        date_parts = issued.get("date-parts") or [[]]
        year = date_parts[0][0] if date_parts and date_parts[0] else None
        venue_list = work.get("container-title") or []
        venue = venue_list[0] if venue_list else ""
        doi = (work.get("DOI") or "").lower()
        # v0.68.5: Crossref returns `page` as a single string already in the
        # canonical "first-last" form (e.g. "123-145"). volume / issue may be
        # missing for some doc types; fall back to "" rather than None.
        return SearchResult(
            title=title,
            doi=doi,
            abstract="",
            year=year,
            authors=authors,
            venue=venue,
            url=f"https://doi.org/{work.get('DOI', '')}",
            citation_count=int(work.get("is-referenced-by-count", 0) or 0),
            source=self.name,
            doc_type=work.get("type", "") or "",
            volume=str(work.get("volume") or ""),
            issue=str(work.get("issue") or ""),
            pages=str(work.get("page") or ""),
        )
