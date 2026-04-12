"""Proactive integration suggestions for new papers."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from research_hub.clusters import Cluster, ClusterRegistry, score_cluster_match, slugify
from research_hub.dedup import DedupHit, DedupIndex, normalize_doi, normalize_title
from research_hub.vault.link_updater import parse_frontmatter


@dataclass
class PaperInput:
    """Minimal paper metadata needed to score suggestions."""

    title: str
    doi: str = ""
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str = ""
    abstract: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass
class ClusterSuggestion:
    """A ranked cluster suggestion for a paper."""

    cluster_slug: str
    cluster_name: str
    score: float
    reasons: list[str]


@dataclass
class RelatedPaper:
    """A ranked related-paper suggestion."""

    doi: str
    title: str
    source: str
    location: str
    score: float
    reasons: list[str]


@dataclass
class _HitMeta:
    """Expanded metadata for scoring a dedup hit."""

    hit: DedupHit
    doi: str
    title: str
    tags: set[str] = field(default_factory=set)
    authors: list[str] = field(default_factory=list)
    venue: str = ""
    topic_cluster: str = ""


_W_SEED_KEYWORDS = 30.0
_W_TAG_OVERLAP = 30.0
_W_AUTHOR_SURNAME = 20.0
_W_VENUE = 10.0
_W_TITLE_KEYWORDS = 10.0


def suggest_cluster_for_paper(
    paper: PaperInput,
    registry: ClusterRegistry,
    dedup: DedupIndex,
    top_n: int = 3,
) -> list[ClusterSuggestion]:
    """Rank existing clusters by how well they fit a paper."""
    if not registry.clusters:
        return []

    paper_tags = _normalize_tags(paper.tags)
    paper_title_tokens = _title_tokens(paper.title)
    paper_query_tokens = paper_title_tokens | _title_tokens(" ".join(paper.tags))
    paper_surnames = _author_surnames(paper.authors)
    paper_venue = _normalize_text(paper.venue)
    cluster_members = _cluster_members(dedup)
    suggestions: list[ClusterSuggestion] = []

    for cluster in sorted(registry.clusters.values(), key=lambda item: item.slug):
        members = cluster_members.get(cluster.slug, [])
        member_tags = set().union(*(member.tags for member in members)) if members else set()
        member_surnames = set().union(*(_author_surnames(member.authors) for member in members)) if members else set()
        member_venues = {_normalize_text(member.venue) for member in members if _normalize_text(member.venue)}

        seed_overlap = score_cluster_match(paper_query_tokens, cluster)
        seed_score = _scaled_score(seed_overlap, min(len(cluster.seed_keywords), len(paper_query_tokens)), _W_SEED_KEYWORDS)

        shared_tags = sorted(paper_tags & member_tags)
        tag_score = _scaled_score(len(shared_tags), min(len(paper_tags), len(member_tags)), _W_TAG_OVERLAP)

        shared_surnames = sorted(paper_surnames & member_surnames)
        author_score = _scaled_score(
            len(shared_surnames),
            min(len(paper_surnames), len(member_surnames)),
            _W_AUTHOR_SURNAME,
        )

        venue_score = _W_VENUE if paper_venue and paper_venue in member_venues else 0.0

        best_title_overlap = 0
        best_title_tokens: set[str] = set()
        for member in members:
            member_title_tokens = _title_tokens(member.title)
            overlap_tokens = paper_title_tokens & member_title_tokens
            overlap = len(overlap_tokens)
            if overlap > best_title_overlap:
                best_title_overlap = overlap
                best_title_tokens = overlap_tokens
        title_score = _scaled_score(
            best_title_overlap,
            min(len(paper_title_tokens), max((len(_title_tokens(member.title)) for member in members), default=0)),
            _W_TITLE_KEYWORDS,
        )

        total_score = round(seed_score + tag_score + author_score + venue_score + title_score, 1)
        reasons = _cluster_reasons(
            cluster=cluster,
            seed_overlap_tokens=sorted(paper_query_tokens & set(cluster.seed_keywords)),
            shared_tags=shared_tags,
            shared_surnames=shared_surnames,
            venue_match=bool(venue_score),
            venue=paper.venue,
            best_title_tokens=sorted(best_title_tokens),
        )
        if total_score > 0 or reasons:
            suggestions.append(
                ClusterSuggestion(
                    cluster_slug=cluster.slug,
                    cluster_name=cluster.name,
                    score=total_score,
                    reasons=reasons or ["title overlap scored low but non-zero context was found"],
                )
            )

    suggestions.sort(key=lambda item: (-item.score, item.cluster_slug))
    return suggestions[:top_n]


def suggest_related_papers(
    new_paper: PaperInput,
    dedup: DedupIndex,
    registry: ClusterRegistry,
    top_n: int = 5,
) -> list[RelatedPaper]:
    """Find vault papers similar to a new paper."""
    new_doi = normalize_doi(new_paper.doi)
    new_title = normalize_title(new_paper.title)
    new_tags = _normalize_tags(new_paper.tags)
    new_surnames = _author_surnames(new_paper.authors)
    new_venue = _normalize_text(new_paper.venue)
    new_title_tokens = _title_tokens(new_paper.title)
    cluster_hits = suggest_cluster_for_paper(new_paper, registry, dedup, top_n=1)
    target_cluster = cluster_hits[0].cluster_slug if cluster_hits and cluster_hits[0].score > 0 else ""

    related: list[RelatedPaper] = []
    for hit in _iter_unique_hits(dedup):
        hit_doi = normalize_doi(hit.doi)
        hit_title = normalize_title(hit.title)
        if (new_doi and hit_doi == new_doi) or (new_title and hit_title == new_title):
            continue

        meta = _load_hit_meta(hit)
        shared_tags = sorted(new_tags & meta.tags)
        tag_score = _scaled_score(len(shared_tags), min(len(new_tags), len(meta.tags)), _W_TAG_OVERLAP)

        same_cluster = bool(target_cluster and meta.topic_cluster and meta.topic_cluster == target_cluster)
        cluster_score = _W_TAG_OVERLAP if same_cluster else 0.0

        shared_surnames = sorted(new_surnames & _author_surnames(meta.authors))
        author_score = _scaled_score(
            len(shared_surnames),
            min(len(new_surnames), len(_author_surnames(meta.authors))),
            _W_AUTHOR_SURNAME,
        )

        venue_score = _W_VENUE if new_venue and meta.venue and _normalize_text(meta.venue) == new_venue else 0.0

        overlap_tokens = sorted(new_title_tokens & _title_tokens(meta.title))
        title_score = _scaled_score(
            len(overlap_tokens),
            min(len(new_title_tokens), len(_title_tokens(meta.title))),
            _W_TITLE_KEYWORDS,
        )

        score = round(tag_score + cluster_score + author_score + venue_score + title_score, 1)
        reasons = _related_reasons(
            shared_tags=shared_tags,
            same_cluster=same_cluster,
            shared_surnames=shared_surnames,
            venue_match=bool(venue_score),
            venue=meta.venue or new_paper.venue,
            overlap_tokens=overlap_tokens,
        )
        if score > 0 or reasons:
            related.append(
                RelatedPaper(
                    doi=meta.doi,
                    title=meta.title,
                    source=meta.hit.source,
                    location=meta.hit.zotero_key or meta.hit.obsidian_path or "",
                    score=score,
                    reasons=reasons or ["weak metadata match"],
                )
            )

    related.sort(key=lambda item: (-item.score, item.doi or item.title.lower()))
    return related[:top_n]


def _cluster_members(dedup: DedupIndex) -> dict[str, list[_HitMeta]]:
    members: dict[str, list[_HitMeta]] = {}
    for hit in _iter_unique_hits(dedup):
        meta = _load_hit_meta(hit)
        if meta.topic_cluster:
            members.setdefault(meta.topic_cluster, []).append(meta)
    return members


def _iter_unique_hits(dedup: DedupIndex):
    seen: set[tuple[str, str, str, str | None, str | None]] = set()
    for mapping in (dedup.doi_to_hits, dedup.title_to_hits):
        for hits in mapping.values():
            for hit in hits:
                marker = (
                    hit.source,
                    normalize_doi(hit.doi),
                    normalize_title(hit.title),
                    hit.zotero_key,
                    hit.obsidian_path,
                )
                if marker in seen:
                    continue
                seen.add(marker)
                yield hit


def _load_hit_meta(hit: DedupHit) -> _HitMeta:
    meta = _HitMeta(
        hit=hit,
        doi=hit.doi,
        title=hit.title,
    )
    if hit.source != "obsidian" or not hit.obsidian_path:
        return meta

    path = Path(hit.obsidian_path)
    note_meta = parse_frontmatter(path)
    if note_meta:
        meta.title = note_meta.title or meta.title
        meta.tags = _normalize_tags(note_meta.tags)
        meta.topic_cluster = note_meta.topic_cluster

    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return meta

    frontmatter = _frontmatter_block(text)
    if not frontmatter:
        return meta

    title_match = re.search(r'^title:\s*"([^"]+)"', frontmatter, re.MULTILINE)
    if title_match:
        meta.title = title_match.group(1)
    doi_match = re.search(r'^doi:\s*"([^"]*)"', frontmatter, re.MULTILINE)
    if doi_match:
        meta.doi = doi_match.group(1)
    authors_match = re.search(r"^authors:\s*\[(.*?)\]", frontmatter, re.MULTILINE | re.DOTALL)
    if authors_match:
        meta.authors = [
            author.strip().strip('"').strip("'")
            for author in authors_match.group(1).split(",")
            if author.strip()
        ]
    venue_match = re.search(r'^(?:journal|venue):\s*"([^"]*)"', frontmatter, re.MULTILINE)
    if venue_match:
        meta.venue = venue_match.group(1)
    return meta


def _frontmatter_block(text: str) -> str:
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    if end < 0:
        return ""
    return text[3:end]


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", normalized.strip().lower())


def _normalize_tags(tags: list[str]) -> set[str]:
    return {_normalize_text(tag) for tag in tags if _normalize_text(tag)}


def _author_surnames(authors: list[str]) -> set[str]:
    surnames = set()
    for author in authors:
        parts = [part for part in (author or "").split() if part]
        if parts:
            surnames.add(_normalize_text(parts[-1]))
    return {surname for surname in surnames if surname}


def _title_tokens(title: str) -> set[str]:
    return {token for token in slugify(title).split("-") if len(token) > 2}


def _scaled_score(overlap: int, denominator: int, weight: float) -> float:
    if overlap <= 0 or denominator <= 0:
        return 0.0
    return min(overlap / denominator, 1.0) * weight


def _cluster_reasons(
    *,
    cluster: Cluster,
    seed_overlap_tokens: list[str],
    shared_tags: list[str],
    shared_surnames: list[str],
    venue_match: bool,
    venue: str,
    best_title_tokens: list[str],
) -> list[str]:
    reasons: list[str] = []
    if seed_overlap_tokens:
        reasons.append(f"matches seed keyword '{seed_overlap_tokens[0]}'")
    if shared_tags:
        reasons.append(f"shares {len(shared_tags)} tags with cluster members")
    if shared_surnames:
        reasons.append(f"shared author: {shared_surnames[0].title()}")
    elif venue_match and venue:
        reasons.append(f"venue: {venue}")
    elif best_title_tokens:
        reasons.append(f"title overlap: {len(best_title_tokens)}")
    if len(reasons) < 3 and venue_match and venue and f"venue: {venue}" not in reasons:
        reasons.append(f"venue: {venue}")
    if len(reasons) < 3 and best_title_tokens:
        reasons.append(f"title overlap: {len(best_title_tokens)}")
    if not reasons and cluster.seed_keywords:
        reasons.append(f"seed keywords available: {cluster.seed_keywords[0]}")
    return reasons[:3]


def _related_reasons(
    *,
    shared_tags: list[str],
    same_cluster: bool,
    shared_surnames: list[str],
    venue_match: bool,
    venue: str,
    overlap_tokens: list[str],
) -> list[str]:
    reasons: list[str] = []
    if same_cluster:
        reasons.append("same cluster")
    if shared_tags:
        reasons.append(f"shares {len(shared_tags)} tags")
    if shared_surnames:
        reasons.append(f"shared author: {shared_surnames[0].title()}")
    elif venue_match and venue:
        reasons.append(f"shared venue: {venue}")
    elif overlap_tokens:
        reasons.append(f"title overlap: {len(overlap_tokens)}")
    if len(reasons) < 3 and venue_match and venue and f"shared venue: {venue}" not in reasons:
        reasons.append(f"shared venue: {venue}")
    if len(reasons) < 3 and overlap_tokens:
        reasons.append(f"title overlap: {len(overlap_tokens)}")
    if not reasons:
        reasons.append("metadata match unavailable")
    return reasons[:3]
