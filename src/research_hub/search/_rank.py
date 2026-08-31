"""Confidence scoring and ranking helpers."""

from __future__ import annotations

import datetime
import re
from dataclasses import replace

from research_hub.search.base import SearchResult


def confidence_from_backends(found_in: list[str]) -> float:
    """0.5 + 0.25 * (n - 1), clamped to [0.5, 1.0]."""
    count = len(set(found_in))
    if count <= 0:
        return 0.5
    return min(1.0, 0.5 + 0.25 * (count - 1))


def _identity_keys(result: SearchResult) -> list[str]:
    """Return every strong cross-backend identity carried by a result."""
    keys = [result.dedup_key] if result.dedup_key else []
    if result.arxiv_id:
        arxiv_key = f"arxiv:{result.arxiv_id.strip().lower()}"
        if arxiv_key not in keys:
            keys.append(arxiv_key)
    return keys


def _merge_record(base: SearchResult, incoming: SearchResult) -> SearchResult:
    found_in = list(base.found_in)
    for backend_name in incoming.found_in:
        if backend_name not in found_in:
            found_in.append(backend_name)
    fill: dict[str, object] = {"found_in": found_in}
    if not base.abstract and incoming.abstract:
        fill["abstract"] = incoming.abstract
    if not base.doi and incoming.doi:
        fill["doi"] = incoming.doi
    if not base.arxiv_id and incoming.arxiv_id:
        fill["arxiv_id"] = incoming.arxiv_id
    if not base.pdf_url and incoming.pdf_url:
        fill["pdf_url"] = incoming.pdf_url
    if base.citation_count == 0 and incoming.citation_count > 0:
        fill["citation_count"] = incoming.citation_count
    if not base.venue and incoming.venue:
        fill["venue"] = incoming.venue
    if not base.doc_type and incoming.doc_type:
        fill["doc_type"] = incoming.doc_type
    return replace(base, **fill)


def merge_results(per_backend: dict[str, list[SearchResult]]) -> list[SearchResult]:
    """Merge results by every shared strong identity, not only one preferred key."""
    merged: dict[str, SearchResult] = {}
    alias_owner: dict[str, str] = {}
    owner_order: dict[str, int] = {}
    next_owner_order = 0
    for backend_name, results in per_backend.items():
        for result in results:
            keys = _identity_keys(result)
            if not keys:
                continue
            incoming = replace(
                result,
                source=result.source or backend_name,
                found_in=[backend_name],
                confidence=0.5,
            )
            owners = list(dict.fromkeys(alias_owner[key] for key in keys if key in alias_owner))
            if not owners:
                owner = keys[0]
                merged[owner] = incoming
                owner_order[owner] = next_owner_order
                next_owner_order += 1
            else:
                owners.sort(key=owner_order.__getitem__)
                owner = owners[0]
                for redundant_owner in owners[1:]:
                    merged[owner] = _merge_record(merged[owner], merged.pop(redundant_owner))
                    owner_order.pop(redundant_owner)
                    for alias, current_owner in list(alias_owner.items()):
                        if current_owner == redundant_owner:
                            alias_owner[alias] = owner
                merged[owner] = _merge_record(merged[owner], incoming)
            for key in keys:
                alias_owner[key] = owner

    for key, result in list(merged.items()):
        merged[key] = replace(result, confidence=confidence_from_backends(result.found_in))
    return list(merged.values())


def _term_overlap(result: SearchResult, query: str) -> float:
    if not query:
        return 0.5
    query_terms = {term.lower() for term in re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", query)}
    if not query_terms:
        return 0.5
    haystack = f"{result.title} {result.abstract}".lower()
    hits = sum(1 for term in query_terms if re.search(rf"\b{re.escape(term)}\b", haystack))
    return hits / len(query_terms)


def rank(
    results: list[SearchResult],
    *,
    rank_by: str = "smart",
    current_year: int | None = None,
    relevance_query: str | None = None,
) -> list[SearchResult]:
    """Sort results by the chosen strategy."""
    if current_year is None:
        current_year = datetime.date.today().year

    def smart_score(result: SearchResult) -> float:
        recency = max(0.0, 1.0 - 0.2 * (current_year - (result.year or current_year - 5)))
        relevance = _term_overlap(result, relevance_query or "") if relevance_query else 0.5
        return 2.0 * result.confidence + 1.0 * recency + 1.0 * relevance

    if rank_by == "citation":
        return sorted(results, key=lambda result: (result.citation_count, result.year or 0), reverse=True)
    if rank_by == "year":
        return sorted(results, key=lambda result: (result.year or 0, result.citation_count), reverse=True)
    return sorted(results, key=smart_score, reverse=True)


def apply_filters(
    results: list[SearchResult],
    *,
    exclude_types: tuple[str, ...] = (),
    exclude_terms: tuple[str, ...] = (),
    min_confidence: float = 0.0,
) -> list[SearchResult]:
    """Drop results matching any exclude rule."""
    type_set = {item.strip().lower() for item in exclude_types if item.strip()}
    term_set = {item.strip().lower() for item in exclude_terms if item.strip()}
    filtered: list[SearchResult] = []
    for result in results:
        if result.confidence < min_confidence:
            continue
        if type_set and (result.doc_type or "").lower() in type_set:
            continue
        if term_set:
            haystack = f"{result.title} {result.abstract}".lower()
            if any(term in haystack for term in term_set):
                continue
        filtered.append(result)
    return filtered
