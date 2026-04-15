"""Obsidian graph.json cluster color updater.

Read the vault's ``.obsidian/graph.json`` and apply one color group per
topic cluster so graph view can distinguish research lines. Existing
graph settings are preserved.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from research_hub.paper import CANONICAL_LABELS


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

LABEL_PALETTE = {
    "seed": "#d7263d",
    "core": "#f28f3b",
    "method": "#2e86de",
    "benchmark": "#7d5ba6",
    "survey": "#1b9aaa",
    "application": "#2a9d8f",
    "tangential": "#8d99ae",
    "deprecated": "#5c677d",
    "archived": "#2b2d42",
}

LABEL_ORDER = [
    "seed",
    "core",
    "method",
    "benchmark",
    "survey",
    "application",
    "tangential",
    "deprecated",
    "archived",
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


def build_label_color_groups(
    label_palette: dict[str, str] | None = None,
) -> list[dict[str, object]]:
    """Build one deterministic color group per canonical paper label."""

    palette = label_palette or LABEL_PALETTE
    return [
        {
            "query": f"tag:#label/{label}",
            "color": _obsidian_color(palette[label]),
        }
        for label in LABEL_ORDER
        if label in CANONICAL_LABELS
    ]


def build_all_color_groups(cluster_slugs: list[str]) -> list[dict[str, object]]:
    """Build both cluster-path and label-tag graph color groups."""

    return build_color_groups(cluster_slugs) + build_label_color_groups()


def _is_managed_query(query: object) -> bool:
    if not isinstance(query, str):
        return False
    return (
        query.startswith("path:raw/")
        or query.startswith('path:"raw/')
        or query.startswith("tag:#label/")
    )


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
    managed_groups = build_color_groups(ordered_slugs)
    existing["colorGroups"] = managed_groups
    rendered = json.dumps(existing, ensure_ascii=False, indent=2) + "\n"
    current = graph_json_path.read_text(encoding="utf-8")
    if current != rendered:
        graph_json_path.write_text(rendered, encoding="utf-8")
        updated = True
    else:
        updated = False
    return GraphConfigUpdate(
        updated=updated,
        color_groups_written=len(managed_groups),
        cluster_slugs=ordered_slugs,
    )


def update_from_clusters_file(vault_root: Path, clusters_file: Path) -> GraphConfigUpdate:
    """Load cluster slugs from the registry and update ``graph.json``."""

    from research_hub.clusters import ClusterRegistry

    registry = ClusterRegistry(clusters_file)
    slugs = [cluster.slug for cluster in registry.list()]
    graph_path = vault_root / ".obsidian" / "graph.json"
    return update_graph_json(graph_path, slugs)


def refresh_graph_from_vault(cfg) -> int:
    """Rebuild BOTH cluster + label color groups from current vault state.

    Reads clusters.yaml, produces color groups, writes to .obsidian/graph.json.
    Preserves any user-authored color groups whose queries don't start with
    'path:"raw/' or 'tag:#label/'.

    Returns total number of research-hub-managed groups written.
    """

    from research_hub.clusters import ClusterRegistry

    registry = ClusterRegistry(Path(cfg.clusters_file))
    slugs = [cluster.slug for cluster in registry.list()]
    graph_json_path = Path(cfg.root) / ".obsidian" / "graph.json"
    if not graph_json_path.exists():
        return 0
    try:
        existing = json.loads(graph_json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        existing = {}
    if not isinstance(existing, dict):
        existing = {}
    managed_groups = build_all_color_groups(slugs)
    preserved_groups = [
        group
        for group in (existing.get("colorGroups") or [])
        if isinstance(group, dict) and not _is_managed_query(group.get("query"))
    ]
    existing["colorGroups"] = managed_groups + preserved_groups
    rendered = json.dumps(existing, ensure_ascii=False, indent=2) + "\n"
    if graph_json_path.read_text(encoding="utf-8") != rendered:
        graph_json_path.write_text(rendered, encoding="utf-8")
    return len(managed_groups)
