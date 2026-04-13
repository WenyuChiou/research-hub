"""Multi-backend search orchestrator."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence

from research_hub.search.arxiv_backend import ArxivBackend
from research_hub.search.biorxiv import BiorxivBackend
from research_hub.search.crossref import CrossrefBackend
from research_hub.search.dblp import DblpBackend
from research_hub.search.base import SearchBackend, SearchResult
from research_hub.search.openalex import OpenAlexBackend
from research_hub.search.pubmed import PubMedBackend
from research_hub.search.repec import RepecBackend
from research_hub.search.semantic_scholar import SemanticScholarClient


logger = logging.getLogger(__name__)

_BACKEND_REGISTRY: dict[str, type[SearchBackend]] = {
    "openalex": OpenAlexBackend,
    "arxiv": ArxivBackend,
    "semantic-scholar": SemanticScholarClient,
    "crossref": CrossrefBackend,
    "dblp": DblpBackend,
    "pubmed": PubMedBackend,
    "biorxiv": BiorxivBackend,
    "medrxiv": BiorxivBackend,
    "repec": RepecBackend,
}

DEFAULT_BACKENDS = ("openalex", "arxiv", "semantic-scholar", "crossref", "dblp")

FIELD_PRESETS: dict[str, tuple[str, ...]] = {
    "cs": ("openalex", "arxiv", "semantic-scholar", "dblp", "crossref"),
    "bio": ("openalex", "pubmed", "biorxiv", "crossref", "semantic-scholar"),
    "med": ("openalex", "pubmed", "biorxiv", "crossref", "semantic-scholar"),
    "physics": ("openalex", "arxiv", "crossref", "semantic-scholar"),
    "math": ("openalex", "arxiv", "crossref", "semantic-scholar"),
    "social": ("openalex", "crossref", "semantic-scholar", "repec"),
    "econ": ("openalex", "crossref", "semantic-scholar", "repec"),
    "general": (
        "openalex",
        "arxiv",
        "semantic-scholar",
        "crossref",
        "dblp",
        "pubmed",
        "biorxiv",
        "repec",
    ),
}


def resolve_backends_for_field(field: str) -> tuple[str, ...]:
    """Return the backend tuple for a known field preset."""
    if field not in FIELD_PRESETS:
        valid = ", ".join(sorted(FIELD_PRESETS.keys()))
        raise ValueError(f"unknown field preset {field!r}; valid: {valid}")
    return FIELD_PRESETS[field]


def search_papers(
    query: str,
    *,
    limit: int = 20,
    year_from: int | None = None,
    year_to: int | None = None,
    min_citations: int = 0,
    backends: Sequence[str] = DEFAULT_BACKENDS,
    exclude_types: Sequence[str] = (),
    exclude_terms: Sequence[str] = (),
    min_confidence: float = 0.0,
    rank_by: str = "smart",
    backend_trace: bool = False,
    per_backend_limit: int | None = None,
) -> list[SearchResult]:
    """Multi-backend search with merge + filter + rank."""
    from research_hub.search._rank import apply_filters, merge_results, rank

    if per_backend_limit is None:
        per_backend_limit = max(limit * 2, 20)

    per_backend: dict[str, list[SearchResult]] = {}
    trace: dict[str, int] = {}
    for name in backends:
        cls = _BACKEND_REGISTRY.get(name)
        if cls is None:
            logger.warning("unknown search backend: %s", name)
            continue
        try:
            backend = cls()
            if name == "arxiv":
                results = backend.search(
                    query,
                    limit=per_backend_limit,
                    year_from=year_from,
                    year_to=year_to,
                )
            else:
                results = backend.search(
                    query,
                    limit=per_backend_limit,
                    year_from=year_from,
                    year_to=year_to,
                )
                if min_citations > 0:
                    results = [result for result in results if result.citation_count >= min_citations]
        except Exception as exc:
            logger.warning("search backend %s failed: %s", name, exc)
            results = []
        per_backend[name] = results
        trace[name] = len(results)

    if backend_trace:
        for name, count in trace.items():
            logger.info("backend %s: %d hits", name, count)

    merged = merge_results(per_backend)
    filtered = apply_filters(
        merged,
        exclude_types=tuple(exclude_types),
        exclude_terms=tuple(exclude_terms),
        min_confidence=min_confidence,
    )
    ranked = rank(filtered, rank_by=rank_by, relevance_query=query)
    return ranked[:limit]


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
