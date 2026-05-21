"""Multi-backend search orchestrator."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
from dataclasses import dataclass
import logging
from collections.abc import Iterable, Sequence

from research_hub.search.arxiv_backend import ArxivBackend
from research_hub.search.biorxiv import BiorxivBackend
from research_hub.search.chemrxiv import ChemrxivBackend
from research_hub.search.cinii import CiniiBackend
from research_hub.search.crossref import CrossrefBackend
from research_hub.search.dblp import DblpBackend
from research_hub.search.base import SearchBackend, SearchResult
from research_hub.search.eric import EricBackend
from research_hub.search.google_scholar_backend import GoogleScholarBackend
from research_hub.search.kci import KciBackend
from research_hub.search.nasa_ads import NasaAdsBackend
from research_hub.search.openalex import OpenAlexBackend
from research_hub.search.pubmed import PubMedBackend
from research_hub.search.repec import RepecBackend
from research_hub.search.semantic_scholar import SemanticScholarClient
from research_hub.search.ssrn_backend import SsrnBackend
from research_hub.search.websearch import WebSearchBackend


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
    "chemrxiv": ChemrxivBackend,
    "nasa-ads": NasaAdsBackend,
    "eric": EricBackend,
    "cinii": CiniiBackend,
    "kci": KciBackend,
    "websearch": WebSearchBackend,
    "google-scholar": GoogleScholarBackend,  # optional: pip install scholarly
    "ssrn": SsrnBackend,
}

DEFAULT_BACKENDS = ("openalex", "arxiv", "semantic-scholar", "crossref", "dblp")
PREPRINT_BACKENDS = ("arxiv", "biorxiv", "chemrxiv", "medrxiv")
GRAY_DOC_TYPES = (
    "preprint",
    "posted-content",
    "report",
    "book-chapter",
    "paratext",
    "dataset",
)

FIELD_PRESETS: dict[str, tuple[str, ...]] = {
    "cs": ("openalex", "arxiv", "semantic-scholar", "dblp", "crossref", "google-scholar"),
    "bio": ("openalex", "pubmed", "biorxiv", "crossref", "semantic-scholar"),
    "med": ("openalex", "pubmed", "biorxiv", "crossref", "semantic-scholar"),
    "physics": ("openalex", "arxiv", "crossref", "semantic-scholar"),
    "math": ("openalex", "arxiv", "crossref", "semantic-scholar"),
    "social": ("openalex", "crossref", "semantic-scholar", "repec", "ssrn"),
    "econ": ("openalex", "crossref", "semantic-scholar", "repec", "ssrn"),
    "chem": ("openalex", "chemrxiv", "crossref", "semantic-scholar"),
    "astro": ("openalex", "arxiv", "nasa-ads", "crossref", "semantic-scholar"),
    "edu": ("openalex", "eric", "crossref", "semantic-scholar"),
    "general": (
        "openalex",
        "arxiv",
        "semantic-scholar",
        "crossref",
        "dblp",
        "pubmed",
        "biorxiv",
        "repec",
        "ssrn",
        "chemrxiv",
        "nasa-ads",
        "eric",
        "google-scholar",
    ),
}

REGION_PRESETS: dict[str, tuple[str, ...]] = {
    "en": DEFAULT_BACKENDS,
    "jp": ("openalex", "cinii", "crossref"),
    "kr": ("openalex", "kci", "crossref"),
    "cjk": ("openalex", "cinii", "kci", "crossref"),
}


def apply_peer_reviewed(
    backends: Sequence[str],
    exclude_types: Sequence[str],
    min_confidence: float,
) -> tuple[tuple[str, ...], tuple[str, ...], float]:
    """Return (backends, exclude_types, min_confidence) hardened to peer-reviewed-only.

    Drops preprint-only backends, adds gray-literature doc types to
    exclude_types, and floors min_confidence at 0.5.
    """
    backend_tuple = tuple(backends)
    hardened_backends = tuple(
        backend for backend in backend_tuple if backend not in PREPRINT_BACKENDS
    ) or backend_tuple
    hardened_exclude_types = tuple(dict.fromkeys((*exclude_types, *GRAY_DOC_TYPES)))
    return hardened_backends, hardened_exclude_types, max(min_confidence, 0.5)


def resolve_backends_for_field(field: str) -> tuple[str, ...]:
    """Return the backend tuple for a known field preset."""
    if field not in FIELD_PRESETS:
        valid = ", ".join(sorted(FIELD_PRESETS.keys()))
        raise ValueError(f"unknown field preset {field!r}; valid: {valid}")
    return FIELD_PRESETS[field]


def resolve_backends_for_region(region: str) -> tuple[str, ...]:
    """Return the backend tuple for a known region preset."""
    if region not in REGION_PRESETS:
        valid = ", ".join(sorted(REGION_PRESETS.keys()))
        raise ValueError(f"unknown region preset {region!r}; valid: {valid}")
    return REGION_PRESETS[region]


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
    backend_to_class: list[tuple[str, type[SearchBackend]]] = []
    for name in backends:
        cls = _BACKEND_REGISTRY.get(name)
        if cls is None:
            logger.warning("unknown search backend: %s", name)
            continue
        backend_to_class.append((name, cls))

    def _search_one_backend(name: str, cls: type[SearchBackend]) -> tuple[str, list[SearchResult]]:
        backend = cls()
        results = backend.search(
            query,
            limit=per_backend_limit,
            year_from=year_from,
            year_to=year_to,
        )
        if name != "arxiv" and min_citations > 0:
            results = [result for result in results if result.citation_count >= min_citations]
        return name, results

    if backend_to_class:
        completed_results: dict[str, list[SearchResult]] = {}
        executor = ThreadPoolExecutor(max_workers=min(len(backend_to_class), 8))
        futures = {
            executor.submit(_search_one_backend, name, cls): name
            for name, cls in backend_to_class
        }
        try:
            for future in as_completed(futures, timeout=60):
                name = futures[future]
                try:
                    backend_name, results = future.result()
                    completed_results[backend_name] = results
                except Exception as exc:
                    logger.warning("search backend %s failed: %s", name, exc)
                    completed_results[name] = []
        except TimeoutError:
            logger.warning("search backend pool timed out after 60s")
        finally:
            for future, name in futures.items():
                if name not in completed_results:
                    future.cancel()
                    completed_results[name] = []
            executor.shutdown(wait=False, cancel_futures=True)
        for name, _cls in backend_to_class:
            per_backend[name] = completed_results.get(name, [])

    trace = {name: len(per_backend.get(name, [])) for name, _cls in backend_to_class}

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


@dataclass
class RecallReport:
    """Recall-confidence summary for an adversarial (multi-query) search.

    `confidence` answers: how likely is it that the union of results is the
    near-complete set of relevant papers? It is derived from saturation —
    whether later query phrasings stopped contributing new papers.
    """

    queries_run: int
    variants: list[str]
    new_per_query: list[int]  # unique papers each successive variant added
    total_unique: int
    saturated: bool
    confidence: str  # "high" | "medium" | "low"


# Recall-confidence bands: the share of total unique papers the LAST query
# variant still contributed. A small share => the corpus is saturated.
# Magic numbers by design — expect to recalibrate after real-world runs.
_RECALL_HIGH_THRESHOLD = 0.05
_RECALL_MED_THRESHOLD = 0.20


def _recall_confidence(new_per_query: list[int]) -> tuple[str, bool]:
    """Estimate recall confidence from the per-variant new-paper counts.

    Saturation: the last variant added (almost) nothing new -> the corpus is
    likely exhausted -> high confidence. If every variant keeps adding a
    meaningful share, the corpus is not exhausted -> low confidence. Fewer
    than two variants, or zero papers found at all, give no saturation
    signal -> low confidence (zero results is "found nothing", not "thorough").
    """
    if len(new_per_query) < 2:
        return "low", False
    total = sum(new_per_query)
    if total == 0:
        return "low", False
    last_share = new_per_query[-1] / total
    if last_share <= _RECALL_HIGH_THRESHOLD:
        return "high", True
    if last_share <= _RECALL_MED_THRESHOLD:
        return "medium", False
    return "low", False


def adversarial_search(
    query: str,
    *,
    limit: int = 20,
    max_variants: int = 5,
    llm_cli: str | None = None,
    per_query_limit: int | None = None,
    **search_kwargs,
) -> tuple[list[SearchResult], RecallReport]:
    """Search under several query phrasings, union the results, and report
    how confident we can be that recall is complete.

    A single query phrasing systematically misses papers that use other
    vocabulary — and a missed paper makes a research gap look open when it is
    not. This runs `search_papers` once per expanded phrasing, unions by
    `dedup_key`, re-ranks, and returns a `RecallReport` alongside the results.

    `search_kwargs` is forwarded to `search_papers` (year_from, year_to,
    backends, exclude_types, exclude_terms, min_confidence, min_citations,
    rank_by, backend_trace).
    """
    from research_hub.search._rank import rank
    from research_hub.search.query_expansion import expand_query

    variants = expand_query(query, max_variants=max_variants, llm_cli=llm_cli)
    if not variants:
        return [], RecallReport(0, [], [], 0, False, "low")
    if per_query_limit is None:
        per_query_limit = max(limit * 3, 30)

    rank_by = search_kwargs.pop("rank_by", "smart")
    logger.info(
        "adversarial_search: %d query phrasings (per_query_limit=%d) — "
        "favours completeness over speed",
        len(variants),
        per_query_limit,
    )
    seen: dict[str, SearchResult] = {}
    new_per_query: list[int] = []
    for variant in variants:
        before = len(seen)
        hits = search_papers(variant, limit=per_query_limit, **search_kwargs)
        for result in hits:
            seen.setdefault(result.dedup_key, result)
        new_per_query.append(len(seen) - before)

    confidence, saturated = _recall_confidence(new_per_query)
    report = RecallReport(
        queries_run=len(variants),
        variants=variants,
        new_per_query=new_per_query,
        total_unique=len(seen),
        saturated=saturated,
        confidence=confidence,
    )
    ranked = rank(list(seen.values()), rank_by=rank_by, relevance_query=query)
    return ranked[:limit], report


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
