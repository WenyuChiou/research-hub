"""Citation graph exploration via Semantic Scholar API.

Wraps the /paper/{id}/references and /paper/{id}/citations endpoints
to let researchers explore which papers cite a given paper, and which
papers it cites.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

import requests

_S2_BASE = "https://api.semanticscholar.org/graph/v1"
_DEFAULT_FIELDS = "title,year,authors,externalIds,venue,citationCount,url,openAccessPdf"
_DEFAULT_TIMEOUT = 10
_DEFAULT_THROTTLE = 3.0


@dataclass
class CitationNode:
    """A paper in a citation relationship."""

    paper_id: str
    title: str
    doi: str = ""
    year: int | None = None
    authors: list[str] = field(default_factory=list)
    venue: str = ""
    citation_count: int = 0
    url: str = ""
    pdf_url: str = ""

    @classmethod
    def from_s2_json(cls, item: dict) -> CitationNode:
        """Build from a Semantic Scholar paper object."""
        paper = item.get("citingPaper") or item.get("citedPaper") or item
        external = paper.get("externalIds") or {}
        authors = [author.get("name", "") for author in paper.get("authors") or [] if author.get("name")]
        pdf = paper.get("openAccessPdf") or {}
        return cls(
            paper_id=paper.get("paperId", "") or "",
            title=paper.get("title", "") or "",
            doi=external.get("DOI", "") or "",
            year=paper.get("year"),
            authors=authors,
            venue=paper.get("venue", "") or "",
            citation_count=paper.get("citationCount", 0) or 0,
            url=paper.get("url", "") or "",
            pdf_url=pdf.get("url", "") or "",
        )


class CitationGraphClient:
    """Thin wrapper around Semantic Scholar citation endpoints."""

    def __init__(self, delay: float = _DEFAULT_THROTTLE, timeout: int = _DEFAULT_TIMEOUT) -> None:
        self.delay = delay
        self.timeout = timeout
        self._last_request: float | None = None

    def _throttle(self) -> None:
        now = time.time()
        if self._last_request is not None:
            elapsed = now - self._last_request
            if elapsed < self.delay:
                time.sleep(self.delay - elapsed)
        self._last_request = time.time()

    def _normalize_id(self, identifier: str) -> str:
        """Convert DOI / arXiv / S2 ID into the format Semantic Scholar expects."""
        normalized = identifier.strip()
        if normalized.upper().startswith(
            ("DOI:", "ARXIV:", "MAG:", "PMID:", "PMCID:", "URL:", "CORPUSID:")
        ):
            return normalized
        if normalized.startswith("10."):
            return f"DOI:{normalized}"
        if re.match(r"^\d{4}\.\d{4,5}(v\d+)?$", normalized):
            return f"ARXIV:{normalized}"
        return normalized

    def _request(self, identifier: str, edge: str, limit: int) -> list[CitationNode]:
        self._throttle()
        url = f"{_S2_BASE}/paper/{self._normalize_id(identifier)}/{edge}"
        response = requests.get(
            url,
            params={"fields": _DEFAULT_FIELDS, "limit": min(limit, 1000)},
            timeout=self.timeout,
        )
        if response.status_code == 429:
            time.sleep(self.delay * 2)
            return []
        if response.status_code == 404:
            return []
        response.raise_for_status()
        data = response.json().get("data", [])
        return [CitationNode.from_s2_json(item) for item in data]

    def get_references(self, identifier: str, limit: int = 50) -> list[CitationNode]:
        """Return papers that the given paper cites."""
        return self._request(identifier, "references", limit)

    def get_citations(self, identifier: str, limit: int = 50) -> list[CitationNode]:
        """Return papers that cite the given paper."""
        return self._request(identifier, "citations", limit)
