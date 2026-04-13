"""Topic overview notes: emit digests, scaffold, and read overview markdown."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


OVERVIEW_FILENAME = "00_overview.md"
OVERVIEW_TEMPLATE = """---
type: topic-overview
cluster: {cluster_slug}
title: {cluster_title}
status: draft
---

# {cluster_title}

<!-- Generated template. Fill each section below. Keep the frontmatter. -->

## Definition

<!-- What is this topic? One paragraph, written for someone new to the field.
     Include the canonical definition(s), any disambiguation from adjacent areas. -->

## Why it matters

<!-- The motivation. What problem does this solve? Who cares, and why now?
     One short paragraph. -->

## Applications

<!-- Where is this used in practice? Bullet list of 3-6 concrete applications
     or use cases with one sentence of context each. -->

-
-
-

## Key sub-problems

<!-- The open questions the field is actively working on. Bullet list.
     Each bullet: the sub-problem + one sentence on why it's hard. -->

-
-
-

## Seed papers

<!-- The most foundational papers in this cluster, each with a one-sentence take.
     Pattern: `- [[<slug>|<short title>]] ({{year}}) - <what this paper contributes>`
     The AI fills this from the cluster's paper list. -->

-
-
-

## Further reading

<!-- Outside this vault - survey papers, textbooks, canonical blog posts. -->

-
"""


@dataclass
class PaperDigestEntry:
    slug: str
    title: str
    authors: list[str]
    year: int | None
    doi: str
    abstract: str


@dataclass
class TopicDigest:
    cluster_slug: str
    cluster_title: str
    paper_count: int
    papers: list[PaperDigestEntry] = field(default_factory=list)

    def to_markdown(self) -> str:
        """Render a single markdown blob an AI can read."""
        lines = [f"# {self.cluster_title}", "", f"{self.paper_count} papers.", ""]
        for paper in self.papers:
            lines.append(f"### {paper.title}")
            authors = ", ".join(paper.authors[:5])
            if len(paper.authors) > 5:
                authors += f" +{len(paper.authors) - 5} more"
            lines.append(f"*{authors}* - {paper.year or '????'} - {paper.doi or '(no DOI)'}")
            lines.append("")
            if paper.abstract:
                lines.append("> " + paper.abstract.replace("\n", "\n> "))
            else:
                lines.append("> (no abstract)")
            lines.append("")
        return "\n".join(lines)


def hub_cluster_dir(cfg, cluster_slug: str) -> Path:
    hub_root = getattr(cfg, "hub", None)
    if hub_root is None:
        root = getattr(cfg, "root", None)
        if root is None:
            raise AttributeError("config must define either 'hub' or 'root'")
        hub_root = Path(root) / "research_hub" / "hub"
    return Path(hub_root) / cluster_slug


def overview_path(cfg, cluster_slug: str) -> Path:
    return hub_cluster_dir(cfg, cluster_slug) / OVERVIEW_FILENAME


def get_topic_digest(cfg, cluster_slug: str) -> TopicDigest:
    """Build a digest of every paper note in the cluster."""
    from research_hub.clusters import ClusterRegistry

    registry = ClusterRegistry(cfg.clusters_file)
    cluster = registry.get(cluster_slug)
    if cluster is None:
        raise ValueError(f"unknown cluster: {cluster_slug}")

    cluster_dir = Path(cfg.raw) / cluster_slug
    if not cluster_dir.exists():
        return TopicDigest(cluster_slug=cluster_slug, cluster_title=cluster.name, paper_count=0)

    papers: list[PaperDigestEntry] = []
    for note_path in sorted(cluster_dir.glob("*.md")):
        if note_path.name in {OVERVIEW_FILENAME, "index.md"}:
            continue
        meta, abstract = _parse_note(note_path)
        year_text = meta.get("year", "")
        papers.append(
            PaperDigestEntry(
                slug=note_path.stem,
                title=meta.get("title", note_path.stem),
                authors=_split_authors(meta.get("authors", "")),
                year=int(year_text) if year_text.isdigit() else None,
                doi=meta.get("doi", ""),
                abstract=abstract,
            )
        )

    return TopicDigest(
        cluster_slug=cluster_slug,
        cluster_title=cluster.name,
        paper_count=len(papers),
        papers=papers,
    )


def scaffold_overview(cfg, cluster_slug: str, *, force: bool = False) -> Path:
    """Create the overview template for a cluster."""
    from research_hub.clusters import ClusterRegistry

    registry = ClusterRegistry(cfg.clusters_file)
    cluster = registry.get(cluster_slug)
    if cluster is None:
        raise ValueError(f"unknown cluster: {cluster_slug}")

    path = overview_path(cfg, cluster_slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        raise FileExistsError(f"overview already exists at {path}")
    path.write_text(
        OVERVIEW_TEMPLATE.format(cluster_slug=cluster_slug, cluster_title=cluster.name),
        encoding="utf-8",
    )
    return path


def read_overview(cfg, cluster_slug: str) -> str | None:
    """Return overview markdown or None if it does not exist."""
    path = overview_path(cfg, cluster_slug)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def _parse_note(path: Path) -> tuple[dict[str, str], str]:
    """Return note frontmatter plus abstract section text."""
    import re

    text = path.read_text(encoding="utf-8")
    meta: dict[str, str] = {}
    body = text
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            for line in text[4:end].splitlines():
                if ":" in line:
                    key, _, value = line.partition(":")
                    meta[key.strip()] = value.strip().strip('"')
            body = text[end + 5 :]

    match = re.search(r"^##\s+Abstract\s*\n(.*?)(?=^##\s|\Z)", body, re.MULTILINE | re.DOTALL)
    abstract = match.group(1).strip() if match else ""
    return meta, abstract


def _split_authors(authors_str: str) -> list[str]:
    if not authors_str:
        return []
    return [author.strip() for author in authors_str.replace(";", ",").split(",") if author.strip()]
