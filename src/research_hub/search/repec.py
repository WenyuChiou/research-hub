"""RePEc (Research Papers in Economics) search via OAI-PMH."""

from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET

import requests

from research_hub.search.base import SearchResult

logger = logging.getLogger(__name__)

REPEC_SEARCH_URL = "https://ideas.repec.org/cgi-bin/htsearch"
REPEC_OAI_BASE = "https://oai.repec.org/"
_USER_AGENT = "research-hub/0.17.0"
_DEFAULT_TIMEOUT = 30
_DEFAULT_DELAY = 0.5

_NS = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
}


class RepecBackend:
    name = "repec"

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
        handles = self._search_handles(query, limit=limit)
        results: list[SearchResult] = []
        for handle in handles:
            self._throttle()
            record = self._fetch_oai_record(handle)
            if record is None:
                continue
            if year_from is not None and (record.year is None or record.year < year_from):
                continue
            if year_to is not None and (record.year is None or record.year > year_to):
                continue
            results.append(record)
            if len(results) >= limit:
                break
        return results

    def get_paper(self, identifier: str) -> SearchResult | None:
        cleaned = identifier.strip()
        if cleaned.startswith("RePEc:") or ":" in cleaned:
            return self._fetch_oai_record(cleaned)
        results = self.search(cleaned, limit=1)
        return results[0] if results else None

    def _search_handles(self, query: str, limit: int) -> list[str]:
        self._throttle()
        try:
            response = requests.get(
                REPEC_SEARCH_URL,
                params={"q": query, "ul": "p"},
                headers={"User-Agent": _USER_AGENT},
                timeout=self.timeout,
            )
        except requests.exceptions.RequestException as exc:
            logger.debug("RePEc IDEAS search failed: %s", exc)
            return []
        if response.status_code != 200:
            return []
        handles: list[str] = []
        for match in re.finditer(r"/p/([a-z]+)/(\S+?)\.html", response.text):
            handles.append(f"RePEc:{match.group(1)}:{match.group(2)}")
            if len(handles) >= limit:
                break
        return handles

    def _fetch_oai_record(self, handle: str) -> SearchResult | None:
        try:
            response = requests.get(
                REPEC_OAI_BASE,
                params={
                    "verb": "GetRecord",
                    "identifier": f"oai:{handle}",
                    "metadataPrefix": "oai_dc",
                },
                headers={"User-Agent": _USER_AGENT},
                timeout=self.timeout,
            )
        except requests.exceptions.RequestException as exc:
            logger.debug("RePEc OAI fetch failed for %s: %s", handle, exc)
            return None
        if response.status_code != 200:
            return None
        try:
            root = ET.fromstring(response.text)
        except ET.ParseError as exc:
            logger.debug("RePEc XML parse failed for %s: %s", handle, exc)
            return None
        return self._parse_oai_record(root, handle)

    def _parse_oai_record(self, root: ET.Element, handle: str) -> SearchResult | None:
        record = root.find(".//oai_dc:dc", _NS)
        if record is None:
            return None

        title_el = record.find("dc:title", _NS)
        date_el = record.find("dc:date", _NS)
        venue_el = record.find("dc:source", _NS)
        type_el = record.find("dc:type", _NS)

        year = None
        if date_el is not None and date_el.text:
            match = re.match(r"(\d{4})", date_el.text)
            if match:
                year = int(match.group(1))

        doi = ""
        url = ""
        for ident in record.findall("dc:identifier", _NS):
            text = ident.text or ""
            if text.startswith("https://doi.org/"):
                doi = text[len("https://doi.org/") :].lower()
            elif text.startswith("http"):
                url = url or text

        doc_type = type_el.text if type_el is not None and type_el.text else "preprint"
        doc_type = doc_type.lower().replace(" ", "-")
        return SearchResult(
            title=(title_el.text or "").strip() if title_el is not None else "",
            doi=doi,
            arxiv_id="",
            abstract="",
            year=year,
            authors=[(el.text or "").strip() for el in record.findall("dc:creator", _NS) if (el.text or "").strip()],
            venue=venue_el.text or "" if venue_el is not None else "",
            url=url or f"https://ideas.repec.org/p/{handle.replace('RePEc:', '').replace(':', '/')}.html",
            citation_count=0,
            pdf_url="",
            source=self.name,
            doc_type=doc_type,
        )
