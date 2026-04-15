"""Citation graph clustering for sub-topic split suggestions."""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "to",
        "for",
        "in",
        "on",
        "at",
        "with",
        "by",
        "from",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "this",
        "that",
        "these",
        "those",
        "can",
        "will",
        "shall",
        "may",
        "might",
        "using",
        "based",
        "new",
        "novel",
        "approach",
        "method",
        "study",
        "analysis",
        "model",
        "models",
        "paper",
        "research",
        "via",
        "towards",
        "through",
        "against",
        "between",
        "among",
        "into",
    }
)


@dataclass
class CommunityProposal:
    slug: str
    title: str
    member_slugs: list[str]
    shared_references: list[str]
    modularity_contribution: float


@dataclass
class SplitSuggestion:
    cluster_slug: str
    paper_count: int
    community_count: int
    modularity_score: float
    communities: list[CommunityProposal]
    coverage_fraction: float
    rate_limited: bool


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Return a minimal frontmatter mapping for simple key: value fields."""
    if not text.startswith("---\n"):
        return {}
    try:
        end = text.index("\n---\n", 4)
    except ValueError:
        return {}
    data: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def _normalize_doi(value: str) -> str:
    return value.strip().lower()


def _read_cluster_papers(cfg, cluster_slug: str) -> list[dict[str, Any]]:
    """Return paper metadata for every paper note in the cluster.

    Uses `vault.sync.list_cluster_notes` which identifies membership by the
    paper's `topic_cluster` frontmatter field (rglob over cfg.raw), not by
    directory name. This handles the common case where legacy notes live in
    a folder that doesn't match the cluster slug.
    """
    try:
        from research_hub.vault.sync import list_cluster_notes
    except Exception:
        list_cluster_notes = None  # type: ignore[assignment]

    notes: list[Path]
    if list_cluster_notes is not None:
        notes = list_cluster_notes(cluster_slug, Path(cfg.raw))
    else:
        cluster_dir = Path(cfg.raw) / cluster_slug
        notes = sorted(cluster_dir.glob("*.md")) if cluster_dir.exists() else []

    papers: list[dict[str, Any]] = []
    for note in notes:
        if note.name.startswith("00_") or "topics" in note.parts:
            continue
        try:
            frontmatter = _parse_frontmatter(note.read_text(encoding="utf-8"))
        except OSError as exc:
            logger.warning("skipping unreadable note %s: %s", note, exc)
            continue
        doi = _normalize_doi(str(frontmatter.get("doi", "") or ""))
        title = str(frontmatter.get("title", "") or note.stem).strip()
        papers.append({"slug": note.stem, "doi": doi, "title": title})
    return papers


def _cache_dir(cfg, cluster_slug: str) -> Path:
    path = Path(cfg.research_hub_dir) / "citation_cache" / cluster_slug
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load_cached_refs(cfg, cluster_slug: str, slug: str) -> list[str] | None:
    path = _cache_dir(cfg, cluster_slug) / f"{slug}.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(payload, list):
        return None
    return [_normalize_doi(str(item)) for item in payload if str(item).strip()]


def _save_cached_refs(cfg, cluster_slug: str, slug: str, refs: list[str]) -> None:
    path = _cache_dir(cfg, cluster_slug) / f"{slug}.json"
    path.write_text(json.dumps(refs, ensure_ascii=False, indent=2), encoding="utf-8")


def _fetch_references(cfg, cluster_slug: str, paper: dict[str, Any]) -> list[str]:
    """Get reference DOIs for a paper, using cache before Semantic Scholar."""
    slug = str(paper["slug"])
    cached = _load_cached_refs(cfg, cluster_slug, slug)
    if cached is not None:
        return cached

    doi = str(paper.get("doi", "") or "").strip()
    if not doi:
        return []

    try:
        from research_hub.citation_graph import CitationGraphClient

        refs = CitationGraphClient().get_references(doi)
        ref_dois: list[str] = []
        for ref in refs or []:
            ref_doi = _normalize_doi(getattr(ref, "doi", "") or "")
            if ref_doi:
                ref_dois.append(ref_doi)
        _save_cached_refs(cfg, cluster_slug, slug, ref_dois)
        return ref_dois
    except Exception as exc:
        logger.warning("citation fetch failed for %s: %s", slug, exc)
        return []


def build_intra_cluster_citation_graph(cfg, cluster_slug: str) -> "Any":
    """Build a graph where edge weights are shared-reference counts."""
    import networkx as nx

    papers = _read_cluster_papers(cfg, cluster_slug)
    graph = nx.Graph()
    if not papers:
        graph.graph["empty_citation_count"] = 0
        graph.graph["total_papers"] = 0
        return graph

    refs_by_slug: dict[str, set[str]] = {}
    empty_count = 0
    for paper in papers:
        refs = set(_fetch_references(cfg, cluster_slug, paper))
        refs_by_slug[paper["slug"]] = refs
        if not refs:
            empty_count += 1
        graph.add_node(paper["slug"], title=paper["title"], doi=paper.get("doi", ""))

    slugs = [paper["slug"] for paper in papers]
    for index, source in enumerate(slugs):
        for target in slugs[index + 1 :]:
            shared = sorted(refs_by_slug[source] & refs_by_slug[target])
            if shared:
                graph.add_edge(source, target, weight=len(shared), shared=shared)

    graph.graph["empty_citation_count"] = empty_count
    graph.graph["total_papers"] = len(papers)
    return graph


def _compute_subtopic_name(member_titles: list[str], all_titles: list[str]) -> tuple[str, str]:
    """Pick distinctive terms common inside a community and rarer outside."""

    def tokenize(value: str) -> list[str]:
        return [
            token
            for token in re.findall(r"\b[a-z][a-z\-]{2,}\b", value.lower())
            if token not in STOPWORDS
        ]

    member_counts: Counter[str] = Counter()
    for title in member_titles:
        member_counts.update(set(tokenize(title)))

    global_counts: Counter[str] = Counter()
    for title in all_titles:
        global_counts.update(set(tokenize(title)))

    scored: list[tuple[float, str]] = []
    total_members = max(1, len(member_titles))
    total_others = max(1, len(all_titles) - total_members)
    for term, member_count in member_counts.items():
        if member_count < 2:
            continue
        outside = global_counts[term] - member_count
        score = (member_count / total_members) - (outside / total_others)
        if score > 0:
            scored.append((score, term))
    scored.sort(key=lambda item: (-item[0], item[1]))

    top_terms = [term for _, term in scored[:3]]
    if not top_terms:
        return ("subtopic", "Subtopic")
    return ("-".join(top_terms), " ".join(term.capitalize() for term in top_terms))


def suggest_split(
    cfg,
    cluster_slug: str,
    *,
    min_community_size: int = 8,
    max_communities: int = 8,
) -> SplitSuggestion:
    """Run greedy modularity community detection on a cluster citation graph."""
    import networkx as nx
    from networkx.algorithms.community import greedy_modularity_communities

    graph = build_intra_cluster_citation_graph(cfg, cluster_slug)
    total_papers = int(graph.graph.get("total_papers", graph.number_of_nodes()))
    empty_count = int(graph.graph.get("empty_citation_count", 0))
    coverage_fraction = 1.0 - (empty_count / max(1, total_papers))
    rate_limited = coverage_fraction < 0.5

    if graph.number_of_edges() == 0:
        members = sorted(graph.nodes)
        communities = []
        if members:
            communities.append(
                CommunityProposal(
                    slug="cluster",
                    title=f"All {len(members)} papers (no citation structure detected)",
                    member_slugs=members,
                    shared_references=[],
                    modularity_contribution=0.0,
                )
            )
        return SplitSuggestion(
            cluster_slug=cluster_slug,
            paper_count=total_papers,
            community_count=len(communities),
            modularity_score=0.0,
            communities=communities,
            coverage_fraction=coverage_fraction,
            rate_limited=rate_limited,
        )

    raw_communities = list(greedy_modularity_communities(graph, weight="weight"))
    filtered = [community for community in raw_communities if len(community) >= min_community_size]
    if not filtered:
        filtered = raw_communities[:1]
    filtered = filtered[:max_communities]
    modularity = nx.algorithms.community.modularity(graph, raw_communities, weight="weight")

    title_by_slug = {slug: graph.nodes[slug].get("title", slug) for slug in graph.nodes}
    all_titles = list(title_by_slug.values())
    proposals: list[CommunityProposal] = []
    for community in filtered:
        members = sorted(community)
        member_titles = [title_by_slug.get(slug, slug) for slug in members]
        subtopic_slug, subtopic_title = _compute_subtopic_name(member_titles, all_titles)
        ref_counter: Counter[str] = Counter()
        for index, source in enumerate(members):
            for target in members[index + 1 :]:
                if graph.has_edge(source, target):
                    ref_counter.update(graph.edges[source, target].get("shared", []))
        proposals.append(
            CommunityProposal(
                slug=subtopic_slug,
                title=subtopic_title,
                member_slugs=members,
                shared_references=[doi for doi, _ in ref_counter.most_common(3)],
                modularity_contribution=0.0,
            )
        )

    return SplitSuggestion(
        cluster_slug=cluster_slug,
        paper_count=total_papers,
        community_count=len(proposals),
        modularity_score=float(modularity),
        communities=proposals,
        coverage_fraction=coverage_fraction,
        rate_limited=rate_limited,
    )


def render_split_suggestion_markdown(suggestion: SplitSuggestion) -> str:
    """Render a markdown report compatible with manual review + assignment apply."""
    assignments: dict[str, list[str]] = {}
    for community in suggestion.communities:
        for slug in community.member_slugs:
            assignments.setdefault(slug, []).append(community.slug)

    lines = [
        f"# Cluster split suggestion - {suggestion.cluster_slug}",
        "",
        f"**Papers analyzed:** {suggestion.paper_count}",
        f"**Communities proposed:** {suggestion.community_count}",
        f"**Modularity score:** {suggestion.modularity_score:.3f}",
        f"**Citation coverage:** {suggestion.coverage_fraction:.0%}",
    ]
    if suggestion.rate_limited:
        lines.extend(
            [
                "",
                "> **Warning:** citation data coverage below 50%. Results may be incomplete due to Semantic Scholar rate limiting. Rerun later to benefit from cached results.",
            ]
        )
    lines.extend(["", "## Proposed subtopics", ""])
    for index, community in enumerate(suggestion.communities, start=1):
        lines.append(f"### {index:02d}. {community.title} (`{community.slug}`)")
        lines.append("")
        lines.append(f"**Members:** {len(community.member_slugs)} papers")
        if community.shared_references:
            lines.append("**Top shared references:**")
            for ref in community.shared_references:
                lines.append(f"- `{ref}`")
        lines.append("")
        lines.append("**Papers:**")
        for slug in community.member_slugs:
            lines.append(f"- `{slug}`")
        lines.append("")
    lines.extend(
        [
            "## How to apply this suggestion",
            "",
            "1. Review the communities above. Rename subtopic slugs and titles as needed.",
            "2. Save the following assignments JSON:",
            "",
            "```json",
            json.dumps({"assignments": assignments}, indent=2, ensure_ascii=False),
            "```",
            "",
            f"3. Apply it: `research-hub topic assign apply --cluster {suggestion.cluster_slug} --assignments assignments.json`",
            f"4. Build subtopic notes: `research-hub topic build --cluster {suggestion.cluster_slug}`",
            "5. Regenerate dashboard: `research-hub dashboard`",
        ]
    )
    return "\n".join(lines)
