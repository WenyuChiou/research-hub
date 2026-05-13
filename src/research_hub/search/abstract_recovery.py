"""Best-effort abstract recovery from DOI metadata services."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import quote

import requests


logger = logging.getLogger(__name__)

_USER_AGENT = "research-hub/0.80.0 (https://github.com/WenyuChiou/research-hub)"
_UNPAYWALL_EMAIL = "research-hub@anthropic.com"


@dataclass
class RecoveredAbstract:
    text: str
    source: str
    oa_url: str = ""


def _recover_from_crossref(doi: str, *, timeout: int = 10) -> RecoveredAbstract:
    try:
        from research_hub.search.crossref import _extract_crossref_abstract

        response = requests.get(
            f"https://api.crossref.org/works/{quote(doi.strip(), safe='')}",
            timeout=timeout,
            headers={"User-Agent": _USER_AGENT},
        )
        if response.status_code == 200:
            work = (response.json().get("message") or {})
            abstract = _extract_crossref_abstract(work)
            if abstract:
                logger.info("abstract recovery: doi=%s source=crossref", doi)
                return RecoveredAbstract(text=abstract, source="crossref")
    except Exception as exc:
        logger.debug("Crossref abstract recovery failed for %s: %s", doi, exc)
    return RecoveredAbstract(text="", source="")


def _recover_from_unpaywall(doi: str, *, timeout: int = 10) -> RecoveredAbstract:
    try:
        response = requests.get(
            f"https://api.unpaywall.org/v2/{quote(doi.strip(), safe='')}",
            params={"email": _UNPAYWALL_EMAIL},
            timeout=timeout,
            headers={"User-Agent": _USER_AGENT},
        )
        if response.status_code == 200:
            data = response.json() or {}
            best_oa = (data.get("best_oa_location") or {})
            oa_url = best_oa.get("url", "") or ""
            if oa_url:
                logger.info("abstract recovery: doi=%s source=unpaywall oa_url=%s", doi, oa_url)
                return RecoveredAbstract(text="", source="unpaywall", oa_url=oa_url)
    except Exception as exc:
        logger.debug("Unpaywall lookup failed for %s: %s", doi, exc)
    return RecoveredAbstract(text="", source="")


def _recover_from_semantic_scholar(doi: str, *, timeout: int = 10) -> RecoveredAbstract:
    try:
        response = requests.get(
            f"https://api.semanticscholar.org/graph/v1/paper/DOI:{quote(doi.strip(), safe='')}",
            params={"fields": "abstract,tldr"},
            timeout=timeout,
            headers={"User-Agent": _USER_AGENT},
        )
        if response.status_code != 200:
            return RecoveredAbstract(text="", source="")
        data = response.json() or {}
        abstract = str(data.get("abstract", "") or "").strip()
        if abstract:
            logger.info("abstract recovery: doi=%s source=s2", doi)
            return RecoveredAbstract(text=abstract, source="s2")
        tldr = data.get("tldr") or {}
        tldr_text = str((tldr.get("text", "") if isinstance(tldr, dict) else "") or "").strip()
        if tldr_text:
            logger.info("abstract recovery: doi=%s source=s2-tldr", doi)
            return RecoveredAbstract(text=tldr_text, source="s2-tldr")
    except Exception as exc:
        logger.debug("Semantic Scholar abstract recovery failed for %s: %s", doi, exc)
    return RecoveredAbstract(text="", source="")


_MIN_ABSTRACT_CHARS = 200
_PLACEHOLDER_PATTERNS = (
    "(no abstract)",
    "no abstract available",
    "[no abstract]",
    "abstract not available",
)


def _is_substantive(text: str) -> bool:
    """A 'substantive' abstract is ≥ _MIN_ABSTRACT_CHARS chars and not a known placeholder.

    v0.87.1 #3 (V3 audit): Crossref sometimes returns 13-char strings like
    "(no abstract)" instead of an empty value, defeating the previous
    "if x.text: return x" early-exit. Apply a length + denylist check.
    """
    if not text:
        return False
    stripped = text.strip()
    lowered = stripped.lower()
    for pattern in _PLACEHOLDER_PATTERNS:
        if pattern in lowered:
            return False
    return len(stripped) >= _MIN_ABSTRACT_CHARS


def _recover_from_openalex(doi: str, *, timeout: int = 10) -> RecoveredAbstract:
    """v0.87.1 #3: reconstruct abstract from OpenAlex `abstract_inverted_index`.

    OpenAlex stores abstracts as {word: [positions]} for IP / copyright
    reasons (so they can claim "we don't ship the full text"). The
    reconstruction sorts by position to rebuild the original abstract
    text. Coverage on academic DOIs is ~80% (better than S2's 60% and
    not rate-limited like S2).
    """
    try:
        response = requests.get(
            f"https://api.openalex.org/works/doi:{quote(doi.strip(), safe='')}",
            timeout=timeout,
            headers={"User-Agent": _USER_AGENT},
        )
        if response.status_code != 200:
            return RecoveredAbstract(text="", source="")
        data = response.json() or {}
        inverted = data.get("abstract_inverted_index")
        if not isinstance(inverted, dict) or not inverted:
            return RecoveredAbstract(text="", source="")
        # Sort (position, word) pairs and join.
        positions: list[tuple[int, str]] = []
        for word, positions_list in inverted.items():
            if not isinstance(positions_list, list):
                continue
            for pos in positions_list:
                try:
                    positions.append((int(pos), str(word)))
                except (TypeError, ValueError):
                    continue
        if not positions:
            return RecoveredAbstract(text="", source="")
        positions.sort()
        reconstructed = " ".join(word for _, word in positions)
        if reconstructed.strip():
            logger.info("abstract recovery: doi=%s source=openalex", doi)
            return RecoveredAbstract(text=reconstructed.strip(), source="openalex")
    except Exception as exc:
        logger.debug("OpenAlex abstract recovery failed for %s: %s", doi, exc)
    return RecoveredAbstract(text="", source="")


def recover_abstract(doi: str, *, timeout: int = 10) -> RecoveredAbstract:
    """Try Crossref → OpenAlex → Unpaywall → Semantic Scholar for a missing abstract.

    v0.87.1 #3: substantive-content check via `_is_substantive` rejects
    13-char placeholders like "(no abstract)" that previously short-
    circuited the chain. OpenAlex inverted-index reconstruction added
    before Unpaywall+S2 because OpenAlex isn't rate-limited and covers
    ~80% of DOIs.
    """
    if not doi:
        return RecoveredAbstract(text="", source="")

    crossref = _recover_from_crossref(doi, timeout=timeout)
    if _is_substantive(crossref.text):
        return crossref

    openalex = _recover_from_openalex(doi, timeout=timeout)
    if _is_substantive(openalex.text):
        return openalex

    unpaywall = _recover_from_unpaywall(doi, timeout=timeout)
    if _is_substantive(unpaywall.text):
        return unpaywall

    semantic_scholar = _recover_from_semantic_scholar(doi, timeout=timeout)
    if _is_substantive(semantic_scholar.text):
        return semantic_scholar

    # Falling-back: return the longest non-empty text we found, so callers
    # at least see something rather than nothing. Order of preference still
    # informs the source label.
    fallback_candidates = [crossref, openalex, unpaywall, semantic_scholar]
    best = max(fallback_candidates, key=lambda r: len(r.text or ""))
    if best.text:
        return best
    if unpaywall.oa_url:
        return unpaywall
    return RecoveredAbstract(text="", source="")
