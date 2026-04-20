"""Field inference helper for doctor.

v0.54: tightened the keyword matcher so common words like "cell" don't
match "cell phone" or "household cell" anymore. Now uses word-boundary
regex + a confidence floor before raising a warning.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

# v0.54: confidence below this threshold means the classifier itself is
# unsure -- don't surface a warning. Empirically 0.45 was triggering on
# every mixed-discipline cluster (e.g. flood/social/health surveys). 0.6
# matches "more than half the signal points one way".
_CONFIDENCE_THRESHOLD = 0.6

_FIELD_SIGNALS: dict[str, list[str]] = {
    "cs": [
        "arxiv",
        "icse",
        "fse",
        "neurips",
        "iclr",
        "icml",
        "acl",
        "cvpr",
        "swe",
        "llm",
        "compiler",
        "software",
    ],
    "bio": ["biorxiv", "nature", "cell", "plos", "molecular", "genome", "protein", "rna", "dna"],
    "med": ["jama", "lancet", "nejm", "bmj", "pubmed", "clinical", "patient", "trial"],
    "physics": ["physical review", "physics", "quantum", "particle", "phys. rev."],
    "math": ["mathematics", "geometric", "topology", "algebra"],
    "astro": ["nasa", "astronomical", "astrophysical", "ads", "galaxy", "stellar", "cosmolog"],
    "chem": ["chemrxiv", "chemistry", "molecular", "synthesis", "catalysis"],
    "social": ["sociology", "social", "economic", "political", "ssrn", "repec"],
    "econ": ["economics", "ssrn", "repec", "nber", "journal of economic"],
    "edu": ["education", "eric", "learning", "teaching", "pedagog"],
}

# Pre-compile a word-boundary regex per signal so substring matches like
# "cell" inside "cellular" or "cell phone surveys" don't inflate bio scores.
_SIGNAL_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    field: [re.compile(rf"\b{re.escape(sig)}\b", re.IGNORECASE) for sig in signals]
    for field, signals in _FIELD_SIGNALS.items()
}


def infer_field_from_notes(notes_dir: Path) -> tuple[str, dict[str, int]]:
    """Scan paper notes and return (best_field, score_map).

    v0.54: counts whole-word matches only (regex \\b boundary) so common
    English words don't bleed into other fields' scores.
    """
    if not notes_dir.exists():
        return "general", {}

    counts: Counter[str] = Counter()
    for note in notes_dir.glob("*.md"):
        text = note.read_text(encoding="utf-8", errors="ignore")
        for field, patterns in _SIGNAL_PATTERNS.items():
            for pat in patterns:
                counts[field] += len(pat.findall(text))

    if not counts or max(counts.values()) <= 0:
        return "general", {}
    return counts.most_common(1)[0][0], dict(counts)


def _infer_declared_field(seed_keywords: list[str]) -> str:
    if not seed_keywords:
        return "general"

    text = " ".join(seed_keywords).lower()
    counts: Counter[str] = Counter()
    for field, signals in _FIELD_SIGNALS.items():
        for sig in signals:
            if sig in text:
                counts[field] += 1
    if not counts:
        return "general"
    return counts.most_common(1)[0][0]


def field_inference_check(cfg) -> list[dict[str, Any]]:
    """Infer cluster field from note contents and compare against seed keywords."""
    from research_hub.clusters import ClusterRegistry

    registry = ClusterRegistry(cfg.clusters_file)
    reports: list[dict[str, Any]] = []
    for cluster in registry.list():
        inferred, scores = infer_field_from_notes(Path(cfg.raw) / cluster.slug)
        declared = _infer_declared_field(cluster.seed_keywords)
        total_signal = sum(scores.values())
        confidence = 0.0
        if total_signal > 0:
            confidence = scores.get(inferred, 0) / total_signal
        # v0.54: only warn if the classifier is reasonably confident
        # (>= 0.6) AND the declared field disagrees. Below the floor the
        # classifier is essentially guessing — typical for mixed-discipline
        # clusters like flood/social/health surveys.
        if declared == inferred or declared == "general":
            status = "ok"
        elif confidence < _CONFIDENCE_THRESHOLD:
            status = "ok"
        else:
            status = "warn"
        reports.append(
            {
                "cluster_slug": cluster.slug,
                "declared_field": declared,
                "inferred_field": inferred,
                "confidence": round(confidence, 2),
                "signal_total": total_signal,
                "status": status,
            }
        )
    return reports
