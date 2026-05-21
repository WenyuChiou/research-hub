"""Research gap analysis — intra-cluster and cross-cluster gap finder (F4a).

Reads paper summaries from a cluster's raw/ folder, builds a structured
digest, and emits an LLM prompt that asks for evidence-anchored gap analysis.
Results are written to hub/<cluster>/research-gaps.md.

Usage via CLI:
    research-hub paper gaps --cluster <slug>
    research-hub paper gaps --cluster A --compare B   (cross-cluster, Wave 5)
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_SECTION_RE = re.compile(
    r"^#{1,3}\s+(?P<header>.+?)\s*$",
    re.MULTILINE,
)

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)

_SECTION_NAMES_OF_INTEREST = {
    "summary",
    "key findings",
    "key finding",
    "methodology",
    "methods",
    "method",
    "abstract",
    "results",
    "conclusions",
    "conclusion",
    "findings",
}


def _read_frontmatter(text: str) -> dict:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}
    try:
        import yaml
        return yaml.safe_load(m.group(1)) or {}
    except Exception:
        return {}


def _extract_sections(text: str) -> dict[str, str]:
    """Extract named sections from a Markdown file.

    Returns {normalized_header: content} for headers matching
    ``_SECTION_NAMES_OF_INTEREST``. Content is trimmed to 500 chars to
    keep the digest token-efficient.
    """
    # Strip frontmatter
    body = _FRONTMATTER_RE.sub("", text, count=1).strip()

    sections: dict[str, str] = {}
    positions = [(m.start(), m.group("header")) for m in _SECTION_RE.finditer(body)]
    for i, (pos, header) in enumerate(positions):
        normalized = header.strip().lower()
        if not any(normalized == n or n in normalized for n in _SECTION_NAMES_OF_INTEREST):
            continue
        end = positions[i + 1][0] if i + 1 < len(positions) else len(body)
        # Skip the header line itself (find returns -1 on miss, index raises ValueError)
        nl_pos = body.find("\n", pos)
        content_start = nl_pos + 1 if nl_pos != -1 else end
        content = body[content_start:end].strip()
        sections[normalized] = content[:500]  # cap at 500 chars
    return sections


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@dataclass
class PaperDigestEntry:
    """Condensed view of one paper for gap analysis."""

    title: str
    doi: str = ""
    year: Optional[int] = None
    summary: str = ""
    methodology: str = ""
    key_findings: str = ""
    authors: list[str] = field(default_factory=list)


@dataclass
class ClusterDigest:
    """Structured digest of all papers in a cluster."""

    slug: str
    name: str = ""
    paper_count: int = 0
    papers: list[PaperDigestEntry] = field(default_factory=list)


@dataclass
class GapResult:
    """Result of writing gap analysis output."""

    written: bool
    research_gaps_path: Optional[Path] = None
    overview_updated: bool = False
    prompt_saved_path: Optional[Path] = None


def build_cluster_digest(cfg, slug: str) -> ClusterDigest:
    """Read all papers in a cluster folder and build a structured digest.

    Extracts title, year, DOI, summary, methodology, and key-findings from
    each paper's YAML frontmatter and Markdown section headers.

    Args:
        cfg: HubConfig (must have .raw Path attribute).
        slug: Cluster slug (used to find raw/<slug>/*.md).

    Returns:
        ClusterDigest with one PaperDigestEntry per non-overview paper.
    """
    raw_root = Path(cfg.raw)
    cluster_dir = raw_root / slug

    # Attempt to get cluster display name from the registry
    name = slug
    try:
        from research_hub.clusters import ClusterRegistry
        registry = ClusterRegistry(cfg.clusters_file)
        cluster = registry.get(slug)
        if cluster is not None:
            name = getattr(cluster, "name", slug) or slug
    except Exception:
        pass

    digest = ClusterDigest(slug=slug, name=name)

    if not cluster_dir.exists():
        logger.warning("Gap analysis: cluster dir not found: %s", cluster_dir)
        return digest

    paper_paths = [
        p for p in sorted(cluster_dir.glob("*.md"), key=lambda x: x.name)
        if not p.name.startswith("00_") and not p.name.startswith("_")
    ]
    digest.paper_count = len(paper_paths)

    for paper_path in paper_paths:
        try:
            text = paper_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        fm = _read_frontmatter(text)
        sections = _extract_sections(text)

        year_raw = fm.get("year") or fm.get("publication_year")
        year: Optional[int] = None
        if year_raw:
            try:
                year = int(str(year_raw))
            except (ValueError, TypeError):
                pass

        authors_raw = fm.get("authors") or fm.get("author") or []
        if isinstance(authors_raw, list):
            authors = [str(a).strip() for a in authors_raw if str(a).strip()]
        elif isinstance(authors_raw, str):
            authors = [a.strip() for a in authors_raw.split(";") if a.strip()]
        else:
            authors = []

        # Prefer explicit frontmatter fields; fall back to extracted sections
        summary = (
            str(fm.get("abstract") or "").strip()
            or sections.get("abstract", "")
            or sections.get("summary", "")
        )
        methodology = (
            sections.get("methodology", "")
            or sections.get("methods", "")
            or sections.get("method", "")
        )
        key_findings = (
            sections.get("key findings", "")
            or sections.get("key finding", "")
            or sections.get("findings", "")
            or sections.get("results", "")
            or sections.get("conclusions", "")
            or sections.get("conclusion", "")
        )

        entry = PaperDigestEntry(
            title=(str(fm.get("title") or "")).strip() or paper_path.stem,
            doi=(str(fm.get("doi") or "")).strip(),
            year=year,
            authors=authors,
            summary=summary[:500],
            methodology=methodology[:400],
            key_findings=key_findings[:400],
        )
        digest.papers.append(entry)

    return digest


def emit_gap_prompt(digest: ClusterDigest) -> str:
    """Generate an LLM prompt for evidence-anchored gap analysis.

    The prompt is findings-first: LLM must anchor each identified gap to
    specific papers that demonstrate its absence, not infer gaps from
    general knowledge. Output format is structured Markdown.

    Args:
        digest: ClusterDigest from build_cluster_digest().

    Returns:
        Multi-line string ready to pipe to an LLM CLI.
    """
    lines: list[str] = []
    lines.append("You are a rigorous research synthesis expert.")
    lines.append(
        "Your task: identify research gaps in the following literature cluster."
    )
    lines.append(
        "CRITICAL RULE: Every gap you identify must be evidence-anchored — "
        "cite which specific papers demonstrate the gap by their absence or by "
        "explicit limitations they state. Do NOT infer gaps from general domain knowledge."
    )
    lines.append("")
    lines.append(f"## Cluster: {digest.name} ({digest.slug})")
    lines.append(f"Total papers analyzed: {digest.paper_count}")
    lines.append("")
    lines.append("## Paper Summaries")
    lines.append("")

    for i, paper in enumerate(digest.papers, 1):
        year_str = f" ({paper.year})" if paper.year else ""
        doi_str = f" [DOI: {paper.doi}]" if paper.doi else ""
        lines.append(f"### Paper {i}: {paper.title}{year_str}{doi_str}")
        if paper.authors:
            lines.append(f"**Authors**: {', '.join(paper.authors[:3])}")
        if paper.summary:
            lines.append(f"**Summary**: {paper.summary}")
        if paper.methodology:
            lines.append(f"**Methodology**: {paper.methodology}")
        if paper.key_findings:
            lines.append(f"**Key Findings**: {paper.key_findings}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "Based ONLY on the papers above (do not use general knowledge), "
        "identify research gaps under these four categories. For each gap, "
        "cite the relevant paper number(s) that reveal the gap."
    )
    lines.append("")
    lines.append(
        "## Required Output Format (Markdown)\n"
        "\n"
        "### Methodological Gaps\n"
        "- [Gap description] (absent in Papers X, Y — e.g., 'no longitudinal designs')\n"
        "\n"
        "### Conceptual Gaps\n"
        "- [Gap description] (Papers X, Y assume but never test...)\n"
        "\n"
        "### Scope Gaps\n"
        "- [Population/geography/time horizon not covered] (Papers X, Y focus on...)\n"
        "\n"
        "### Actionable Research Directions\n"
        "Provide exactly 3-5 specific research directions in the format:\n"
        "'[Study X] using [Method Y] in [Context Z]'\n"
        "\n"
        "### Evidence Basis\n"
        "List all papers you referenced (title + number), confirming your "
        "gaps are derived ONLY from these papers.\n"
    )
    return "\n".join(lines)


def apply_gap_results(cfg, slug: str, gap_markdown: str) -> GapResult:
    """Write gap analysis output to hub/<cluster>/research-gaps.md.

    Also appends a brief summary section to the cluster's 00_overview.md
    under a '## Research Gaps' heading (creates the section if absent).

    Args:
        cfg: HubConfig (must have .root or .hub Path attribute).
        slug: Cluster slug.
        gap_markdown: LLM-produced Markdown gap analysis text.

    Returns:
        GapResult with paths and success flags.
    """
    # Resolve hub directory
    hub_root = _resolve_hub_root(cfg, slug)
    hub_root.mkdir(parents=True, exist_ok=True)

    gaps_path = hub_root / "research-gaps.md"
    header = f"# Research Gaps — {slug}\n\n"
    gaps_path.write_text(header + gap_markdown.strip() + "\n", encoding="utf-8")
    logger.info("Wrote research gaps to %s", gaps_path)

    result = GapResult(written=True, research_gaps_path=gaps_path)

    # Update 00_overview.md
    overview_path = hub_root / "00_overview.md"
    if overview_path.exists():
        overview_text = overview_path.read_text(encoding="utf-8")
        if "## Research Gaps" not in overview_text:
            # Extract just the first section heading from the gap output as a teaser
            first_section = ""
            for line in gap_markdown.splitlines():
                if line.startswith("### ") and "Actionable" in line:
                    break
                first_section += line + "\n"
                if len(first_section) > 600:
                    break
            teaser = (
                "\n\n## Research Gaps\n\n"
                f"*Full analysis: [[research-gaps]]*\n\n"
                f"{first_section.strip()[:400]}\n"
            )
            overview_path.write_text(overview_text.rstrip() + teaser, encoding="utf-8")
            result.overview_updated = True

    return result


def save_gap_prompt(cfg, slug: str, prompt: str) -> Path:
    """Save gap prompt to artifacts dir for manual LLM use.

    Returns the path where the prompt was saved.
    """
    artifacts_dir = cfg.research_hub_dir / "artifacts" / slug
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = artifacts_dir / "gap-analysis-prompt.md"
    prompt_path.write_text(prompt, encoding="utf-8")
    return prompt_path


# ---------------------------------------------------------------------------
# Cross-cluster gap analysis (F4b)
# ---------------------------------------------------------------------------


@dataclass
class CrossClusterGapResult:
    """Result of writing cross-cluster gap analysis output."""

    written: bool
    gap_path: Optional[Path] = None
    overview_a_updated: bool = False
    overview_b_updated: bool = False


def emit_cross_cluster_gap_prompt(
    digest_a: ClusterDigest, digest_b: ClusterDigest
) -> str:
    """Generate an LLM prompt for evidence-anchored cross-cluster gap analysis.

    The prompt asks the LLM to identify what each cluster covers that the other
    does not, what neither covers, and 3-5 specific bridging research directions
    — all anchored to specific papers from the provided digests.

    Args:
        digest_a: ClusterDigest for cluster A.
        digest_b: ClusterDigest for cluster B.

    Returns:
        Multi-line string ready to pipe to an LLM CLI.
    """
    lines: list[str] = []
    lines.append("You are a rigorous research synthesis expert.")
    lines.append(
        "Your task: identify the intersection space and bridging research directions "
        "between TWO literature clusters."
    )
    lines.append(
        "CRITICAL RULE: Every gap or bridge you identify must be evidence-anchored — "
        "cite which specific papers from each cluster demonstrate the gap by their absence "
        "or by explicit limitations they state. Do NOT infer gaps from general domain knowledge."
    )
    lines.append("")

    for label, digest in [("A", digest_a), ("B", digest_b)]:
        lines.append(f"## Cluster {label}: {digest.name} ({digest.slug})")
        lines.append(f"Total papers: {digest.paper_count}")
        lines.append("")
        lines.append(f"### Paper Summaries — Cluster {label}")
        lines.append("")
        for i, paper in enumerate(digest.papers, 1):
            year_str = f" ({paper.year})" if paper.year else ""
            doi_str = f" [DOI: {paper.doi}]" if paper.doi else ""
            lines.append(f"#### {label}{i}: {paper.title}{year_str}{doi_str}")
            if paper.authors:
                lines.append(f"**Authors**: {', '.join(paper.authors[:3])}")
            if paper.summary:
                lines.append(f"**Summary**: {paper.summary}")
            if paper.methodology:
                lines.append(f"**Methodology**: {paper.methodology}")
            if paper.key_findings:
                lines.append(f"**Key Findings**: {paper.key_findings}")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "Based ONLY on the papers above (do not use general knowledge), "
        "identify cross-cluster gaps and bridging opportunities. "
        "Cite paper codes (e.g. A1, B3) for every claim."
    )
    lines.append("")
    lines.append(
        "## Required Output Format (Markdown)\n"
        "\n"
        "### What Cluster A Covers That B Does Not\n"
        "- [description] (Papers A1, A2 address X; no equivalent found in Cluster B)\n"
        "\n"
        "### What Cluster B Covers That A Does Not\n"
        "- [description] (Papers B1, B2 address Y; no equivalent found in Cluster A)\n"
        "\n"
        "### Intersection Gaps (Neither Cluster Covers)\n"
        "- [topic or method absent from both] "
        "(implied by limitations stated in A1, B2, etc.)\n"
        "\n"
        "### Bridging Research Directions\n"
        "Provide exactly 3-5 specific directions that connect both clusters:\n"
        "'[Insight/method from Cluster A] × [Insight/method from Cluster B] "
        "→ [Concrete Research Direction]'\n"
        "\n"
        "### Evidence Basis\n"
        "List every paper you cited (title + code e.g. A1, B3), confirming your "
        "analysis is derived ONLY from these papers.\n"
    )
    return "\n".join(lines)


def cross_cluster_gap(
    cfg, slug_a: str, slug_b: str, gap_markdown: str
) -> CrossClusterGapResult:
    """Write cross-cluster gap analysis to hub/_cross-cluster/<A>-x-<B>-gaps.md.

    Also adds a ``## Cross-Cluster Analysis`` section with a wikilink to each
    cluster's ``00_overview.md`` (if the file exists and the section is absent).

    Args:
        cfg: HubConfig (must have .root or .hub Path attribute).
        slug_a: First cluster slug.
        slug_b: Second cluster slug.
        gap_markdown: LLM-produced Markdown cross-cluster gap analysis text.

    Returns:
        CrossClusterGapResult with paths and success flags.
    """
    cross_hub = _resolve_hub_root(cfg, "_cross-cluster")
    cross_hub.mkdir(parents=True, exist_ok=True)

    gap_filename = f"{slug_a}-x-{slug_b}-gaps.md"
    gap_path = cross_hub / gap_filename
    header = f"# Cross-Cluster Gaps — {slug_a} × {slug_b}\n\n"
    gap_path.write_text(header + gap_markdown.strip() + "\n", encoding="utf-8")
    logger.info("Wrote cross-cluster gaps to %s", gap_path)

    result = CrossClusterGapResult(written=True, gap_path=gap_path)

    # Add cross-reference wikilinks to each cluster's 00_overview.md
    wikilink_stem = gap_filename[:-3]  # strip .md
    for idx, (slug, other_slug) in enumerate(
        [(slug_a, slug_b), (slug_b, slug_a)]
    ):  # idx 0 → A, idx 1 → B
        overview_path = _resolve_hub_root(cfg, slug) / "00_overview.md"
        if not overview_path.exists():
            continue
        overview_text = overview_path.read_text(encoding="utf-8")
        cross_heading = "## Cross-Cluster Analysis"
        if cross_heading in overview_text:
            continue  # already present — do not duplicate
        link_line = (
            f"- [[_cross-cluster/{wikilink_stem}|{slug} × {other_slug} gaps]]"
        )
        overview_path.write_text(
            overview_text.rstrip() + f"\n\n{cross_heading}\n\n{link_line}\n",
            encoding="utf-8",
        )
        if idx == 0:
            result.overview_a_updated = True
        else:
            result.overview_b_updated = True

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_hub_root(cfg, slug: str) -> Path:
    """Resolve the hub/<slug>/ directory from cfg.

    Uses ``cfg.hub`` (the canonical hub root set by HubConfig) to match
    the path convention used by every other command in the codebase.
    Falls back to ``cfg.root / "hub"`` for lightweight test SimpleNamespace cfgs
    that lack a ``hub`` attribute.
    """
    if hasattr(cfg, "hub"):
        return Path(cfg.hub) / slug
    # Fallback for tests that pass a SimpleNamespace without hub attribute
    root = getattr(cfg, "root", None)
    if root is not None:
        return Path(root) / "hub" / slug
    return Path(cfg.raw).parent / "hub" / slug
