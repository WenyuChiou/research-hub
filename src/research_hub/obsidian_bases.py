"""Obsidian Bases (.base) generator for research-hub clusters.

A `.base` file is a YAML-defined database view that Obsidian renders
inside the vault. Each cluster gets one auto-generated `.base` with 4
views:

  1. "Papers" - table of cluster papers
  2. "Crystals" - pre-computed Q&A cards
  3. "Open Questions" - pulls open-questions section from overview
  4. "Recent activity" - most-recently ingested papers

Spec reference:
  - https://github.com/kepano/obsidian-skills/tree/main/skills/obsidian-bases
  - https://help.obsidian.md/bases/syntax

Adapted from kepano/obsidian-skills (MIT, by Steph Ango / Obsidian CEO).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ClusterBaseInputs:
    cluster_slug: str
    cluster_name: str
    obsidian_subfolder: str = ""


def _papers_view(cluster_slug: str) -> dict[str, Any]:
    return {
        "type": "table",
        "name": "Papers",
        "filters": {
            "and": [
                f'topic_cluster == "{cluster_slug}"',
                'file.ext == "md"',
            ],
        },
        "order": ["file.name", "title", "year", "status", "verified", "doi"],
        "groupBy": {"property": "year", "direction": "DESC"},
    }


def _crystals_view(cluster_slug: str) -> dict[str, Any]:
    return {
        "type": "cards",
        "name": "Crystals",
        "filters": {
            "and": [
                'type == "crystal"',
                f'cluster == "{cluster_slug}"',
            ],
        },
        "order": ["question", "confidence", "based_on_paper_count", "last_generated"],
    }


def _open_questions_view(cluster_slug: str) -> dict[str, Any]:
    return {
        "type": "table",
        "name": "Open Questions",
        "filters": {
            "and": [
                'type == "topic-overview"',
                f'cluster == "{cluster_slug}"',
            ],
        },
        "order": ["file.name", "title", "status"],
    }


def _recent_activity_view(cluster_slug: str) -> dict[str, Any]:
    return {
        "type": "table",
        "name": "Recent activity",
        "filters": {
            "and": [
                f'topic_cluster == "{cluster_slug}"',
                "ingested_at != null",
            ],
        },
        "order": ["ingested_at", "title", "status"],
        "limit": 10,
    }


def build_cluster_base(inputs: ClusterBaseInputs) -> str:
    """Return a `.base` YAML string for the given cluster."""
    payload: dict[str, Any] = {
        "filters": {
            "and": [f'topic_cluster == "{inputs.cluster_slug}"'],
        },
        "formulas": {
            "days_since_ingested": "if(ingested_at, (today() - date(ingested_at)).days, '')",
            "paper_count": 'count(file.where(topic_cluster == "' + inputs.cluster_slug + '"))',
        },
        "views": [
            _papers_view(inputs.cluster_slug),
            _crystals_view(inputs.cluster_slug),
            _open_questions_view(inputs.cluster_slug),
            _recent_activity_view(inputs.cluster_slug),
        ],
    }
    return yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)


def base_path_for_cluster(hub_root: Path, cluster_slug: str) -> Path:
    """Return ``<hub>/<slug>/<slug>.base``."""
    return hub_root / cluster_slug / (cluster_slug + ".base")


def write_cluster_base(
    hub_root: Path,
    cluster_slug: str,
    cluster_name: str,
    *,
    obsidian_subfolder: str = "",
    force: bool = False,
) -> tuple[Path, bool]:
    """Write the cluster's `.base` to disk."""
    path = base_path_for_cluster(hub_root, cluster_slug)
    if path.exists() and not force:
        return path, False
    path.parent.mkdir(parents=True, exist_ok=True)
    inputs = ClusterBaseInputs(
        cluster_slug=cluster_slug,
        cluster_name=cluster_name,
        obsidian_subfolder=obsidian_subfolder or cluster_slug,
    )
    content = build_cluster_base(inputs)
    path.write_text(content, encoding="utf-8")
    return path, True
