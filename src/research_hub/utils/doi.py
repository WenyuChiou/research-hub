"""Canonical DOI normalization helper.

Replaces the 4 different implementations across dedup.py, verify.py,
bundle.py, and pipeline.py.
"""

from __future__ import annotations

import re

_DOI_PREFIXES = (
    "https://doi.org/",
    "http://doi.org/",
    "https://dx.doi.org/",
    "http://dx.doi.org/",
    "doi:",
    "DOI:",
)


def normalize_doi(doi: str) -> str:
    """Return a lowercase, prefix-stripped DOI string.

    Examples:
        >>> normalize_doi("https://doi.org/10.1038/S44168-025-00254-1")
        '10.1038/s44168-025-00254-1'
        >>> normalize_doi("doi:10.1145/3630106.3658942")
        '10.1145/3630106.3658942'
        >>> normalize_doi("")
        ''
    """
    if not doi:
        return ""
    cleaned = doi.strip()
    for prefix in _DOI_PREFIXES:
        if cleaned.lower().startswith(prefix.lower()):
            cleaned = cleaned[len(prefix):]
            break
    return cleaned.strip().lower()


def is_arxiv_doi(doi: str) -> bool:
    """Detect arXiv-style DOIs (10.48550/arxiv.NNNN.NNNNN)."""
    return "10.48550/arxiv" in normalize_doi(doi)


def extract_arxiv_id(doi_or_url: str) -> str:
    """Pull a bare arXiv id (e.g., '2502.10978') from various forms."""
    if not doi_or_url:
        return ""
    match = re.search(r"(\d{4}\.\d{4,5}(?:v\d+)?)", doi_or_url)
    return match.group(1) if match else ""
