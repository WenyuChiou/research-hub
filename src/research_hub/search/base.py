"""Base types for search backends."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class SearchResult:
    """Normalized search result from any backend."""

    title: str
    doi: str = ""
    arxiv_id: str = ""
    abstract: str = ""
    year: int | None = None
    authors: list[str] = field(default_factory=list)
    venue: str = ""
    url: str = ""
    citation_count: int = 0
    pdf_url: str = ""
    source: str = ""
    confidence: float = 0.5
    found_in: list[str] = field(default_factory=list)
    doc_type: str = ""
    categories: list[str] = field(default_factory=list)
    publication_types: list[str] = field(default_factory=list)

    @classmethod
    def from_s2_json(cls, item: dict) -> "SearchResult":
        """Create a result from Semantic Scholar JSON."""
        authors = [
            author.get("name", "")
            for author in item.get("authors") or []
            if author.get("name")
        ]
        external_ids = item.get("externalIds") or {}
        pdf = item.get("openAccessPdf") or {}
        arxiv_id = external_ids.get("ArXiv", "") or external_ids.get("ARXIV", "") or ""
        if arxiv_id.lower().startswith("arxiv:"):
            arxiv_id = arxiv_id.split(":", 1)[1]
        if "v" in arxiv_id and arxiv_id.startswith(tuple(str(i) for i in range(10))):
            arxiv_id = arxiv_id.split("v", 1)[0]
        return cls(
            title=item.get("title") or "",
            doi=external_ids.get("DOI", "") or "",
            arxiv_id=arxiv_id,
            abstract=item.get("abstract") or "",
            year=item.get("year"),
            authors=authors,
            venue=item.get("venue") or "",
            url=item.get("url") or "",
            citation_count=item.get("citationCount", 0) or 0,
            pdf_url=pdf.get("url", "") or "",
            source="semantic-scholar",
            doc_type=item.get("publicationTypes", [""])[0] if item.get("publicationTypes") else "",
            publication_types=[
                str(pub_type).strip()
                for pub_type in (item.get("publicationTypes") or [])[:3]
                if str(pub_type).strip()
            ],
        )

    @property
    def dedup_key(self) -> str:
        """Stable key for merging across backends. DOI preferred, arxiv fallback."""
        from research_hub.utils.doi import normalize_doi

        if self.doi:
            return normalize_doi(self.doi)
        if self.arxiv_id:
            return f"arxiv:{self.arxiv_id}"
        return f"title:{self.title.lower().strip()}"


class SearchBackend(Protocol):
    """Protocol every backend implements."""

    name: str

    def search(
        self,
        query: str,
        *,
        limit: int = 20,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[SearchResult]:
        ...

    def get_paper(self, identifier: str) -> SearchResult | None:
        """Fetch a single paper by DOI or arXiv ID. May return None."""
        ...
