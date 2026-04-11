"""Experimental headless Semantic Scholar search client for Research Hub."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Iterable

import requests


SEMANTIC_SCHOLAR_BASE = "https://api.semanticscholar.org/graph/v1"
DEFAULT_FIELDS = (
    "title,abstract,year,authors,externalIds,venue,citationCount,url,openAccessPdf"
)


@dataclass
class SearchResult:
    """Normalized search result."""

    title: str
    doi: str = ""
    abstract: str = ""
    year: int | None = None
    authors: list[str] = field(default_factory=list)
    venue: str = ""
    url: str = ""
    citation_count: int = 0
    pdf_url: str = ""
    source: str = "semantic-scholar"

    @classmethod
    def from_s2_json(cls, item: dict) -> "SearchResult":
        """Create a result from Semantic Scholar JSON."""
        authors = [author.get("name", "") for author in item.get("authors") or [] if author.get("name")]
        external_ids = item.get("externalIds") or {}
        pdf = item.get("openAccessPdf") or {}
        return cls(
            title=item.get("title") or "",
            doi=external_ids.get("DOI", "") or "",
            abstract=item.get("abstract") or "",
            year=item.get("year"),
            authors=authors,
            venue=item.get("venue") or "",
            url=item.get("url") or "",
            citation_count=item.get("citationCount", 0) or 0,
            pdf_url=pdf.get("url", "") or "",
        )


class SemanticScholarClient:
    """Thin Semantic Scholar REST client with polite throttling."""

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
    ) -> list[SearchResult]:
        """Search papers by query."""
        self._throttle()
        params: dict[str, str | int] = {
            "query": query,
            "limit": min(limit, 100),
            "fields": DEFAULT_FIELDS,
        }
        if year_from:
            params["year"] = f"{year_from}-"
        response = requests.get(
            f"{SEMANTIC_SCHOLAR_BASE}/paper/search",
            params=params,
            timeout=self.timeout,
        )
        if response.status_code == 429:
            time.sleep(self.delay * 2)
            return []
        response.raise_for_status()
        return [SearchResult.from_s2_json(item) for item in response.json().get("data", [])]

    def get_paper(self, identifier: str) -> SearchResult | None:
        """Fetch a single paper by DOI, arXiv ID, or Semantic Scholar ID."""
        self._throttle()
        response = requests.get(
            f"{SEMANTIC_SCHOLAR_BASE}/paper/{identifier}",
            params={"fields": DEFAULT_FIELDS},
            timeout=self.timeout,
        )
        if response.status_code != 200:
            return None
        return SearchResult.from_s2_json(response.json())


def iter_new_results(
    client: SemanticScholarClient,
    query: str,
    already_ingested: Iterable[str],
    limit: int = 20,
) -> list[SearchResult]:
    """Filter search results by normalized DOI."""
    from research_hub.dedup import normalize_doi

    ingested = {normalize_doi(doi) for doi in already_ingested}
    return [
        result
        for result in client.search(query, limit=limit)
        if normalize_doi(result.doi) not in ingested
    ]
