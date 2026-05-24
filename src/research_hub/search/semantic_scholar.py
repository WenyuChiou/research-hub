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
# Unauthenticated access uses a shared public pool and can still return
# 429 under load. With a key, Semantic Scholar's introductory published
# limit is 1 request/sec across all endpoints.
SEMANTIC_SCHOLAR_API_KEY_ENV = "SEMANTIC_SCHOLAR_API_KEY"
SEMANTIC_SCHOLAR_RPS_ENV = "SEMANTIC_SCHOLAR_RPS"
DEFAULT_ANONYMOUS_DELAY_SECONDS = 3.0
DEFAULT_AUTHENTICATED_DELAY_SECONDS = 1.1
DEFAULT_MAX_RETRIES = 2


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
    uses a conservative 1-RPS throttle by default. Advanced users with
    a higher Semantic Scholar quota may set ``SEMANTIC_SCHOLAR_RPS``.
    """

    name = "semantic-scholar"

    def __init__(
        self,
        delay_seconds: float = DEFAULT_ANONYMOUS_DELAY_SECONDS,
        timeout: int = 30,
        api_key: str | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
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
        self.delay = self._resolve_delay(
            api_key=api_key,
            delay_seconds=delay_seconds,
        )
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self._last_request: float | None = None

    @staticmethod
    def _resolve_delay(*, api_key: str | None, delay_seconds: float) -> float:
        rps = _positive_float_env(SEMANTIC_SCHOLAR_RPS_ENV)
        if rps is not None:
            return 1.0 / rps
        if api_key:
            return DEFAULT_AUTHENTICATED_DELAY_SECONDS
        return delay_seconds

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return headers

    def _throttle(self) -> None:
        if self.delay <= 0:
            return
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

    def _retry_delay(self, response: requests.Response, attempt: int) -> float:
        headers = getattr(response, "headers", {}) or {}
        retry_after = headers.get("Retry-After", "")
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                pass
        base = self.delay if self.delay > 0 else 1.0
        return min(30.0, base * (2 ** attempt))

    def _get(self, url: str, **kwargs) -> requests.Response | None:
        for attempt in range(self.max_retries + 1):
            self._throttle()
            try:
                response = requests.get(
                    url,
                    timeout=self.timeout,
                    headers=self._headers(),
                    **kwargs,
                )
            except requests.exceptions.RequestException:
                return None
            if response.status_code != 429:
                return response
            retry_delay = self._retry_delay(response, attempt)
            if attempt >= self.max_retries:
                return response
            logger.warning(
                "semantic-scholar rate-limited (HTTP 429); retrying in %.1fs "
                "(attempt %d/%d, auth=%s)",
                retry_delay,
                attempt + 1,
                self.max_retries,
                "api-key" if self.api_key else "anonymous",
            )
            time.sleep(retry_delay)
        return None

    def search(
        self,
        query: str,
        limit: int = 20,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[SearchResult]:
        """Search papers by query."""
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
            response = self._get(
                f"{SEMANTIC_SCHOLAR_BASE}/paper/search",
                params=params,
            )
        except requests.exceptions.RequestException:
            return []
        if response is None:
            return []
        if response.status_code == 429:
            if self.api_key:
                # Authenticated 429 = we genuinely exceeded the per-key
                # rate. Anonymous 429 = shared-pool
                # contention; suggest applying for a key.
                logger.warning(
                    "semantic-scholar rate-limited (HTTP 429) WITH API key "
                    "after %d retry attempt(s). Default is ~1 request/sec; "
                    "lower %s if your key has a smaller quota.",
                    self.max_retries,
                    SEMANTIC_SCHOLAR_RPS_ENV,
                )
            else:
                logger.warning(
                    "semantic-scholar rate-limited (HTTP 429) after %d retry attempt(s); "
                    "backend returned 0 results. Consider requesting an API key at "
                    "https://www.semanticscholar.org/product/api#api-key-form and "
                    "exporting it as SEMANTIC_SCHOLAR_API_KEY, "
                    "or using --backend-trace to see the silent-drop.",
                    self.max_retries,
                )
            return []
        try:
            response.raise_for_status()
        except requests.exceptions.RequestException:
            return []
        return [SearchResult.from_s2_json(item) for item in response.json().get("data", [])]

    def get_paper(self, identifier: str) -> SearchResult | None:
        """Fetch a single paper by DOI, arXiv ID, or Semantic Scholar ID."""
        try:
            response = self._get(
                f"{SEMANTIC_SCHOLAR_BASE}/paper/{identifier}",
                params={"fields": DEFAULT_FIELDS},
            )
        except requests.exceptions.RequestException:
            return None
        if response is None:
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
        url = (
            f"https://api.semanticscholar.org/recommendations/v1"
            f"/papers/forpaper/{paper_id}"
        )
        params: dict[str, str | int] = {
            "limit": min(limit, 500),
            "fields": DEFAULT_FIELDS,
        }
        try:
            response = self._get(
                url,
                params=params,
            )
        except requests.exceptions.RequestException as exc:
            logger.warning("S2 recommendations network error for %s: %s", paper_id, exc)
            return []
        if response is None:
            return []
        if response.status_code == 429:
            logger.warning(
                "semantic-scholar recommendations rate-limited (HTTP 429) for %s "
                "after %d retry attempt(s)",
                paper_id,
                self.max_retries,
            )
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


def _positive_float_env(name: str) -> float | None:
    raw = os.environ.get(name, "")
    if not raw or not raw.strip():
        return None
    try:
        value = float(raw.strip())
    except ValueError:
        logger.warning("%s=%r is not a number; using Semantic Scholar defaults.", name, raw)
        return None
    if value <= 0:
        logger.warning("%s=%r must be positive; using Semantic Scholar defaults.", name, raw)
        return None
    return value
