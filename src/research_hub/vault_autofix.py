"""Mechanical frontmatter backfills for existing vault notes."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from research_hub.clusters import ClusterRegistry
from research_hub.paper import _parse_frontmatter, _rewrite_paper_frontmatter

_ARXIV_SLUG_RE = re.compile(r"(\d{4}\.\d{4,6})(?:v\d+)?")


def run_autofix(cfg) -> dict[str, int]:
    registry = ClusterRegistry(cfg.clusters_file)
    folder_to_cluster = {
        (cluster.obsidian_subfolder or cluster.slug): cluster.slug
        for cluster in registry.list()
    }
    summary = {
        "topic_cluster": 0,
        "ingested_at": 0,
        "doi_derived": 0,
        "skipped_no_cluster": 0,
    }

    for note_path in sorted(Path(cfg.raw).rglob("*.md")):
        if note_path.name.startswith("00_") or note_path.name.startswith("index"):
            continue
        if "topics" in note_path.parts:
            continue

        meta = _parse_frontmatter(note_path.read_text(encoding="utf-8"))
        updates: dict[str, object] = {}
        folder_name = note_path.parent.name
        cluster_slug = folder_to_cluster.get(folder_name)

        topic_cluster = str(meta.get("topic_cluster", "") or "").strip()
        if not topic_cluster:
            if cluster_slug:
                updates["topic_cluster"] = cluster_slug
                summary["topic_cluster"] += 1
            else:
                summary["skipped_no_cluster"] += 1

        if not str(meta.get("ingested_at", "") or "").strip():
            mtime = datetime.fromtimestamp(note_path.stat().st_mtime, tz=timezone.utc)
            updates["ingested_at"] = mtime.strftime("%Y-%m-%dT%H:%M:%SZ")
            summary["ingested_at"] += 1

        if not str(meta.get("doi", "") or "").strip():
            match = _ARXIV_SLUG_RE.search(note_path.stem)
            if match:
                updates["doi"] = f"10.48550/arxiv.{match.group(1)}"
                summary["doi_derived"] += 1

        if updates:
            _rewrite_paper_frontmatter(note_path, updates)

    return summary
