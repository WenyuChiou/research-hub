"""Obsidian graph.json cluster color updater.

Read the vault's ``.obsidian/graph.json`` and apply one color group per
topic cluster so graph view can distinguish research lines. Existing
graph settings are preserved.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


PALETTE = [
    "#e6194B",
    "#3cb44b",
    "#ffe119",
    "#4363d8",
    "#f58231",
    "#911eb4",
    "#42d4f4",
    "#f032e6",
]


@dataclass
class GraphConfigUpdate:
    """Report for a graph.json update attempt."""

    updated: bool = False
    color_groups_written: int = 0
    skipped_reason: str = ""
    cluster_slugs: list[str] = field(default_factory=list)


def _hex_to_int_rgb(hex_color: str) -> int:
    """Convert ``#RRGGBB`` to Obsidian's integer RGB format."""

    clean = hex_color.lstrip("#")
    red = int(clean[0:2], 16)
    green = int(clean[2:4], 16)
    blue = int(clean[4:6], 16)
    return (red << 16) | (green << 8) | blue


def _obsidian_color(hex_color: str) -> dict[str, int]:
    """Return an Obsidian color object."""

    return {"a": 1, "rgb": _hex_to_int_rgb(hex_color)}


def build_color_groups(cluster_slugs: list[str]) -> list[dict[str, object]]:
    """Build one deterministic color group per cluster slug."""

    groups: list[dict[str, object]] = []
    for index, slug in enumerate(cluster_slugs):
        groups.append(
            {
                "query": f"path:raw/{slug}/",
                "color": _obsidian_color(PALETTE[index % len(PALETTE)]),
            }
        )
    return groups


def update_graph_json(graph_json_path: Path, cluster_slugs: list[str]) -> GraphConfigUpdate:
    """Update ``colorGroups`` in graph.json while preserving other settings."""

    if not graph_json_path.exists():
        return GraphConfigUpdate(skipped_reason=f"No graph.json at {graph_json_path}")

    try:
        existing = json.loads(graph_json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        existing = {}

    if not isinstance(existing, dict):
        existing = {}

    ordered_slugs = list(cluster_slugs)
    existing["colorGroups"] = build_color_groups(ordered_slugs)
    graph_json_path.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return GraphConfigUpdate(
        updated=True,
        color_groups_written=len(ordered_slugs),
        cluster_slugs=ordered_slugs,
    )


def update_from_clusters_file(vault_root: Path, clusters_file: Path) -> GraphConfigUpdate:
    """Load cluster slugs from the registry and update ``graph.json``."""

    from research_hub.clusters import ClusterRegistry

    registry = ClusterRegistry(clusters_file)
    slugs = [cluster.slug for cluster in registry.list()]
    graph_path = vault_root / ".obsidian" / "graph.json"
    return update_graph_json(graph_path, slugs)
