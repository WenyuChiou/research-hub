"""Cluster synthesis page generator.

Walk all papers in a topic cluster and write a single synthesis markdown
file summarizing the cluster: collated summaries, collated key findings,
methodology comparison, aggregated relevance questions, and a live
dataview reading queue.

This module is read-only on ``raw/`` notes. It only writes generated
pages under ``hub/clusters``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class ClusterPaper:
    """A parsed paper note with the fields needed for synthesis output."""

    slug: str
    title: str
    authors: str = ""
    year: str = ""
    journal: str = ""
    doi: str = ""
    status: str = "unread"
    tags: list[str] = field(default_factory=list)
    summary: str = ""
    key_findings: list[str] = field(default_factory=list)
    methodology: str = ""
    relevance: str = ""
    raw_text: str = ""


def _extract_section(text: str, header: str) -> str:
    """Return the body of a ``## <header>`` section until the next heading."""

    pattern = re.compile(
        rf"^##\s+{re.escape(header)}\s*\n(.*?)(?=\n##\s|\Z)",
        re.DOTALL | re.MULTILINE,
    )
    match = pattern.search(text)
    if not match:
        return ""
    return match.group(1).strip()


def _extract_bullets(section_text: str) -> list[str]:
    """Extract markdown bullet items from a section body."""

    bullets: list[str] = []
    for line in section_text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("- "):
            bullets.append(stripped[2:].strip())
    return bullets


def _parse_frontmatter(frontmatter: str) -> dict[str, object]:
    """Parse YAML frontmatter into a mapping."""

    data = yaml.safe_load(frontmatter) or {}
    if isinstance(data, dict):
        return data
    return {}


def parse_cluster_paper(path: Path) -> ClusterPaper | None:
    """Read a paper note and return synthesis-ready fields."""

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    if not text.startswith("---"):
        return None

    match = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.DOTALL)
    if not match:
        return None

    frontmatter = _parse_frontmatter(match.group(1))
    body = match.group(2)

    tags = frontmatter.get("tags", [])
    if not isinstance(tags, list):
        tags = []

    return ClusterPaper(
        slug=path.stem,
        title=str(frontmatter.get("title") or path.stem),
        authors=str(frontmatter.get("authors") or ""),
        year=str(frontmatter.get("year") or ""),
        journal=str(frontmatter.get("journal") or ""),
        doi=str(frontmatter.get("doi") or ""),
        status=str(frontmatter.get("status") or "unread"),
        tags=[str(tag) for tag in tags],
        summary=_extract_section(body, "Summary"),
        key_findings=_extract_bullets(_extract_section(body, "Key Findings")),
        methodology=_extract_section(body, "Methodology"),
        relevance=_extract_section(body, "Relevance"),
        raw_text=body,
    )


def _first_sentence(text: str) -> str:
    """Return the first sentence, capped for table readability."""

    stripped = " ".join(text.split())
    if not stripped:
        return ""
    match = re.search(r"(.+?[.!?])(?:\s|$)", stripped)
    if match:
        return match.group(1)[:150]
    return stripped[:150]


def _author_short(authors: str) -> str:
    """Convert author strings into a short citation-style label."""

    if not authors:
        return "Unknown"
    parts = [part.strip() for part in authors.split(";") if part.strip()]
    if not parts:
        return "Unknown"
    last_names = [part.split(",")[0].strip() for part in parts]
    if len(last_names) == 1:
        return last_names[0]
    if len(last_names) == 2:
        return f"{last_names[0]} & {last_names[1]}"
    return f"{last_names[0]} et al."


def _llm_from_text(paper: ClusterPaper) -> str:
    """Infer a likely LLM reference from tags and note text."""

    combined = " ".join(paper.tags + [paper.methodology, paper.summary, paper.relevance]).lower()
    for name in ("gpt-4", "gpt-3.5", "claude", "llama", "gemini", "mistral", "qwen"):
        if name in combined:
            return name
    if "llm" in combined or "large language model" in combined:
        return "LLM (unspecified)"
    return ""


def _year_sort_value(year: str) -> tuple[int, str]:
    """Provide a deterministic descending sort key for years."""

    if year.isdigit():
        return (1, year)
    return (0, year)


def build_synthesis_markdown(
    cluster_slug: str,
    cluster_name: str,
    first_query: str,
    papers: list[ClusterPaper],
) -> str:
    """Render the cluster synthesis page as markdown."""

    sorted_papers = sorted(
        papers,
        key=lambda paper: (_year_sort_value(paper.year), paper.slug),
        reverse=True,
    )

    by_year: dict[str, int] = {}
    for paper in sorted_papers:
        year = paper.year or "n.d."
        by_year[year] = by_year.get(year, 0) + 1
    year_line = " | ".join(
        f"{year}: {count}" for year, count in sorted(by_year.items(), key=lambda item: item[0], reverse=True)
    )

    lines = [
        "---",
        "type: cluster-synthesis",
        f"cluster: {cluster_slug}",
        f"papers: {len(sorted_papers)}",
        "---",
        "",
        f"# {cluster_name} - Synthesis",
        "",
        f"**First query:** {first_query}",
        f"**Papers in cluster:** {len(sorted_papers)}",
        f"**By year:** {year_line or 'n.d.: 0'}",
        "",
        (
            f"> Auto-generated by `research-hub synthesize --cluster {cluster_slug}`. "
            "Regenerate after new ingestions to refresh the collated content."
        ),
        "",
        "## Collated Summaries",
        "",
    ]

    for paper in sorted_papers:
        lines.append(f"### {_author_short(paper.authors)} ({paper.year or 'n.d.'}) - {paper.title}")
        lines.append("")
        lines.append(paper.summary or "*(no summary recorded yet)*")
        lines.append("")
        lines.append(f"Source note: [[{paper.slug}]]")
        lines.append("")

    lines.extend(["## Collated Key Findings", ""])
    for paper in sorted_papers:
        lines.append(f"### {_author_short(paper.authors)} ({paper.year or 'n.d.'}) - {paper.title}")
        lines.append("")
        if paper.key_findings:
            for finding in paper.key_findings:
                lines.append(f"- {finding}")
        else:
            lines.append("*(no key findings recorded yet)*")
        lines.append("")

    lines.extend(
        [
            "## Methodology Comparison",
            "",
            "| Paper | Method | LLM | Status |",
            "|---|---|---|---|",
        ]
    )
    for paper in sorted_papers:
        method_short = _first_sentence(paper.methodology) or "n/a"
        llm = _llm_from_text(paper) or "n/a"
        link_label = f"{_author_short(paper.authors)} ({paper.year or 'n.d.'})"
        lines.append(
            f"| [[{paper.slug}|{link_label}]] | {method_short} | {llm} | {paper.status} |"
        )
    lines.append("")

    lines.extend(["## Open Questions / Relevance", ""])
    any_relevance = False
    for paper in sorted_papers:
        if not paper.relevance:
            continue
        any_relevance = True
        lines.append(
            f"- **{_author_short(paper.authors)} ({paper.year or 'n.d.'}):** "
            f"{' '.join(paper.relevance.split())[:300]}"
        )
    if not any_relevance:
        lines.append("*(no relevance notes recorded yet)*")
    lines.extend(["", "## Reading Queue (live)", ""])

    lines.extend(
        [
            "```dataview",
            "TABLE year, authors, status, citation-count",
            'FROM "raw"',
            f'WHERE topic_cluster = "{cluster_slug}" AND status = "unread"',
            "SORT year DESC",
            "LIMIT 15",
            "```",
            "",
            "## Deep-read (active thinking)",
            "",
            "```dataview",
            "TABLE year, authors, verified",
            'FROM "raw"',
            f'WHERE topic_cluster = "{cluster_slug}" AND (status = "deep-read" OR status = "cited")',
            "SORT year DESC",
            "```",
            "",
        ]
    )

    return "\n".join(lines)


def _collect_cluster_papers(
    cluster_slug: str,
    raw_dir: Path,
) -> list[ClusterPaper]:
    """Find all notes belonging to a cluster.

    A note belongs to a cluster if EITHER:
      (a) it lives under `raw/<cluster_slug>/` (new papers ingested by
          v0.3.x into a dedicated cluster sub-folder), OR
      (b) its YAML frontmatter has `topic_cluster: <cluster_slug>`
          regardless of which sub-folder it lives in (legacy notes that
          were dedup-caught and patched by v0.3.1+).

    This dual-mode lookup is required because the dedup path never
    moves existing files; it only annotates their YAML. Without (b)
    a synthesis would miss every dedup-hit paper.
    """
    papers: list[ClusterPaper] = []
    seen_paths: set[Path] = set()

    cluster_folder = raw_dir / cluster_slug
    if cluster_folder.exists():
        for md_path in sorted(cluster_folder.rglob("*.md")):
            if md_path in seen_paths:
                continue
            paper = parse_cluster_paper(md_path)
            if paper is not None:
                papers.append(paper)
                seen_paths.add(md_path)

    if raw_dir.exists():
        for md_path in sorted(raw_dir.rglob("*.md")):
            if md_path in seen_paths:
                continue
            paper = parse_cluster_paper(md_path)
            if paper is None:
                continue
            if _note_topic_cluster(md_path) != cluster_slug:
                continue
            papers.append(paper)
            seen_paths.add(md_path)

    return papers


def _note_topic_cluster(md_path: Path) -> str:
    """Fast-path read of the `topic_cluster` field for filtering."""
    try:
        text = md_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    if end < 0:
        return ""
    import re as _re
    match = _re.search(
        r'^topic_cluster:\s*[\'"]?([^\'"\n]*)[\'"]?',
        text[3:end],
        _re.MULTILINE,
    )
    return match.group(1).strip() if match else ""


def synthesize_cluster(
    cluster_slug: str,
    cluster_name: str,
    first_query: str,
    raw_dir: Path,
    hub_dir: Path,
) -> Path:
    """Write a synthesis page for a single cluster.

    Collects papers by both folder location (raw/<slug>/) and YAML
    `topic_cluster:` field so that dedup-hit legacy notes are included
    even when they still live in their original sub-folder.
    """
    papers = _collect_cluster_papers(cluster_slug, raw_dir)
    if not papers:
        raise FileNotFoundError(
            f"No papers found for cluster '{cluster_slug}' in {raw_dir} "
            "(checked both raw/<slug>/ and YAML topic_cluster field)"
        )

    markdown = build_synthesis_markdown(cluster_slug, cluster_name, first_query, papers)
    out_dir = hub_dir / "clusters"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{cluster_slug}-synthesis.md"
    out_path.write_text(markdown, encoding="utf-8")
    return out_path


def synthesize_all_clusters(raw_dir: Path, hub_dir: Path, clusters_file: Path) -> list[Path]:
    """Write synthesis pages for every cluster defined in the registry."""

    from research_hub.clusters import ClusterRegistry

    registry = ClusterRegistry(clusters_file)
    outputs: list[Path] = []
    for cluster in registry.list():
        try:
            outputs.append(
                synthesize_cluster(
                    cluster.slug,
                    cluster.name,
                    cluster.first_query,
                    raw_dir,
                    hub_dir,
                )
            )
        except FileNotFoundError:
            continue
    return outputs
