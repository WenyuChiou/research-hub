"""OpenAlex search backend."""

from __future__ import annotations

import logging
import re
import time
from urllib.parse import quote

import requests

from research_hub.search.base import SearchResult


logger = logging.getLogger(__name__)

OPENALEX_BASE = "https://api.openalex.org/works"
_MAILTO = "research-hub@example.invalid"
_USER_AGENT = f"research-hub/0.13.0 (mailto:{_MAILTO})"
_ARXIV_URL_RE = re.compile(r"arxiv\.org/abs/(\d{4}\.\d{4,5})")
_DOI_RE = re.compile(r"^10\.\d{4,}/\S+$", re.IGNORECASE)
_ARXIV_RE = re.compile(r"^\d{4}\.\d{4,5}(?:v\d+)?$")


def _reconstruct_abstract(inv_index: dict[str, list[int]] | None) -> str:
    if not inv_index:
        return ""
    positions: list[tuple[int, str]] = []
    for word, indexes in inv_index.items():
        for pos in indexes:
            positions.append((pos, word))
    positions.sort()
    return " ".join(word for _, word in positions)


class OpenAlexBackend:
    """OpenAlex REST backend with polite throttling."""

    name = "openalex"

    def __init__(self, delay_seconds: float = 0.2, timeout: int = 20) -> None:
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

    def _request(self, url: str, *, params: dict[str, str | int]) -> requests.Response | None:
        self._throttle()
        try:
            response = requests.get(
                url,
                params=params,
                timeout=self.timeout,
                headers={"User-Agent": _USER_AGENT},
            )
        except requests.exceptions.RequestException as exc:
            logger.debug("OpenAlex request failed: %s", exc)
            return None
        return response

    def _parse_work(self, work: dict) -> SearchResult:
        doi = work.get("doi") or ""
        if doi.lower().startswith("https://doi.org/"):
            doi = doi[len("https://doi.org/") :]
        authorships = work.get("authorships") or []
        primary_location = work.get("primary_location") or {}
        primary_source = primary_location.get("source") or {}
        open_access = work.get("open_access") or {}
        locations = work.get("locations") or []

        arxiv_id = ""
        for location in locations:
            source = location.get("source") or {}
            if source.get("display_name") != "arXiv":
                continue
            landing_page_url = location.get("landing_page_url") or ""
            match = _ARXIV_URL_RE.search(landing_page_url)
            if match:
                arxiv_id = match.group(1)
                break

        return SearchResult(
            title=work.get("title") or "",
            doi=doi,
            arxiv_id=arxiv_id,
            abstract=_reconstruct_abstract(work.get("abstract_inverted_index")),
            year=work.get("publication_year"),
            authors=[
                authorship.get("author", {}).get("display_name", "")
                for authorship in authorships
                if authorship.get("author", {}).get("display_name")
            ],
            venue=primary_source.get("display_name") or "",
            url=work.get("id") or "",
            citation_count=work.get("cited_by_count", 0) or 0,
            pdf_url=(
                open_access.get("oa_url", "") or ""
                if open_access.get("is_oa") is True
                else ""
            ),
            source=self.name,
            doc_type=work.get("type", "") or "",
        )

    def search(
        self,
        query: str,
        *,
        limit: int = 20,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[SearchResult]:
        params: dict[str, str | int] = {
            "search": query,
            "per-page": min(limit, 200),
            "select": (
                "id,doi,title,publication_year,authorships,primary_location,locations,"
                "cited_by_count,abstract_inverted_index,open_access,type"
            ),
            "mailto": _MAILTO,
        }
        if year_from is not None or year_to is not None:
            start = "" if year_from is None else str(year_from)
            end = "" if year_to is None else str(year_to)
            params["filter"] = f"publication_year:{start}-{end}"

        response = self._request(OPENALEX_BASE, params=params)
        if response is None:
            return []
        try:
            response.raise_for_status()
            payload = response.json()
        except (ValueError, requests.exceptions.RequestException) as exc:
            logger.debug("OpenAlex search failed: %s", exc)
            return []
        return [self._parse_work(work) for work in payload.get("results", [])]

    def get_paper(self, identifier: str) -> SearchResult | None:
        cleaned = identifier.strip()
        if _DOI_RE.match(cleaned):
            response = self._request(
                f"{OPENALEX_BASE}/https://doi.org/{quote(cleaned, safe='')}",
                params={"mailto": _MAILTO},
            )
            if response is None:
                return None
            if response.status_code == 404:
                logger.debug("OpenAlex DOI not found: %s", cleaned)
                return None
            try:
                response.raise_for_status()
                return self._parse_work(response.json())
            except (ValueError, requests.exceptions.RequestException) as exc:
                logger.debug("OpenAlex DOI lookup failed: %s", exc)
                return None

        if _ARXIV_RE.match(cleaned):
            arxiv_id = cleaned.split("v", 1)[0]
            response = self._request(
                OPENALEX_BASE,
                params={
                    "filter": f"locations.landing_page_url:https://arxiv.org/abs/{arxiv_id}",
                    "per-page": 1,
                    "select": (
                        "id,doi,title,publication_year,authorships,primary_location,locations,"
                        "cited_by_count,abstract_inverted_index,open_access,type"
                    ),
                    "mailto": _MAILTO,
                },
            )
            if response is None:
                return None
            try:
                response.raise_for_status()
                payload = response.json()
            except (ValueError, requests.exceptions.RequestException) as exc:
                logger.debug("OpenAlex arXiv lookup failed: %s", exc)
                return None
            results = payload.get("results", [])
            if not results:
                logger.debug("OpenAlex arXiv not found: %s", arxiv_id)
                return None
            return self._parse_work(results[0])

        return None
