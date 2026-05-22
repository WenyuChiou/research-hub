"""Multi-gate fit-check system for clusters.

Gate 1: pre-ingest AI scoring (emit/apply pattern)
Gate 2: ingest-time term overlap check (fast, no AI)
Gate 3: post-ingest NotebookLM briefing audit
Gate 4: periodic drift check
"""

from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)


@dataclass
class FitCheckResult:
    doi: str
    title: str
    score: int
    reason: str
    kept: bool

    def to_dict(self) -> dict:
        return {
            "doi": self.doi,
            "title": self.title,
            "score": self.score,
            "reason": self.reason,
            "kept": self.kept,
        }


@dataclass
class FitCheckReport:
    cluster_slug: str
    threshold: int
    candidates_in: int
    accepted: list[FitCheckResult] = field(default_factory=list)
    rejected: list[FitCheckResult] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"cluster={self.cluster_slug} threshold={self.threshold} "
            f"in={self.candidates_in} accepted={len(self.accepted)} "
            f"rejected={len(self.rejected)}"
        )


_SCORING_RUBRIC = """## Scoring rubric

- **5**: Squarely about the cluster topic. Title uses cluster terms.
- **4**: On-topic but from an adjacent angle.
- **3**: Tangentially related. Default keep.
- **2**: Shares vocabulary but different actual topic.
- **1**: Only superficially related.
- **0**: Off-topic.
"""

_OUTPUT_JSON_EXAMPLE = {
    "scores": [
        {"index": 1, "doi": "10.xxx/yyy", "score": 5, "reason": "Squarely about X"},
        {"index": 2, "doi": "10.xxx/zzz", "score": 2, "reason": "Different topic"},
    ]
}

_OUTPUT_INSTRUCTIONS = (
    "## Your output\n\n"
    "Emit ONE JSON object, nothing else (no prose, no markdown fence):\n\n"
    + json.dumps(_OUTPUT_JSON_EXAMPLE, indent=2)
)


def emit_prompt(
    cluster_slug: str,
    candidates: list[dict],
    definition: str | None = None,
    cfg=None,
) -> str:
    """Build the Gate 1 fit-check prompt."""
    if definition is None and cfg is not None:
        definition = _read_definition_from_overview(cfg, cluster_slug)
    if not definition:
        definition = f"(no definition supplied for cluster {cluster_slug})"

    key_terms = _extract_key_terms(definition)
    lines = [
        f'# Fit-check: cluster "{cluster_slug}"',
        "",
        "## Cluster definition",
        "",
        definition,
        "",
        f"Key terms: {', '.join(key_terms)}." if key_terms else "Key terms: none.",
        "",
        _SCORING_RUBRIC,
        "",
        f"## Papers to score ({len(candidates)} total)",
        "",
    ]
    for i, paper in enumerate(candidates, start=1):
        title = paper.get("title", "(untitled)")
        authors = paper.get("authors", "")
        if isinstance(authors, list):
            authors_str = ", ".join(str(author) for author in authors[:3])
            if len(authors) > 3:
                authors_str += f" +{len(authors) - 3} more"
        else:
            authors_str = str(authors)
        year = paper.get("year") or "????"
        doi = paper.get("doi", "") or paper.get("arxiv_id", "")
        abstract = paper.get("abstract", "(no abstract)")
        if not str(abstract or "").strip():
            abstract = "(no abstract)"
        lines.extend(
            [
                f"### {i}. {title}",
                f"**Authors:** {authors_str} ({year})",
                f"**DOI:** {doi}",
                "**Abstract:**",
                abstract,
                "",
            ]
        )
    lines.append(_OUTPUT_INSTRUCTIONS)
    return "\n".join(lines)


def apply_scores(
    cluster_slug: str,
    candidates: list[dict],
    scores: list[dict] | dict,
    threshold: int = 3,
    auto_threshold: bool = False,
    cfg=None,
) -> FitCheckReport:
    """Consume AI-produced scores and write sidecars when configured."""
    if isinstance(scores, dict) and "scores" in scores:
        scores = scores["scores"]

    if auto_threshold:
        values = [int(item.get("score", 0)) for item in scores]
        threshold = compute_auto_threshold(values)
        logger.info("auto threshold computed: %d", threshold)

    by_doi: dict[str, dict] = {}
    by_title: dict[str, dict] = {}
    for entry in scores:
        doi = (entry.get("doi") or "").strip().lower()
        if doi:
            by_doi[doi] = entry
        title = (entry.get("title") or "").strip().lower()
        if title:
            by_title[title] = entry

    report = FitCheckReport(
        cluster_slug=cluster_slug,
        threshold=threshold,
        candidates_in=len(candidates),
    )

    for paper in candidates:
        doi = (paper.get("doi") or "").strip().lower()
        title_lower = (paper.get("title") or "").strip().lower()
        entry = by_doi.get(doi) or by_title.get(title_lower)
        if entry is None:
            result = FitCheckResult(
                doi=paper.get("doi", ""),
                title=paper.get("title", ""),
                score=0,
                reason="no score provided",
                kept=False,
            )
        else:
            score = int(entry.get("score", 0))
            result = FitCheckResult(
                doi=paper.get("doi", ""),
                title=paper.get("title", ""),
                score=score,
                reason=str(entry.get("reason", "")),
                kept=score >= threshold,
            )
        if result.kept:
            report.accepted.append(result)
        else:
            report.rejected.append(result)

    if cfg is not None:
        _write_rejected_sidecar(cfg, cluster_slug, report.rejected, threshold)
        _write_accepted_sidecar(cfg, cluster_slug, report.accepted, threshold)

    return report


def compute_auto_threshold(scores: list[int]) -> int:
    """Return median(scores) - 1 clamped to [2, 5]."""
    if not scores:
        return 3
    sorted_scores = sorted(scores)
    n = len(sorted_scores)
    if n % 2 == 1:
        median = sorted_scores[n // 2]
    else:
        median = (sorted_scores[n // 2 - 1] + sorted_scores[n // 2]) // 2
    return max(2, min(5, median - 1))


def term_overlap(abstract: str, key_terms: Iterable[str]) -> float:
    """Return the fraction of key terms present in the abstract."""
    if not abstract:
        return 0.0
    terms = [term.strip().lower() for term in key_terms if term and term.strip()]
    if not terms:
        return 0.0
    abstract_lower = abstract.lower()
    hits = sum(
        1
        for term in terms
        if re.search(rf"\b{re.escape(term)}\b", abstract_lower) is not None
    )
    return hits / len(terms)


def term_overlap_batch(
    papers: list,
    key_terms: list[str],
) -> list[float]:
    """Compute term_overlap score for a list of papers against key_terms.

    papers: list of objects/dicts with .abstract/.title or ["abstract"]/["title"]
    key_terms: list of keyword strings (topic keywords, cluster name words, etc.)
    Returns: list of float scores in [0.0, 1.0], same length as papers.

    Used by the --no-llm-fit-check path in auto_pipeline.
    """
    scores = []
    for paper in papers:
        # Support both object-style (.abstract) and dict-style (["abstract"])
        if hasattr(paper, "abstract"):
            text = (paper.abstract or "") + " " + (getattr(paper, "title", "") or "")
        elif isinstance(paper, dict):
            text = (paper.get("abstract") or "") + " " + (paper.get("title") or "")
        else:
            text = str(paper)
        scores.append(term_overlap(text.strip(), key_terms))
    return scores


# ---------------------------------------------------------------------------
# v1.x relevance gate -- BM25 + distinctive-term hard gate
#
# Replaces the naive ``term_overlap >= 0.1`` no-LLM gate. That gate split the
# topic into independent unigrams and kept any paper matching 1-of-N common
# words, so ``llm-water-resources`` filled with generic hydrology papers
# ("water"/"model"/"resources" matched; the discriminating phrase "large
# language model" was destroyed). Grounded in ASReview / BM25 practice:
#   * the topic is parsed into 1..3-gram terms so phrases survive intact;
#   * BM25 IDF is computed from the candidate batch itself, so a term
#     present in every candidate ("water" in an all-water batch) carries
#     ~0 weight while a distinctive term carries high weight;
#   * HARD GATE -- a paper must contain >=1 *distinctive* term (a topic
#     term appearing in fewer than _DISTINCTIVE_DF_RATIO of the batch); a
#     generic hydrology paper matches no distinctive term -> rejected;
#   * cold-start -- if no topic term is distinctive (uniform batch) the
#     gate cannot discriminate, so every paper is kept and flagged
#     `relevance_unverified` (never silently auto-pass, never blanket
#     reject -- a screening gate is recall-biased).
# ---------------------------------------------------------------------------

_BM25_K1 = 1.2
_BM25_B = 0.75
# A topic term is "distinctive" when it appears in fewer than this fraction
# of the candidate batch; above it the term is batch-wide context.
_DISTINCTIVE_DF_RATIO = 0.6
# Below this many candidates the batch is too small for IDF to discriminate
# reliably -- treat as cold-start and defer (keep all, flag for re-screen).
_MIN_BATCH_FOR_GATE = 5
_TOPIC_STOPLIST = {
    "this", "that", "with", "from", "into", "about", "which", "their",
    "there", "where", "these", "those", "have", "been", "will", "would",
    "could", "should", "also", "such", "than", "using", "based", "study",
    "approach", "research", "the", "and", "for", "are", "was", "its",
    "use", "per", "via",
}


def extract_topic_terms(definition: str, max_ngram: int = 3) -> list[str]:
    """Extract 1..*max_ngram*-gram terms from a topic definition.

    Unlike :func:`_extract_key_terms` (the legacy unigram split), multi-word
    concepts such as "large language model" survive as single terms, so a
    distinctive phrase is not diluted into its common component words.
    """
    words = [
        w.lower()
        for w in re.findall(r"[A-Za-z][A-Za-z0-9-]*", definition)
        if len(w) >= 3 and w.lower() not in _TOPIC_STOPLIST
    ]
    seen: set[str] = set()
    terms: list[str] = []
    for n in range(1, max_ngram + 1):
        for i in range(len(words) - n + 1):
            gram = " ".join(words[i : i + n])
            if gram not in seen:
                seen.add(gram)
                terms.append(gram)
    return terms


def _count_term(text: str, term: str) -> int:
    """Word-boundary occurrence count of *term* (a word or phrase) in *text*."""
    if not term:
        return 0
    return len(re.findall(rf"\b{re.escape(term)}\b", text))


def bm25_scores(
    docs: list[str],
    query_terms: list[str],
    k1: float = _BM25_K1,
    b: float = _BM25_B,
) -> tuple[list[float], dict[str, int]]:
    """BM25 score of each doc against *query_terms*.

    IDF is derived from *docs* itself (self-calibrating: a term in every doc
    gets ~0 IDF, a rare term gets high IDF). Returns ``(per-doc score,
    document-frequency per term)``.
    """
    n_docs = len(docs)
    if n_docs == 0:
        return [], {}
    doc_lens = [max(1, len(re.findall(r"[a-z0-9-]+", d))) for d in docs]
    avgdl = sum(doc_lens) / n_docs
    tf_per_doc: list[dict[str, int]] = []
    doc_freq: dict[str, int] = {term: 0 for term in query_terms}
    for d in docs:
        tf = {term: _count_term(d, term) for term in query_terms}
        tf_per_doc.append(tf)
        for term, count in tf.items():
            if count > 0:
                doc_freq[term] += 1
    idf = {
        term: math.log(
            1 + (n_docs - doc_freq[term] + 0.5) / (doc_freq[term] + 0.5)
        )
        for term in query_terms
    }
    scores: list[float] = []
    for tf, dl in zip(tf_per_doc, doc_lens):
        score = 0.0
        for term in query_terms:
            f = tf[term]
            if f == 0:
                continue
            score += idf[term] * (f * (k1 + 1)) / (
                f + k1 * (1 - b + b * dl / avgdl)
            )
        scores.append(round(score, 4))
    return scores, doc_freq


def screen_relevance(candidates: list[dict], definition: str) -> list[dict]:
    """Score and gate candidate papers for topic relevance (no-LLM tier).

    Returns one verdict dict per candidate, in input order::

        {"kept": bool, "score": float, "tier": str, "reason": str}

    A paper is kept iff it contains at least one *distinctive* topic term
    (one appearing in fewer than ``_DISTINCTIVE_DF_RATIO`` of the batch).
    When the topic has no distinctive term in this batch (cold-start /
    uniform batch) every paper is kept and flagged ``relevance_unverified``.
    """
    n = len(candidates)
    docs = [
        ((c.get("abstract") or "") + " " + (c.get("title") or "")).lower()
        for c in candidates
    ]
    query_terms = extract_topic_terms(definition)
    if not query_terms or n == 0:
        return [
            {
                "kept": True,
                "score": 0.0,
                "tier": "cold-start",
                "reason": "relevance_unverified: topic has no usable terms",
            }
            for _ in range(n)
        ]
    if n < _MIN_BATCH_FOR_GATE:
        # Too few candidates for batch IDF to discriminate -- defer.
        return [
            {
                "kept": True,
                "score": 0.0,
                "tier": "cold-start",
                "reason": (
                    f"relevance_unverified: batch too small to screen "
                    f"({n} < {_MIN_BATCH_FOR_GATE})"
                ),
            }
            for _ in range(n)
        ]

    scores, doc_freq = bm25_scores(docs, query_terms)
    distinctive = {
        term
        for term in query_terms
        if 0 < doc_freq.get(term, 0) < _DISTINCTIVE_DF_RATIO * n
    }
    if not distinctive:
        # Uniform batch -- no term discriminates. Defer; never auto-reject.
        return [
            {
                "kept": True,
                "score": scores[i],
                "tier": "cold-start",
                "reason": (
                    "relevance_unverified: no distinctive topic term in batch"
                ),
            }
            for i in range(n)
        ]

    verdicts: list[dict] = []
    for i, doc in enumerate(docs):
        hits = sorted(t for t in distinctive if _count_term(doc, t) > 0)
        if hits:
            verdicts.append(
                {
                    "kept": True,
                    "score": scores[i],
                    "tier": "bm25",
                    "reason": "matched distinctive term(s): " + ", ".join(hits),
                }
            )
        else:
            verdicts.append(
                {
                    "kept": False,
                    "score": scores[i],
                    "tier": "bm25",
                    "reason": "no distinctive topic term matched",
                }
            )
    return verdicts


def parse_nlm_off_topic(briefing_md: str) -> list[str]:
    """Extract paper identifiers from the briefing's Off-topic section."""
    match = re.search(
        r"^###\s+Off-topic\s+papers\s*\n(.*?)(?=^##|\Z)",
        briefing_md,
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return []
    body = match.group(1).strip()
    if body.lower() in {"", "none", "none.", "(none)"}:
        return []

    titles: list[str] = []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^[-*]\s*", "", line)
        title = re.split(r"\s+(?:--|—|–)\s+", line, maxsplit=1)[0].strip()
        if title and title.lower() not in {"none", "none."}:
            titles.append(title)
    return titles


def drift_check(cfg, cluster_slug: str, threshold: int = 3) -> dict:
    """Emit a drift-check prompt against the current overview."""
    from research_hub.topic import get_topic_digest

    digest = get_topic_digest(cfg, cluster_slug)
    definition = _read_definition_from_overview(cfg, cluster_slug) or ""
    candidates = [
        {
            "title": paper.title,
            "doi": paper.doi,
            "abstract": paper.abstract,
            "year": paper.year,
            "authors": paper.authors,
        }
        for paper in digest.papers
    ]
    prompt = emit_prompt(cluster_slug, candidates, definition=definition)
    return {
        "cluster_slug": cluster_slug,
        "paper_count": len(candidates),
        "threshold": threshold,
        "prompt": prompt,
    }


def _extract_key_terms(definition: str) -> list[str]:
    stoplist = {
        "this",
        "that",
        "with",
        "from",
        "into",
        "about",
        "which",
        "their",
        "there",
        "where",
        "these",
        "those",
        "have",
        "been",
        "will",
        "would",
        "could",
        "should",
        "also",
        "such",
        "than",
    }
    seen: set[str] = set()
    terms: list[str] = []
    for word in re.findall(r"[A-Za-z][A-Za-z0-9-]{3,}", definition):
        lower = word.lower()
        if lower in stoplist or lower in seen:
            continue
        seen.add(lower)
        terms.append(lower)
        if len(terms) >= 12:
            break
    return terms


def _read_definition_from_overview(cfg, cluster_slug: str) -> str | None:
    from research_hub.topic import read_overview

    content = read_overview(cfg, cluster_slug)
    if not content:
        return None
    match = re.search(
        r"^##\s+Definition\s*\n(.*?)(?=^##\s|\Z)",
        content,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        return None
    text = re.sub(r"<!--.*?-->", "", match.group(1), flags=re.DOTALL).strip()
    return text or None


def _write_rejected_sidecar(
    cfg,
    cluster_slug: str,
    rejected: list[FitCheckResult],
    threshold: int,
) -> Path:
    from research_hub.topic import hub_cluster_dir

    target_dir = hub_cluster_dir(cfg, cluster_slug)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / ".fit_check_rejected.json"
    payload = {
        "cluster_slug": cluster_slug,
        "threshold": threshold,
        "rejected": [item.to_dict() for item in rejected],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _write_accepted_sidecar(
    cfg,
    cluster_slug: str,
    accepted: list[FitCheckResult],
    threshold: int,
) -> Path:
    from research_hub.topic import hub_cluster_dir

    target_dir = hub_cluster_dir(cfg, cluster_slug)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / ".fit_check_accepted.json"
    payload = {
        "cluster_slug": cluster_slug,
        "threshold": threshold,
        "accepted": [item.to_dict() for item in accepted],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def rejected_as_label_updates(cfg, cluster_slug: str) -> dict[str, list[str]]:
    """Apply deprecated labels to papers rejected by Gate 1 fit-check."""
    from research_hub.paper import apply_fit_check_to_labels

    return apply_fit_check_to_labels(cfg, cluster_slug)
