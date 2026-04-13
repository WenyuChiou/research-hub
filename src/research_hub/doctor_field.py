"""Field inference helper for doctor."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

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


def infer_field_from_notes(notes_dir: Path) -> tuple[str, dict[str, int]]:
    """Scan paper notes and return (best_field, score_map)."""
    if not notes_dir.exists():
        return "general", {}

    counts: Counter[str] = Counter()
    for note in notes_dir.glob("*.md"):
        text = note.read_text(encoding="utf-8", errors="ignore").lower()
        for field, signals in _FIELD_SIGNALS.items():
            counts[field] += sum(1 for sig in signals if sig in text)

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
        status = "ok" if declared == inferred or declared == "general" else "warn"
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
