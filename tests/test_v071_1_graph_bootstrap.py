from __future__ import annotations

import json
from pathlib import Path

from research_hub.vault.graph_config import (
    build_all_color_groups,
    update_graph_json,
)


def test_update_graph_json_creates_file_when_missing(tmp_path: Path):
    graph_path = tmp_path / ".obsidian" / "graph.json"

    report = update_graph_json(graph_path, ["alpha", "beta"])

    assert report.updated is True
    assert report.created is True
    assert graph_path.exists()
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    queries = [group["query"] for group in data["colorGroups"]]
    assert "path:raw/alpha/" in queries
    assert "path:raw/beta/" in queries
    assert "tag:#label/seed" in queries
    assert "tag:#label/archived" in queries
    assert report.color_groups_written == len(data["colorGroups"])


def test_update_graph_json_creates_parent_dir_when_missing(tmp_path: Path):
    graph_path = tmp_path / "vault" / ".obsidian" / "graph.json"

    report = update_graph_json(graph_path, ["alpha"])

    assert report.created is True
    assert graph_path.parent.is_dir()
    assert graph_path.is_file()


def test_update_graph_json_preserves_existing_file_behavior(tmp_path: Path):
    graph_path = tmp_path / ".obsidian" / "graph.json"
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    graph_path.write_text(
        json.dumps(
            {
                "showTags": False,
                "colorGroups": [
                    {"query": "tag:#custom", "color": {"a": 1, "rgb": 123}},
                    {"query": "path:raw/old/", "color": {"a": 1, "rgb": 456}},
                    {"query": "tag:#label/seed", "color": {"a": 1, "rgb": 789}},
                ],
            }
        ),
        encoding="utf-8",
    )

    report = update_graph_json(graph_path, ["alpha"])

    assert report.updated is True
    assert report.created is False
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    queries = [group["query"] for group in data["colorGroups"]]
    assert "tag:#custom" in queries
    assert "path:raw/old/" not in queries
    assert queries.count("tag:#label/seed") == 1
    assert report.color_groups_written == len(build_all_color_groups(["alpha"]))


def test_init_wizard_bootstraps_graph_json(tmp_path: Path, monkeypatch, capsys):
    from research_hub import init_wizard

    vault = tmp_path / "vault"
    config_dir = tmp_path / "config"
    monkeypatch.setattr(
        init_wizard.platformdirs,
        "user_config_dir",
        lambda *args, **kwargs: str(config_dir),
    )
    monkeypatch.setattr(
        init_wizard,
        "_check_first_run_readiness",
        lambda vault, *, persona, has_zotero: [("chrome", "OK", "patchright can launch Chrome")],
    )

    assert init_wizard.run_init(vault_root=str(vault), non_interactive=True) == 0

    graph_path = vault / ".obsidian" / "graph.json"
    assert graph_path.exists()
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    assert data["colorGroups"]
    assert all(group["query"].startswith("tag:#label/") for group in data["colorGroups"])
    assert "[init] Wrote .obsidian/graph.json" in capsys.readouterr().out


def test_init_wizard_bootstrap_failure_does_not_abort_init(tmp_path: Path, monkeypatch, capsys):
    from research_hub import init_wizard

    vault = tmp_path / "vault"
    config_dir = tmp_path / "config"
    monkeypatch.setattr(
        init_wizard.platformdirs,
        "user_config_dir",
        lambda *args, **kwargs: str(config_dir),
    )
    monkeypatch.setattr(
        init_wizard,
        "update_from_clusters_file",
        lambda vault_root, clusters_file: (_ for _ in ()).throw(OSError("disk full")),
    )
    monkeypatch.setattr(
        init_wizard,
        "_check_first_run_readiness",
        lambda vault, *, persona, has_zotero: [("chrome", "OK", "patchright can launch Chrome")],
    )

    assert init_wizard.run_init(vault_root=str(vault), non_interactive=True) == 0

    captured = capsys.readouterr()
    assert "[init] WARN could not write .obsidian/graph.json: disk full" in captured.err
