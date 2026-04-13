"""Search backends and compatibility exports."""

from research_hub.search.arxiv_backend import ArxivBackend
from research_hub.search.base import SearchBackend, SearchResult
from research_hub.search.biorxiv import BiorxivBackend
from research_hub.search.chemrxiv import ChemrxivBackend
from research_hub.search.cinii import CiniiBackend
from research_hub.search.crossref import CrossrefBackend
from research_hub.search.dblp import DblpBackend
from research_hub.search.enrich import classify_candidate, enrich_candidates
from research_hub.search.eric import EricBackend
from research_hub.search.fallback import iter_new_results, search_papers
from research_hub.search.kci import KciBackend
from research_hub.search.nasa_ads import NasaAdsBackend
from research_hub.search.openalex import OpenAlexBackend
from research_hub.search.pubmed import PubMedBackend
from research_hub.search.repec import RepecBackend
from research_hub.search.semantic_scholar import SemanticScholarClient

__all__ = [
    "SearchResult",
    "SearchBackend",
    "SemanticScholarClient",
    "OpenAlexBackend",
    "ArxivBackend",
    "CrossrefBackend",
    "DblpBackend",
    "PubMedBackend",
    "BiorxivBackend",
    "RepecBackend",
    "ChemrxivBackend",
    "CiniiBackend",
    "NasaAdsBackend",
    "EricBackend",
    "KciBackend",
    "search_papers",
    "iter_new_results",
    "enrich_candidates",
    "classify_candidate",
]
