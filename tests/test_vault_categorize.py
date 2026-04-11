"""Tests for research_hub.vault.categorize helpers."""

from __future__ import annotations

import importlib
import json
import re
import sys
from pathlib import Path


def _import_categorize(tmp_path: Path, monkeypatch):
    from research_hub import config as hub_config

    root = tmp_path / "kb"
    raw = root / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    graph_path = root / ".obsidian" / "graph.json"
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "knowledge_base": {
                    "root": str(root),
                    "raw": str(raw),
                    "hub": str(root / "hub"),
                    "projects": str(root / "projects"),
                    "logs": str(root / "logs"),
                    "obsidian_graph": str(graph_path),
                }
            }
        ),
        encoding="utf-8",
    )

    hub_config._config = None
    monkeypatch.setattr(hub_config, "CONFIG_PATH", config_path)
    sys.modules.pop("research_hub.vault.categorize", None)
    return importlib.import_module("research_hub.vault.categorize")


def test_make_backup_creates_timestamped_copy(tmp_path, monkeypatch):
    categorize = _import_categorize(tmp_path, monkeypatch)
    graph_path = tmp_path / "graph.json"
    graph_path.write_text('{"colorGroups": []}', encoding="utf-8")

    backup = categorize.make_backup(graph_path)

    assert backup is not None
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == '{"colorGroups": []}'
    assert re.match(r"graph\.json\.bak\.\d+", backup.name)


def test_make_backup_returns_none_when_no_graph(tmp_path, monkeypatch):
    categorize = _import_categorize(tmp_path, monkeypatch)

    assert categorize.make_backup(tmp_path / "missing-graph.json") is None
