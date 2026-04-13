"""PubMed search backend via NCBI E-utilities."""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

from research_hub.search.base import SearchResult

logger = logging.getLogger(__name__)

PUBMED_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_USER_AGENT = "research-hub/0.17.0 (mailto:research-hub@example.invalid)"
_DEFAULT_TIMEOUT = 30
_DEFAULT_DELAY = 0.4


class PubMedBackend:
    name = "pubmed"

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

    def _request(self, endpoint: str, *, params: dict[str, Any]) -> dict[str, Any] | None:
        self._throttle()
        try:
            response = requests.get(
                f"{PUBMED_BASE}/{endpoint}",
                params=params,
                headers={"User-Agent": _USER_AGENT},
                timeout=self.timeout,
            )
        except requests.exceptions.RequestException as exc:
            logger.debug("PubMed request failed: %s", exc)
            return None
        if response.status_code != 200:
            return None
        try:
            payload = response.json()
        except ValueError:
            return None
        return payload if isinstance(payload, dict) else None

    def search(
        self,
        query: str,
        *,
        limit: int = 20,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[SearchResult]:
        term = query
        if year_from is not None or year_to is not None:
            yf = year_from or 1900
            yt = year_to or 2099
            term = f"({term}) AND {yf}:{yt}[pdat]"
        esearch_payload = self._request(
            "esearch.fcgi",
            params={
                "db": "pubmed",
                "term": term,
                "retmode": "json",
                "retmax": min(limit, 100),
                "sort": "relevance",
            },
        )
        if esearch_payload is None:
            return []
        pmid_list = esearch_payload.get("esearchresult", {}).get("idlist", []) or []
        if not pmid_list:
            return []

        esummary_payload = self._request(
            "esummary.fcgi",
            params={
                "db": "pubmed",
                "id": ",".join(pmid_list),
                "retmode": "json",
            },
        )
        if esummary_payload is None:
            return []
        result_block = esummary_payload.get("result", {}) or {}
        results: list[SearchResult] = []
        for pmid in pmid_list:
            entry = result_block.get(pmid)
            if isinstance(entry, dict):
                results.append(self._parse_entry(pmid, entry))
        return results

    def get_paper(self, identifier: str) -> SearchResult | None:
        cleaned = identifier.strip()
        term = f'"{cleaned}"[doi]' if "/" in cleaned else cleaned
        results = self.search(term, limit=1)
        return results[0] if results else None

    def _parse_entry(self, pmid: str, entry: dict[str, Any]) -> SearchResult:
        authors_raw = entry.get("authors") or []
        authors = [author.get("name", "") for author in authors_raw if isinstance(author, dict) and author.get("name")]
        pubdate = entry.get("pubdate", "") or entry.get("epubdate", "") or ""
        year = None
        year_str = pubdate.split()[0] if pubdate else ""
        if year_str.isdigit():
            year = int(year_str)

        doi = ""
        for aid in entry.get("articleids") or []:
            if isinstance(aid, dict) and aid.get("idtype") == "doi":
                doi = (aid.get("value") or "").lower()
                break

        venue = entry.get("source", "") or entry.get("fulljournalname", "") or ""
        return SearchResult(
            title=entry.get("title", "") or "",
            doi=doi,
            arxiv_id="",
            abstract="",
            year=year,
            authors=authors,
            venue=venue,
            url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            citation_count=0,
            pdf_url="",
            source=self.name,
            doc_type="journal-article",
        )
