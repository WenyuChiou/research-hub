"""Semantic Scholar search backend."""

from __future__ import annotations

import logging
import os
import time

import requests

from research_hub.errors import UpstreamRateLimited
from research_hub.search.base import SearchResult

logger = logging.getLogger(__name__)


SEMANTIC_SCHOLAR_BASE = "https://api.semanticscholar.org/graph/v1"
DEFAULT_FIELDS = (
    "title,abstract,year,authors,externalIds,venue,citationCount,url,openAccessPdf,publicationTypes,"
    "journal"
)

# v0.88.12: env var the user sets if they've applied for a free
# Semantic Scholar API key (https://www.semanticscholar.org/product/api).
# Unauthenticated sustained rate is ~100 req per 5 min shared across all
# anonymous callers — Stage B hit this wall as HTTP 429. With a key,
# the published limit is ~1 req/sec dedicated per key — ~50× headroom.
SEMANTIC_SCHOLAR_API_KEY_ENV = "SEMANTIC_SCHOLAR_API_KEY"


class RateLimitError(UpstreamRateLimited):
    """Semantic Scholar returned HTTP 429."""

    def __init__(
        self,
        message: str | None = None,
        *,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(
            "Semantic Scholar",
            retry_after=retry_after,
            message=message or "Semantic Scholar rate-limited (HTTP 429)",
        )


class SemanticScholarClient:
    """Thin Semantic Scholar REST client with polite throttling.

    v0.88.12: when ``SEMANTIC_SCHOLAR_API_KEY`` env var is set, the
    client sends it as the ``x-api-key`` header on every request and
    drops the polite throttle delay (S2's published authenticated rate
    is ~1 req/sec, well above our default 3 s polite delay).
    """

    name = "semantic-scholar"

    def __init__(
        self,
        delay_seconds: float = 3.0,
        timeout: int = 30,
        api_key: str | None = None,
    ) -> None:
        # If api_key is None, fall back to the env var. Pass api_key=""
        # explicitly to force-disable env lookup (useful for tests).
        if api_key is None:
            # v0.88.15: .strip() before truthiness check so a whitespace-
            # only env var ("export SEMANTIC_SCHOLAR_API_KEY='  '") is
            # treated as anonymous rather than sending the whitespace as
            # `x-api-key` and triggering a misleading 403.
            raw = os.environ.get(SEMANTIC_SCHOLAR_API_KEY_ENV, "") or ""
            api_key = raw.strip() or None
        # Also normalize an explicit api_key=" " arg the same way
        elif isinstance(api_key, str):
            api_key = api_key.strip() or None
        if isinstance(api_key, str):
            try:
                api_key.encode("latin-1")
            except UnicodeEncodeError:
                logger.warning(
                    "%s is not ASCII/latin-1 (looks like a placeholder or "
                    "mojibake); ignoring it and querying Semantic Scholar "
                    "anonymously.",
                    SEMANTIC_SCHOLAR_API_KEY_ENV,
                )
                api_key = None
        self.api_key = api_key
        # Authenticated clients can poll faster; cap the throttle so a
        # key-holder doesn't waste the rate budget.
        self.delay = 1.0 if api_key else delay_seconds
        self.timeout = timeout
        self._last_request: float | None = None

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return headers

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
                headers=self._headers(),
            )
        except requests.exceptions.RequestException:
            return []
        if response.status_code == 429:
            if self.api_key:
                # Authenticated 429 = we genuinely exceeded the per-key
                # rate; back off harder. Anonymous 429 = shared-pool
                # contention; suggest applying for a key.
                logger.warning(
                    "semantic-scholar rate-limited (HTTP 429) WITH API key. "
                    "Back off harder or check key validity."
                )
            else:
                logger.warning(
                    "semantic-scholar rate-limited (HTTP 429); "
                    "backend returned 0 results. Consider requesting an API key at "
                    "https://www.semanticscholar.org/product/api#api-key-form and "
                    "exporting it as SEMANTIC_SCHOLAR_API_KEY, "
                    "or using --backend-trace to see the silent-drop."
                )
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
                headers=self._headers(),
            )
        except requests.exceptions.RequestException:
            return None
        if response.status_code == 429:
            raise RateLimitError("Semantic Scholar rate-limited (HTTP 429)")
        if response.status_code != 200:
            return None
        try:
            return SearchResult.from_s2_json(response.json())
        except ValueError:
            return None

    def get_recommendations(
        self,
        paper_id: str,
        limit: int = 20,
    ) -> list[SearchResult]:
        """Fetch paper recommendations for a given Semantic Scholar paper ID.

        Uses the free S2 recommendations/v1 endpoint.  The ``paper_id`` may be
        a Semantic Scholar corpus ID, a DOI (``DOI:<doi>``), or an arXiv ID
        (``arXiv:<arxiv_id>``).  Returns an empty list on any network or API
        failure (never raises).
        """
        self._throttle()
        url = (
            f"https://api.semanticscholar.org/recommendations/v1"
            f"/papers/forpaper/{paper_id}"
        )
        params: dict[str, str | int] = {
            "limit": min(limit, 500),
            "fields": DEFAULT_FIELDS,
        }
        try:
            response = requests.get(
                url,
                params=params,
                timeout=self.timeout,
                headers=self._headers(),
            )
        except requests.exceptions.RequestException as exc:
            logger.warning("S2 recommendations network error for %s: %s", paper_id, exc)
            return []
        if response.status_code == 429:
            logger.warning(
                "semantic-scholar recommendations rate-limited (HTTP 429) for %s", paper_id
            )
            time.sleep(self.delay * 2)
            return []
        if response.status_code != 200:
            logger.debug(
                "S2 recommendations non-200 (%s) for %s", response.status_code, paper_id
            )
            return []
        try:
            data = response.json()
        except ValueError as exc:
            logger.warning("S2 recommendations invalid JSON for %s: %s", paper_id, exc)
            return []
        items = data.get("recommendedPapers", [])
        results = []
        for item in items:
            try:
                results.append(SearchResult.from_s2_json(item))
            except Exception:
                pass
        return results
