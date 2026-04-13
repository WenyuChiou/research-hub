"""arXiv API backend."""

from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET

import requests

from research_hub.search.base import SearchResult


logger = logging.getLogger(__name__)

ARXIV_BASE = "http://export.arxiv.org/api/query"
_USER_AGENT = "research-hub/0.13.0 (https://github.com/WenyuChiou/research-hub)"
_ARXIV_ID_RE = re.compile(r"/abs/(\d{4}\.\d{4,5})(?:v\d+)?$")
_DOI_RE = re.compile(r"^10\.\d{4,}/\S+$", re.IGNORECASE)
_ARXIV_RE = re.compile(r"^\d{4}\.\d{4,5}(?:v\d+)?$")
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}


def _collapse_whitespace(text: str | None) -> str:
    return " ".join((text or "").split())


class ArxivBackend:
    """arXiv Atom API backend."""

    name = "arxiv"

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

    def _request(self, params: dict[str, str | int]) -> requests.Response | None:
        self._throttle()
        try:
            return requests.get(
                ARXIV_BASE,
                params=params,
                timeout=self.timeout,
                headers={"User-Agent": _USER_AGENT},
            )
        except requests.exceptions.RequestException as exc:
            logger.debug("arXiv request failed: %s", exc)
            return None

    def _parse_entry(self, entry: ET.Element) -> SearchResult | None:
        paper_url = entry.findtext("atom:id", default="", namespaces=_NS)
        match = _ARXIV_ID_RE.search(paper_url or "")
        if not match:
            return None
        arxiv_id = match.group(1)
        published = entry.findtext("atom:published", default="", namespaces=_NS)
        year = int(published[:4]) if len(published) >= 4 and published[:4].isdigit() else None
        doi = entry.findtext("arxiv:doi", default="", namespaces=_NS) or ""
        return SearchResult(
            title=_collapse_whitespace(entry.findtext("atom:title", default="", namespaces=_NS)),
            doi=doi,
            arxiv_id=arxiv_id,
            abstract=_collapse_whitespace(entry.findtext("atom:summary", default="", namespaces=_NS)),
            year=year,
            authors=[
                name
                for name in (
                    author.findtext("atom:name", default="", namespaces=_NS)
                    for author in entry.findall("atom:author", _NS)
                )
                if name
            ],
            venue="arXiv",
            url=paper_url or "",
            citation_count=0,
            pdf_url=f"https://arxiv.org/pdf/{arxiv_id}.pdf",
            source=self.name,
        )

    def _parse_feed(self, xml_text: str) -> list[SearchResult]:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            logger.debug("arXiv XML parse failed: %s", exc)
            return []
        results: list[SearchResult] = []
        for entry in root.findall("atom:entry", _NS):
            parsed = self._parse_entry(entry)
            if parsed is not None:
                results.append(parsed)
        return results

    def search(
        self,
        query: str,
        *,
        limit: int = 20,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[SearchResult]:
        response = self._request(
            {
                "search_query": f'all:"{query}"',
                "start": 0,
                "max_results": limit,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            }
        )
        if response is None:
            return []
        try:
            response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            logger.debug("arXiv search failed: %s", exc)
            return []
        results = self._parse_feed(response.text)
        if year_from is None and year_to is None:
            return results
        filtered: list[SearchResult] = []
        for result in results:
            if result.year is None:
                continue
            if year_from is not None and result.year < year_from:
                continue
            if year_to is not None and result.year > year_to:
                continue
            filtered.append(result)
        return filtered

    def get_paper(self, identifier: str) -> SearchResult | None:
        cleaned = identifier.strip()
        if _DOI_RE.match(cleaned):
            params = {
                "search_query": f'all:"{cleaned}"',
                "start": 0,
                "max_results": 1,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            }
        elif _ARXIV_RE.match(cleaned):
            params = {"id_list": cleaned.split("v", 1)[0]}
        else:
            return None

        response = self._request(params)
        if response is None:
            return None
        try:
            response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            logger.debug("arXiv lookup failed: %s", exc)
            return None
        results = self._parse_feed(response.text)
        return results[0] if results else None
