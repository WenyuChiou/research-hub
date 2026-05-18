"""Best-effort abstract recovery from DOI metadata services."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
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


_PLACEHOLDER_PATTERNS = (
    "(no abstract)",
    "no abstract available",
    "[no abstract]",
    "abstract not available",
)


def _is_substantive(text: str) -> bool:
    """A 'substantive' abstract is non-empty and not a known placeholder string.

    v0.87.1 #3 (V3 audit): Crossref sometimes returns 13-char strings like
    "(no abstract)" instead of an empty value, defeating the previous
    "if x.text: return x" early-exit. Apply a denylist check.

    Note: no minimum-length threshold — even a 1-sentence abstract is useful
    enough to early-exit the chain, and the v0.72 test_v072_search_quality
    fixtures use short mock abstracts ("Recovered abstract", 18 chars).
    """
    if not text:
        return False
    stripped = text.strip()
    if not stripped:
        return False
    lowered = stripped.lower()
    for pattern in _PLACEHOLDER_PATTERNS:
        if pattern in lowered:
            return False
    return True


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


_BOILERPLATE_RE = re.compile(
    r"(?i)(all\s+rights\s+reserved|copyright\s+\d{4}|doi:\s*10\.\d"
    r"|received:\s*\w+\s+\d{4}|published\s+online|arxiv:\s*\d{4})"
)

_ABSTRACT_HEADER_RE = re.compile(r"(?mi)^[ \t]*abstract\b[ \t]*$")

_SECTION_STOP_RE = re.compile(
    r"(?mi)^[ \t]*(?:(?:\d+[\.\s]+)?introduction|keywords?|ccs\s+concepts"
    r"|index\s+terms|(?:\d+[\.\s]+)[A-Z][a-z])\b"
)


def _extract_abstract_from_text(full_text: str) -> str | None:
    """Extract abstract from the first 6000 chars of PDF full text.

    Heuristic order:
    1. Locate an "Abstract" section header; capture until a section-stop.
    2. Fall back to the 2nd double-newline-separated paragraph.

    Returns None if the extracted text is <200 chars, matches a boilerplate
    pattern, or appears to be column-interleaved/garbled (space ratio <0.08
    or >30% single-char "words"). Returns None on any exception.
    """
    try:
        chunk = full_text[:6000]

        candidate: str | None = None

        header_match = _ABSTRACT_HEADER_RE.search(chunk)
        if header_match:
            after = chunk[header_match.end():]
            stop_match = _SECTION_STOP_RE.search(after)
            candidate = after[: stop_match.start()].strip() if stop_match else after.strip()

        if not candidate:
            # Fall back to 2nd double-newline-separated paragraph
            paragraphs = [p.strip() for p in re.split(r"\n\n+", chunk) if p.strip()]
            if len(paragraphs) >= 2:
                candidate = paragraphs[1]

        if not candidate:
            return None

        # Collapse internal whitespace
        candidate = re.sub(r"[ \t]+", " ", candidate).strip()

        if len(candidate) < 200:
            return None

        if _BOILERPLATE_RE.search(candidate):
            return None

        # Garbled / column-interleaved text heuristic
        if len(candidate) > 0:
            space_ratio = candidate.count(" ") / len(candidate)
            if space_ratio < 0.08:
                return None
            words = candidate.split()
            if words:
                single_char_ratio = sum(1 for w in words if len(w) == 1) / len(words)
                if single_char_ratio > 0.30:
                    return None

        return candidate[:4000]
    except Exception:
        return None


def _recover_from_local_pdf(pdf_path: Path) -> str:
    """Extract abstract text from a local PDF file.

    Returns "" (empty string) when pdf_path is None, does not exist,
    extraction raises, or no substantive abstract can be parsed from
    the PDF text. Never raises.
    """
    if pdf_path is None or not pdf_path.exists():
        return ""
    try:
        from research_hub.importer import _extract_pdf
    except Exception:
        return ""
    try:
        text = _extract_pdf(pdf_path)
    except Exception:
        return ""
    abs_text = _extract_abstract_from_text(text or "")
    return abs_text or ""


def recover_abstract(doi: str, *, timeout: int = 10, pdf_path: Path | None = None) -> RecoveredAbstract:
    """Try Crossref → Unpaywall → OpenAlex → Semantic Scholar for a missing abstract.

    v0.87.1 #3:
    - `_is_substantive` rejects 13-char placeholders like "(no abstract)"
      that previously short-circuited the chain.
    - OpenAlex inverted-index reconstruction added (~80% DOI coverage,
      not rate-limited like S2).
    - Order preserves v0.72 invariant: Unpaywall (which can return a
      non-text oa_url-only record) is checked before OpenAlex so its
      oa_url fallback stays reachable when every source has no text.

    v0.95.0 (pdf_path): when all 4 online sources return non-substantive
    results AND a local PDF path is supplied, extract the abstract from
    the PDF text as a last resort. Fail-safe: returns nothing rather
    than write garbage. Pass pdf_path=None (the default) to disable.
    """
    if not doi:
        return RecoveredAbstract(text="", source="")

    crossref = _recover_from_crossref(doi, timeout=timeout)
    if _is_substantive(crossref.text):
        return crossref

    unpaywall = _recover_from_unpaywall(doi, timeout=timeout)
    if _is_substantive(unpaywall.text):
        return unpaywall

    openalex = _recover_from_openalex(doi, timeout=timeout)
    if _is_substantive(openalex.text):
        return openalex

    semantic_scholar = _recover_from_semantic_scholar(doi, timeout=timeout)
    if _is_substantive(semantic_scholar.text):
        return semantic_scholar

    # Last-resort: extract abstract from local PDF (only when all 4 online
    # sources returned non-substantive and a pdf_path was supplied).
    if pdf_path is not None:
        pdf_abs = _recover_from_local_pdf(pdf_path)
        if _is_substantive(pdf_abs):
            return RecoveredAbstract(text=pdf_abs, source="local-pdf")

    # v0.72 invariant: when Unpaywall has only an oa_url (no abstract text),
    # surface that so downstream tools can still fetch the OA PDF.
    if unpaywall.oa_url:
        return unpaywall
    return RecoveredAbstract(text="", source="")
