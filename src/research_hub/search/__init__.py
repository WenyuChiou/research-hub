"""Search backends and compatibility exports."""

from research_hub.search.arxiv_backend import ArxivBackend
from research_hub.search.base import SearchBackend, SearchResult
from research_hub.search.enrich import classify_candidate, enrich_candidates
from research_hub.search.fallback import iter_new_results, search_papers
from research_hub.search.openalex import OpenAlexBackend
from research_hub.search.semantic_scholar import SemanticScholarClient

__all__ = [
    "SearchResult",
    "SearchBackend",
    "SemanticScholarClient",
    "OpenAlexBackend",
    "ArxivBackend",
    "search_papers",
    "iter_new_results",
    "enrich_candidates",
    "classify_candidate",
]
