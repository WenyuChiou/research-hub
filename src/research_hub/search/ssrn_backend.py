"""SSRN (Social Science Research Network) search backend.

Uses the SSRN public search API. No API key required.
Returns preprints from social science, economics, law, behavioral science,
and related fields — particularly useful for socio-hydrology, policy, and
interdisciplinary research not well-covered by CS/physics backends.

API endpoint: https://api.ssrn.com/content/search/
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import requests
from research_hub.audit import http_request, read_json

from research_hub.search.base import SearchResult
from research_hub._useragent import user_agent

logger = logging.getLogger(__name__)

_USER_AGENT = user_agent()
_SSRN_SEARCH_URL = "https://api.ssrn.com/content/search/"
_DEFAULT_TIMEOUT = 30
_DEFAULT_DELAY = 1.0


class SsrnBackend:
    """SSRN preprint search — social science, economics, law, policy."""

    name = "ssrn"

    def __init__(
        self,
        delay_seconds: float = _DEFAULT_DELAY,
        timeout: int = _DEFAULT_TIMEOUT,
    ) -> None:
        self.delay = delay_seconds
        self.timeout = timeout
        self._last_request: Optional[float] = None

    def _throttle(self) -> None:
        now = time.time()
        if self._last_request is not None:
            elapsed = now - self._last_request
            if elapsed < self.delay:
                time.sleep(self.delay - elapsed)
        self._last_request = time.time()

    def search(
        self,
        query: str,
        *,
        limit: int = 20,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
    ) -> list[SearchResult]:
        self._throttle()
        try:
            resp = http_request("get",
                _SSRN_SEARCH_URL,
                params={"q": query, "per_page": min(limit, 50), "sort": "rel"},
                headers={"User-Agent": _USER_AGENT},
                timeout=self.timeout,
            )
        except requests.exceptions.RequestException as exc:
            logger.debug("SSRN search request failed: %s", exc)
            return []

        if resp.status_code != 200:
            logger.debug("SSRN search returned HTTP %d", resp.status_code)
            return []

        try:
            data = read_json(resp, collections=(("papers",), ("results",), ()))
        except Exception as exc:
            logger.debug("SSRN JSON parse failed: %s", exc)
            return []

        # The API may return {"papers": [...]} or {"results": [...]} or a bare list.
        # Use explicit key presence to avoid falsy cross-contamination:
        # {"papers": [], "results": [...]} would wrongly use "results" with `or`.
        if "papers" in data:
            papers = data["papers"] if isinstance(data["papers"], list) else []
        elif "results" in data:
            papers = data["results"] if isinstance(data["results"], list) else []
        elif isinstance(data, list):
            papers = data
        else:
            papers = []

        results: list[SearchResult] = []
        for paper in papers:
            if len(results) >= limit:
                break
            result = self._convert(paper)
            if result is None:
                continue
            if year_from and result.year and result.year < year_from:
                continue
            if year_to and result.year and result.year > year_to:
                continue
            results.append(result)
        return results

    def get_paper(self, identifier: str) -> Optional[SearchResult]:
        results = self.search(identifier, limit=1)
        return results[0] if results else None

    def _convert(self, paper: dict) -> Optional[SearchResult]:
        title = (paper.get("title") or "").strip()
        if not title:
            return None

        year: Optional[int] = None
        date_str = paper.get("date") or paper.get("submission_date") or ""
        if date_str:
            try:
                year = int(str(date_str)[:4])
            except (ValueError, TypeError):
                pass

        authors_raw = paper.get("authors") or []
        authors: list[str] = []
        if isinstance(authors_raw, list):
            for author in authors_raw:
                if isinstance(author, dict):
                    name = (
                        author.get("name")
                        or f"{author.get('firstName', '')} {author.get('lastName', '')}".strip()
                    )
                    if name:
                        authors.append(name)
                elif isinstance(author, str) and author.strip():
                    authors.append(author.strip())

        doi = (paper.get("doi") or "").strip()
        abstract_id = paper.get("abstract_id") or paper.get("id") or ""
        url = paper.get("url") or (
            f"https://papers.ssrn.com/abstract={abstract_id}" if abstract_id else ""
        )
        abstract = (paper.get("abstract") or "").strip()

        return SearchResult(
            title=title,
            doi=doi,
            arxiv_id="",
            abstract=abstract,
            year=year,
            authors=authors,
            venue=paper.get("journal") or "",
            url=url,
            citation_count=int(paper.get("downloads") or 0),
            pdf_url="",
            source=self.name,
            doc_type="preprint",
            confidence=0.5,
        )
