"""Tests for vault.graph_config cluster graph coloring."""

from __future__ import annotations

import json
from pathlib import Path

from research_hub.vault.graph_config import (
    PALETTE,
    _hex_to_int_rgb,
    build_color_groups,
    update_from_clusters_file,
    update_graph_json,
)


def test_hex_to_int_rgb_known_values():
    assert _hex_to_int_rgb("#ffffff") == (255 << 16) | (255 << 8) | 255
    assert _hex_to_int_rgb("#000000") == 0
    assert _hex_to_int_rgb("#ff0000") == 255 << 16


def test_build_color_groups_one_per_cluster():
    groups = build_color_groups(["alpha", "beta", "gamma"])
    assert len(groups) == 3
    assert all("query" in group and "color" in group for group in groups)
    assert groups[0]["query"] == "path:raw/alpha/"
    assert groups[1]["color"]["rgb"] != groups[0]["color"]["rgb"]


def test_build_color_groups_cycles_palette():
    clusters = [f"c{i}" for i in range(len(PALETTE) + 2)]
    groups = build_color_groups(clusters)
    assert len(groups) == len(clusters)
    assert groups[0]["color"]["rgb"] == groups[len(PALETTE)]["color"]["rgb"]


def test_update_graph_json_missing_file_skips(tmp_path: Path):
    report = update_graph_json(tmp_path / "missing.json", ["alpha"])
    assert report.updated is False
    assert "No graph.json" in report.skipped_reason


def test_update_graph_json_preserves_other_keys(tmp_path: Path):
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(
        json.dumps(
            {
                "zoom": 0.8,
                "showAttachments": False,
                "colorGroups": [{"query": "old", "color": {"a": 1, "rgb": 0}}],
            }
        ),
        encoding="utf-8",
    )
    report = update_graph_json(graph_path, ["alpha", "beta"])
    assert report.updated is True
    assert report.color_groups_written == 2
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    assert data["zoom"] == 0.8
    assert data["showAttachments"] is False
    assert len(data["colorGroups"]) == 2
    assert data["colorGroups"][0]["query"] == "path:raw/alpha/"


def test_update_graph_json_idempotent(tmp_path: Path):
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps({"zoom": 1.0}), encoding="utf-8")
    update_graph_json(graph_path, ["alpha"])
    first = graph_path.read_text(encoding="utf-8")
    update_graph_json(graph_path, ["alpha"])
    second = graph_path.read_text(encoding="utf-8")
    assert first == second


def test_update_from_clusters_file_reads_registry(tmp_path: Path):
    vault_root = tmp_path / "vault"
    graph_path = vault_root / ".obsidian" / "graph.json"
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    graph_path.write_text(json.dumps({"zoom": 1.0}), encoding="utf-8")
    clusters_file = tmp_path / "clusters.yaml"
    clusters_file.write_text(
        "clusters:\n"
        "  alpha:\n"
        "    name: Alpha\n"
        "    first_query: alpha\n"
        "  beta:\n"
        "    name: Beta\n"
        "    first_query: beta\n",
        encoding="utf-8",
    )
    report = update_from_clusters_file(vault_root, clusters_file)
    assert report.updated is True
    assert report.cluster_slugs == ["alpha", "beta"]
