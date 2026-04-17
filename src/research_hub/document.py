"""Document base class for any source item in the vault.

Papers (academic, with DOI) inherit Document and add DOI/authors/journal/etc.
Other source kinds like PDFs from a folder, internal Word docs, web pages,
and meeting notes use Document directly with source_kind set accordingly.

Design constraint: this must not break existing paper notes. Read paths that
do not know about Document still see Paper-shaped frontmatter. Write paths can
choose Paper (rich) or Document (minimal).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import yaml


CANONICAL_SOURCE_KINDS: frozenset[str] = frozenset(
    {
        "paper",
        "pdf",
        "markdown",
        "docx",
        "txt",
        "url",
        "transcript",
    }
)


@dataclass
class Document:
    """Base class for any source item in the vault."""

    slug: str
    title: str
    source_kind: str
    topic_cluster: str | None = None
    ingested_at: str = ""
    ingestion_source: str = ""
    labels: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    raw_path: str | None = None
    summary: str = ""

    def __post_init__(self) -> None:
        if self.source_kind not in CANONICAL_SOURCE_KINDS:
            raise ValueError(
                f"source_kind={self.source_kind!r} invalid. "
                f"Must be one of: {sorted(CANONICAL_SOURCE_KINDS)}"
            )
        if not self.ingested_at:
            self.ingested_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def to_frontmatter(self) -> dict:
        """Return minimal frontmatter for non-paper documents."""

        frontmatter = {
            "title": self.title,
            "slug": self.slug,
            "source_kind": self.source_kind,
            "ingested_at": self.ingested_at,
            "ingestion_source": self.ingestion_source,
            "topic_cluster": self.topic_cluster or "",
            "labels": list(self.labels),
            "tags": list(self.tags),
        }
        if self.raw_path:
            frontmatter["raw_path"] = str(self.raw_path)
        if self.summary:
            frontmatter["summary"] = self.summary
        return frontmatter

    def to_markdown(self, body: str = "") -> str:
        """Render a note as YAML frontmatter followed by the body."""

        yaml_str = yaml.safe_dump(
            self.to_frontmatter(),
            allow_unicode=True,
            sort_keys=False,
        )
        return f"---\n{yaml_str}---\n\n{body}\n"


@dataclass
class Paper(Document):
    """Academic paper subclass with rich academic frontmatter."""

    doi: str = ""
    authors: list[dict] = field(default_factory=list)
    year: int | None = None
    journal: str = ""
    volume: str = ""
    issue: str = ""
    pages: str = ""
    abstract: str = ""
    key_findings: list[str] = field(default_factory=list)
    methodology: str = ""
    relevance: str = ""
    zotero_key: str = ""
    collections: list[str] = field(default_factory=list)
    cluster_queries: list[str] = field(default_factory=list)
    verified: bool | None = None
    verified_at: str = ""
    status: str = "unread"

    def __post_init__(self) -> None:
        if not self.source_kind:
            self.source_kind = "paper"
        elif self.source_kind != "paper":
            raise ValueError(f"Paper source_kind must be 'paper', got {self.source_kind!r}")
        super().__post_init__()

    def to_frontmatter(self) -> dict:
        """Emit the academic frontmatter shape used by paper notes."""

        authors_str = "; ".join(
            f"{author.get('lastName', '')}, {author.get('firstName', '')}".strip(", ")
            for author in self.authors
        )
        return {
            "title": self.title,
            "authors": authors_str,
            "year": self.year if self.year is not None else "",
            "journal": self.journal,
            "volume": self.volume,
            "issue": self.issue,
            "pages": self.pages,
            "doi": self.doi,
            "zotero-key": self.zotero_key,
            "collections": list(self.collections),
            "tags": list(self.tags),
            "ingested_at": self.ingested_at,
            "ingestion_source": self.ingestion_source,
            "topic_cluster": self.topic_cluster or "",
            "cluster_queries": list(self.cluster_queries),
            "verified": self.verified if self.verified is not None else "",
            "verified_at": self.verified_at,
            "status": self.status,
            "source_kind": "paper",
            "labels": list(self.labels),
        }


def parse_source_kind(frontmatter: dict) -> str:
    """Read source_kind, defaulting legacy notes to 'paper'."""

    source_kind = frontmatter.get("source_kind", "")
    if not source_kind or not isinstance(source_kind, str):
        return "paper"
    return source_kind.strip().lower()


__all__ = [
    "CANONICAL_SOURCE_KINDS",
    "Document",
    "Paper",
    "parse_source_kind",
]
