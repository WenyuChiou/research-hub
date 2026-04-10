"""Tests for graph.json backup logic."""

import re
import shutil
import time
from pathlib import Path


def make_backup(graph_path: Path) -> Path | None:
    """Backup graph.json to graph.json.bak.<epoch>. Returns backup path or None."""
    if not graph_path.exists():
        return None
    epoch = int(time.time())
    backup = graph_path.parent / f"graph.json.bak.{epoch}"
    shutil.copy2(str(graph_path), str(backup))
    return backup


def test_backup_created_when_graph_exists(tmp_path):
    graph = tmp_path / "graph.json"
    graph.write_text('{"colorGroups": []}', encoding="utf-8")

    backup = make_backup(graph)

    assert backup is not None
    assert backup.exists()
    assert re.match(r"graph\.json\.bak\.\d+", backup.name)


def test_backup_has_same_content(tmp_path):
    graph = tmp_path / "graph.json"
    content = '{"colorGroups": [{"query": "tag:#flood"}]}'
    graph.write_text(content, encoding="utf-8")

    backup = make_backup(graph)
    assert backup.read_text(encoding="utf-8") == content


def test_no_backup_when_graph_missing(tmp_path):
    graph = tmp_path / "graph.json"
    backup = make_backup(graph)
    assert backup is None


def test_backup_does_not_overwrite_original(tmp_path):
    graph = tmp_path / "graph.json"
    graph.write_text("original", encoding="utf-8")

    make_backup(graph)
    assert graph.read_text(encoding="utf-8") == "original"
