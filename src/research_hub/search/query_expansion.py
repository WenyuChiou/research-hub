"""Query expansion for adversarial-recall search.

Turns one search query into several phrasings of the same search intent, so
a paper that uses different vocabulary than the user's query is still
retrieved. Incomplete recall is the dominant failure mode in topic-scoping
search: a missed paper makes a research gap look open when it is not.

LLM-preferred with a deterministic fallback — mirrors the graceful-degrade
pattern of the `auto`-pipeline fit-check (no LLM CLI on PATH -> still works,
at reduced expansion quality).
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_EXPANSION_PROMPT = """You are helping make an academic literature search exhaustive.

Given ONE search query, produce {n} ALTERNATIVE phrasings of the SAME search
intent. Vary: method-name vs problem-name framing, broad vs narrow scope, and
common synonyms / terminology a different research community would use. Do NOT
change the topic or drift to a related-but-different one.

Output one phrasing per line. No numbering, no quotes, no commentary.

QUERY: {query}"""

# strips a leading list marker ("- ", "* ", "1. ", "42) ") from an LLM line.
# Requires whitespace AFTER the marker, so a digit-prefixed phrasing like
# "3D flood model" or "10x speedup" is never mistaken for a numbered item.
_LIST_MARKER = re.compile(r"^(?:\s*[-*]\s+|\s*\d+[.)]\s+)")


def _deterministic_variants(query: str, max_variants: int) -> list[str]:
    """Rule-based fallback used when no LLM CLI is available.

    Weaker than LLM expansion (it cannot rephrase), but reproducible and
    dependency-free: it only narrows (quote the phrase) and broadens (drop a
    boundary word).
    """
    words = query.split()
    candidates: list[str] = []
    if len(words) > 1:
        candidates.append(f'"{query}"')           # narrow: exact phrase
    if len(words) > 2:
        candidates.append(" ".join(words[:-1]))   # broaden: drop last word
        candidates.append(" ".join(words[1:]))    # broaden: drop first word
    seen = {query.lower()}
    out: list[str] = []
    for cand in candidates:
        if cand.lower() not in seen:
            seen.add(cand.lower())
            out.append(cand)
    return out[:max_variants]


def expand_query(
    query: str,
    *,
    max_variants: int = 5,
    llm_cli: str | None = None,
    _invoke=None,
    _detect=None,
) -> list[str]:
    """Return ``[original_query, *alternative_phrasings]``.

    Element 0 is always the original query verbatim. Alternatives come from
    an LLM CLI when one is available, otherwise from the deterministic
    fallback. This function never raises: any LLM failure is logged and the
    fallback is used. ``_invoke`` / ``_detect`` are injection points for tests.
    """
    query = query.strip()
    if not query:
        return []
    result = [query]
    if max_variants <= 0:
        return result

    from research_hub.llm_cli import detect_llm_cli, invoke_llm_cli

    detect = _detect or detect_llm_cli
    invoke = _invoke or invoke_llm_cli

    cli = llm_cli or detect()
    if cli:
        try:
            prompt = _EXPANSION_PROMPT.format(n=max_variants, query=query)
            raw = invoke(cli, prompt, timeout_sec=60.0)
            for line in raw.splitlines():
                cleaned = _LIST_MARKER.sub("", line).strip().strip('"').strip()
                if not cleaned or cleaned.lower() == query.lower():
                    continue
                if cleaned not in result:
                    result.append(cleaned)
                if len(result) > max_variants:
                    break
            if len(result) > 1:
                return result[: max_variants + 1]
            logger.warning(
                "query expansion: LLM CLI %s returned no usable variants; "
                "using deterministic fallback",
                cli,
            )
        except Exception as exc:  # noqa: BLE001 - never let expansion break search
            logger.warning(
                "query expansion via %s failed (%s); using deterministic fallback",
                cli,
                exc,
            )

    for variant in _deterministic_variants(query, max_variants):
        if variant not in result:
            result.append(variant)
    return result[: max_variants + 1]
