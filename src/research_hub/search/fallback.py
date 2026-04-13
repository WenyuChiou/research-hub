"""Multi-backend search orchestrator."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from dataclasses import replace

from research_hub.search.arxiv_backend import ArxivBackend
from research_hub.search.base import SearchBackend, SearchResult
from research_hub.search.openalex import OpenAlexBackend
from research_hub.search.semantic_scholar import SemanticScholarClient


logger = logging.getLogger(__name__)

_BACKEND_REGISTRY: dict[str, type[SearchBackend]] = {
    "openalex": OpenAlexBackend,
    "arxiv": ArxivBackend,
    "semantic-scholar": SemanticScholarClient,
}

DEFAULT_BACKENDS = ("openalex", "arxiv", "semantic-scholar")


def search_papers(
    query: str,
    *,
    limit: int = 20,
    year_from: int | None = None,
    year_to: int | None = None,
    min_citations: int = 0,
    backends: Sequence[str] = DEFAULT_BACKENDS,
) -> list[SearchResult]:
    """Run a query across multiple backends and merge results by dedup_key."""
    merged: dict[str, SearchResult] = {}

    for name in backends:
        cls = _BACKEND_REGISTRY.get(name)
        if cls is None:
            logger.warning("unknown search backend: %s", name)
            continue
        try:
            backend = cls()
            results = backend.search(
                query,
                limit=limit,
                year_from=year_from,
                year_to=year_to,
            )
        except Exception as exc:
            logger.warning("search backend %s failed: %s", name, exc)
            continue

        for result in results:
            if result.citation_count < min_citations:
                continue
            key = result.dedup_key
            if not key:
                continue
            if key not in merged:
                merged[key] = result
            else:
                merged[key] = _merge(merged[key], result)

    ranked = sorted(
        merged.values(),
        key=lambda r: (r.year or 0, r.citation_count),
        reverse=True,
    )
    return ranked[:limit]


def _merge(base: SearchResult, extra: SearchResult) -> SearchResult:
    """Fill empty fields on `base` from `extra`. Never overwrite non-empty fields."""
    fill: dict[str, object] = {}
    if not base.abstract and extra.abstract:
        fill["abstract"] = extra.abstract
    if not base.doi and extra.doi:
        fill["doi"] = extra.doi
    if not base.arxiv_id and extra.arxiv_id:
        fill["arxiv_id"] = extra.arxiv_id
    if not base.pdf_url and extra.pdf_url:
        fill["pdf_url"] = extra.pdf_url
    if base.citation_count == 0 and extra.citation_count:
        fill["citation_count"] = extra.citation_count
    if not base.venue and extra.venue:
        fill["venue"] = extra.venue
    return replace(base, **fill) if fill else base


def iter_new_results(
    client_or_backends,
    query: str,
    already_ingested: Iterable[str],
    limit: int = 20,
) -> list[SearchResult]:
    """Backwards-compat shim. Old signature: (client, query, already_ingested, limit)."""
    from research_hub.utils.doi import normalize_doi

    ingested = {normalize_doi(doi) for doi in already_ingested if doi}

    if hasattr(client_or_backends, "search") and not isinstance(client_or_backends, (list, tuple)):
        results = client_or_backends.search(query, limit=limit)
    else:
        results = search_papers(query, limit=limit, backends=tuple(client_or_backends))

    return [r for r in results if normalize_doi(r.doi) not in ingested]
