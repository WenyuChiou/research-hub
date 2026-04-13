"""Semantic Scholar search backend."""

from __future__ import annotations

import time

import requests

from research_hub.search.base import SearchResult


SEMANTIC_SCHOLAR_BASE = "https://api.semanticscholar.org/graph/v1"
DEFAULT_FIELDS = (
    "title,abstract,year,authors,externalIds,venue,citationCount,url,openAccessPdf,publicationTypes"
)


class SemanticScholarClient:
    """Thin Semantic Scholar REST client with polite throttling."""

    name = "semantic-scholar"

    def __init__(self, delay_seconds: float = 3.0, timeout: int = 30) -> None:
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

    def search(
        self,
        query: str,
        limit: int = 20,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[SearchResult]:
        """Search papers by query."""
        self._throttle()
        params: dict[str, str | int] = {
            "query": query,
            "limit": min(limit, 100),
            "fields": DEFAULT_FIELDS,
        }
        if year_from is not None or year_to is not None:
            start = "" if year_from is None else str(year_from)
            end = "" if year_to is None else str(year_to)
            params["year"] = f"{start}-{end}"
        try:
            response = requests.get(
                f"{SEMANTIC_SCHOLAR_BASE}/paper/search",
                params=params,
                timeout=self.timeout,
            )
        except requests.exceptions.RequestException:
            return []
        if response.status_code == 429:
            time.sleep(self.delay * 2)
            return []
        try:
            response.raise_for_status()
        except requests.exceptions.RequestException:
            return []
        return [SearchResult.from_s2_json(item) for item in response.json().get("data", [])]

    def get_paper(self, identifier: str) -> SearchResult | None:
        """Fetch a single paper by DOI, arXiv ID, or Semantic Scholar ID."""
        self._throttle()
        try:
            response = requests.get(
                f"{SEMANTIC_SCHOLAR_BASE}/paper/{identifier}",
                params={"fields": DEFAULT_FIELDS},
                timeout=self.timeout,
            )
        except requests.exceptions.RequestException:
            return None
        if response.status_code != 200:
            return None
        try:
            return SearchResult.from_s2_json(response.json())
        except ValueError:
            return None
