"""CiNii Research search backend.

CiNii Research is the National Institute of Informatics (NII) academic
search service for Japan. It indexes Japanese journals, conference
proceedings, theses, books, projects, and dataset records, the
canonical bibliography for Japanese research literature.

Free, no API key required. The OpenSearch endpoint at
https://cir.nii.ac.jp/opensearch/all returns Atom XML.
"""

from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET
from typing import Any

import requests

from research_hub.search.base import SearchResult

logger = logging.getLogger(__name__)

CINII_BASE = "https://cir.nii.ac.jp/opensearch/all"
_USER_AGENT = "research-hub/0.20.0"
_DEFAULT_TIMEOUT = 30
_DEFAULT_DELAY = 0.5

_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
    "prism": "http://prismstandard.org/namespaces/basic/2.0/",
    "cinii": "https://cir.nii.ac.jp/schema/1.0/",
}


class CiniiBackend:
    name = "cinii"

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
            "q": query,
            "format": "atom",
            "count": min(limit, 200),
            "sortorder": "0",
        }
        if year_from is not None:
            params["from"] = f"{year_from}-01-01"
        if year_to is not None:
            params["until"] = f"{year_to}-12-31"
        try:
            response = requests.get(
                CINII_BASE,
                params=params,
                headers={"User-Agent": _USER_AGENT, "Accept": "application/atom+xml"},
                timeout=self.timeout,
            )
        except requests.exceptions.RequestException as exc:
            logger.debug("CiNii search failed: %s", exc)
            return []
        if response.status_code != 200:
            return []
        try:
            root = ET.fromstring(response.text)
        except ET.ParseError as exc:
            logger.debug("CiNii XML parse failed: %s", exc)
            return []

        results: list[SearchResult] = []
        for entry in root.findall("atom:entry", _NS):
            result = self._parse_entry(entry)
            if result is not None:
                results.append(result)
        return results

    def get_paper(self, identifier: str) -> SearchResult | None:
        results = self.search(identifier.strip(), limit=1)
        return results[0] if results else None

    def _parse_entry(self, entry: ET.Element) -> SearchResult | None:
        title_el = entry.find("atom:title", _NS)
        title = (title_el.text or "").strip() if title_el is not None else ""
        if not title:
            return None

        authors: list[str] = []
        for author_el in entry.findall("atom:author", _NS):
            name_el = author_el.find("atom:name", _NS)
            if name_el is not None and name_el.text:
                authors.append(name_el.text.strip())

        year = None
        for date_path in ("prism:publicationDate", "dc:date", "atom:published"):
            date_el = entry.find(date_path, _NS)
            if date_el is not None and date_el.text:
                match = re.match(r"(\d{4})", date_el.text)
                if match:
                    year = int(match.group(1))
                    break

        venue = ""
        venue_el = entry.find("prism:publicationName", _NS)
        if venue_el is None:
            venue_el = entry.find("dc:publisher", _NS)
        if venue_el is not None and venue_el.text:
            venue = venue_el.text.strip()

        doi = ""
        for ident_el in entry.findall("dc:identifier", _NS):
            text = (ident_el.text or "").strip()
            if text.startswith("https://doi.org/"):
                doi = text[len("https://doi.org/") :].lower()
                break
            if text.lower().startswith("info:doi/"):
                doi = text[len("info:doi/") :].lower()
                break
        if not doi:
            doi_el = entry.find("prism:doi", _NS)
            if doi_el is not None and doi_el.text:
                doi = doi_el.text.strip().lower()

        url = ""
        for link_el in entry.findall("atom:link", _NS):
            if link_el.get("rel") in (None, "alternate"):
                url = link_el.get("href", "")
                if url:
                    break
        if not url:
            id_el = entry.find("atom:id", _NS)
            if id_el is not None and id_el.text:
                url = id_el.text.strip()

        abstract = ""
        summary_el = entry.find("atom:summary", _NS)
        if summary_el is not None and summary_el.text:
            abstract = summary_el.text.strip()

        doc_type = "journal-article"
        type_el = entry.find("dc:type", _NS)
        if type_el is not None and type_el.text:
            raw_type = type_el.text.strip().lower()
            if "thesis" in raw_type or "dissertation" in raw_type:
                doc_type = "thesis"
            elif "book" in raw_type:
                doc_type = "book"
            elif "conference" in raw_type or "proceeding" in raw_type:
                doc_type = "conference-paper"

        return SearchResult(
            title=title,
            doi=doi,
            arxiv_id="",
            abstract=abstract,
            year=year,
            authors=authors,
            venue=venue,
            url=url,
            citation_count=0,
            pdf_url="",
            source=self.name,
            doc_type=doc_type,
        )
