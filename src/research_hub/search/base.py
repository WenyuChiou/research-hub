"""Base types for search backends."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(init=False)
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
    # v0.68.5: bibliographic locator fields. Populated by openalex/crossref
    # when the API returns them; left "" by arxiv (preprints have no journal
    # volume/issue) and by semantic-scholar when its `journal` block is absent.
    # Required for complete citations (Author year. Title. Journal vol(issue):pp).
    volume: str = ""
    issue: str = ""
    pages: str = ""

    def __init__(
        self,
        title: str,
        doi: str = "",
        arxiv_id: str = "",
        abstract: str = "",
        abstract_source: str = "",
        year: int | None = None,
        metadata_year: int | None = None,
        authors: list[str] | None = None,
        venue: str = "",
        url: str = "",
        citation_count: int = 0,
        pdf_url: str = "",
        source: str = "",
        confidence: float = 0.5,
        found_in: list[str] | None = None,
        doc_type: str = "",
        categories: list[str] | None = None,
        publication_types: list[str] | None = None,
        volume: str = "",
        issue: str = "",
        pages: str = "",
    ) -> None:
        self.title = title
        self.doi = doi
        self.arxiv_id = arxiv_id
        self.abstract = abstract
        self.abstract_source = abstract_source or ""
        self.year = year
        self.metadata_year = metadata_year
        self.authors = list(authors or [])
        self.venue = venue
        self.url = url
        self.citation_count = citation_count
        self.pdf_url = pdf_url
        self.source = source
        self.confidence = confidence
        self.found_in = list(found_in or [])
        self.doc_type = doc_type
        self.categories = list(categories or [])
        self.publication_types = list(publication_types or [])
        self.volume = volume
        self.issue = issue
        self.pages = pages

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
        # v0.68.5: Semantic Scholar exposes journal locator fields under the
        # `journal` block. The block is optional and inconsistently populated;
        # fall back to "" when absent so downstream writers (Zotero, Obsidian)
        # see a real string rather than None.
        journal = item.get("journal") or {}
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
            volume=str(journal.get("volume") or ""),
            pages=str(journal.get("pages") or ""),
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
