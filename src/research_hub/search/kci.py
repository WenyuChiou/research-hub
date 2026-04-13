"""Korea Citation Index (KCI) search backend.

KCI is the Korean National Research Foundation's citation database for
Korean academic literature. Free OpenAPI access is available for basic
queries with JSON responses.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

from research_hub.search.base import SearchResult

logger = logging.getLogger(__name__)

KCI_BASE = "https://www.kci.go.kr/kciportal/po/search/poArtiSearList.kci"
_USER_AGENT = "research-hub/0.20.0"
_DEFAULT_TIMEOUT = 30
_DEFAULT_DELAY = 0.5


class KciBackend:
    name = "kci"

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
        params: dict[str, Any] = {
            "searchQuery": query,
            "displayCount": min(limit, 100),
            "page": 1,
        }
        if year_from is not None:
            params["startYear"] = year_from
        if year_to is not None:
            params["endYear"] = year_to
        try:
            response = requests.get(
                KCI_BASE,
                params=params,
                headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
                timeout=self.timeout,
            )
        except requests.exceptions.RequestException as exc:
            logger.debug("KCI search failed: %s", exc)
            return []
        if response.status_code != 200:
            return []
        try:
            payload = response.json()
        except ValueError:
            return []
        articles = payload.get("articles") or payload.get("items") or []
        return [self._parse_article(article) for article in articles]

    def get_paper(self, identifier: str) -> SearchResult | None:
        results = self.search(identifier.strip(), limit=1)
        return results[0] if results else None

    def _parse_article(self, article: dict[str, Any]) -> SearchResult:
        title = article.get("titleEng") or article.get("title") or article.get("articleTitle") or ""
        if isinstance(title, list):
            title = title[0] if title else ""

        authors_raw = article.get("authors") or article.get("authorList") or []
        if isinstance(authors_raw, str):
            authors = [author.strip() for author in authors_raw.split(",") if author.strip()]
        elif isinstance(authors_raw, list):
            authors = []
            for author in authors_raw:
                if isinstance(author, dict):
                    name = author.get("nameEng") or author.get("name") or ""
                    if name:
                        authors.append(name)
                elif isinstance(author, str):
                    authors.append(author)
        else:
            authors = []

        year = article.get("publishedYear") or article.get("year") or article.get("pubYear")
        if isinstance(year, str) and year.isdigit():
            year = int(year)
        elif not isinstance(year, int):
            year = None

        venue = article.get("journalNameEng") or article.get("journalName") or article.get("journal") or ""
        if isinstance(venue, list):
            venue = venue[0] if venue else ""

        doi = article.get("doi") or ""
        if isinstance(doi, list):
            doi = doi[0] if doi else ""
        doi = doi.lower()

        url = article.get("linkUrl") or article.get("url") or ""
        if not url and article.get("articleId"):
            article_id = article["articleId"]
            url = (
                "https://www.kci.go.kr/kciportal/ci/sereArticleSearch/ciSereArtiView.kci"
                f"?sereArticleSearchBean.artiId={article_id}"
            )

        abstract = article.get("abstractEng") or article.get("abstract") or ""

        return SearchResult(
            title=title,
            doi=doi,
            arxiv_id="",
            abstract=abstract,
            year=year,
            authors=authors,
            venue=venue,
            url=url,
            citation_count=int(article.get("citedCount", 0) or 0),
            pdf_url="",
            source=self.name,
            doc_type="journal-article",
        )
