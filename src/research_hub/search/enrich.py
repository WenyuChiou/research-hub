"""Enrich candidate identifiers into full SearchResults."""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence

from research_hub.search.arxiv_backend import ArxivBackend
from research_hub.search.base import SearchResult
from research_hub.search.openalex import OpenAlexBackend
from research_hub.search.semantic_scholar import SemanticScholarClient


logger = logging.getLogger(__name__)

_DOI_RE = re.compile(r"10\.\d{4,}/\S+")
_ARXIV_RE = re.compile(r"^\d{4}\.\d{4,5}(?:v\d+)?$")


def classify_candidate(candidate: str) -> str:
    """Return 'doi' | 'arxiv' | 'title'."""
    if _DOI_RE.search(candidate):
        return "doi"
    if _ARXIV_RE.match(candidate.strip()):
        return "arxiv"
    return "title"


def enrich_candidates(
    candidates: Sequence[str],
    *,
    backends: Sequence[str] = ("openalex", "arxiv", "semantic-scholar"),
) -> list[SearchResult | None]:
    """Resolve each candidate to a full SearchResult."""
    try:
        from rapidfuzz import fuzz

        def _ratio(left: str, right: str) -> int:
            return int(fuzz.ratio(left, right))

    except ImportError:  # pragma: no cover - exercised when optional dep is absent
        from difflib import SequenceMatcher

        def _ratio(left: str, right: str) -> int:
            return int(SequenceMatcher(None, left, right).ratio() * 100)

    instances: dict[str, object] = {}
    for name in backends:
        if name == "openalex":
            instances[name] = OpenAlexBackend()
        elif name == "arxiv":
            instances[name] = ArxivBackend()
        elif name == "semantic-scholar":
            instances[name] = SemanticScholarClient()

    out: list[SearchResult | None] = []
    for cand in candidates:
        kind = classify_candidate(cand)
        resolved: SearchResult | None = None

        if kind in ("doi", "arxiv"):
            for name, backend in instances.items():
                try:
                    identifier = cand
                    if kind == "arxiv" and name == "semantic-scholar":
                        identifier = f"arxiv:{cand}"
                    result = backend.get_paper(identifier)
                except Exception as exc:
                    logger.debug("enrich %s via %s failed: %s", cand, name, exc)
                    continue
                if result is not None:
                    resolved = result
                    break
        else:
            for name, backend in instances.items():
                try:
                    hits = backend.search(cand, limit=5)
                except Exception as exc:
                    logger.debug("enrich title %r via %s failed: %s", cand, name, exc)
                    continue
                if not hits:
                    continue
                best = max(hits, key=lambda h: _ratio(h.title.lower(), cand.lower()))
                if _ratio(best.title.lower(), cand.lower()) >= 60:
                    resolved = best
                    break

        out.append(resolved)
    return out
