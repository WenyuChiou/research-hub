"""bioRxiv and medRxiv preprint search."""

from __future__ import annotations

import logging
import re
import time
from datetime import date, timedelta
from typing import Any

import requests

from research_hub.search.base import SearchResult

logger = logging.getLogger(__name__)

BIORXIV_BASE = "https://api.biorxiv.org/details"
_SERVERS = ("biorxiv", "medrxiv")
_USER_AGENT = "research-hub/0.17.0"
_DEFAULT_TIMEOUT = 30
_DEFAULT_DELAY = 0.5
_FETCH_WINDOW_DAYS = 365


class BiorxivBackend:
    name = "biorxiv"

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
        if year_from is None and year_to is None:
            today = date.today()
            date_to = today.strftime("%Y-%m-%d")
            date_from = (today - timedelta(days=_FETCH_WINDOW_DAYS)).strftime("%Y-%m-%d")
        else:
            yf = year_from or 1990
            yt = year_to or 2099
            date_from = f"{yf}-01-01"
            date_to = f"{yt}-12-31"

        query_terms = {term.lower() for term in re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", query)}
        all_papers: list[SearchResult] = []
        for server in _SERVERS:
            cursor = 0
            fetched_in_server = 0
            while fetched_in_server < limit:
                self._throttle()
                url = f"{BIORXIV_BASE}/{server}/{date_from}/{date_to}/{cursor}"
                try:
                    response = requests.get(
                        url,
                        headers={"User-Agent": _USER_AGENT},
                        timeout=self.timeout,
                    )
                except requests.exceptions.RequestException as exc:
                    logger.debug("biorxiv %s fetch failed: %s", server, exc)
                    break
                if response.status_code != 200:
                    break
                try:
                    payload = response.json()
                except ValueError:
                    break
                collection = payload.get("collection") or []
                if not collection:
                    break
                for entry in collection:
                    if not isinstance(entry, dict):
                        continue
                    result = self._parse_entry(entry, server)
                    if self._matches_query(result, query_terms):
                        all_papers.append(result)
                        fetched_in_server += 1
                        if fetched_in_server >= limit:
                            break
                cursor += 100
                if cursor > 500:
                    break
        return all_papers[: limit * 2]

    def get_paper(self, identifier: str) -> SearchResult | None:
        cleaned = identifier.strip()
        if "/" not in cleaned:
            return None
        for server in _SERVERS:
            self._throttle()
            try:
                response = requests.get(
                    f"{BIORXIV_BASE}/{server}/{cleaned}",
                    headers={"User-Agent": _USER_AGENT},
                    timeout=self.timeout,
                )
            except requests.exceptions.RequestException:
                continue
            if response.status_code != 200:
                continue
            try:
                payload = response.json()
            except ValueError:
                continue
            collection = payload.get("collection") or []
            if collection and isinstance(collection[0], dict):
                return self._parse_entry(collection[0], server)
        return None

    def _matches_query(self, result: SearchResult, terms: set[str]) -> bool:
        """Require ALL query terms to appear in the paper's title or abstract.

        bioRxiv has no server-side text search; this backend pulls a date
        window and filters client-side. A weaker filter (any/majority) is
        overwhelmed by how often generic terms like "protein" and "structure"
        appear in biomedical abstracts. Strict AND is the only setting that
        delivers non-garbage results for typical multi-word queries."""
        if not terms:
            return True
        haystack = f"{result.title} {result.abstract}".lower()
        return all(re.search(rf"\b{re.escape(term)}\b", haystack) for term in terms)

    def _parse_entry(self, entry: dict[str, Any], server: str) -> SearchResult:
        date_str = entry.get("date", "") or ""
        year = None
        try:
            year = int(date_str.split("-")[0]) if date_str else None
        except (ValueError, IndexError):
            year = None
        authors = [author.strip() for author in (entry.get("authors", "") or "").split(";") if author.strip()]
        doi = (entry.get("doi") or "").lower()
        return SearchResult(
            title=entry.get("title", "") or "",
            doi=doi,
            arxiv_id="",
            abstract=entry.get("abstract", "") or "",
            year=year,
            authors=authors,
            venue=server.replace("rxiv", "Rxiv"),
            url=f"https://www.{server}.org/content/{doi}v1" if doi else "",
            citation_count=0,
            pdf_url=f"https://www.{server}.org/content/{doi}v1.full.pdf" if doi else "",
            source=self.name,
            doc_type="preprint",
        )
