"""v0.31 Track C: graphify_bridge tests. All subprocess calls mocked."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

FIXTURE_GRAPH = Path(__file__).parent / "fixtures" / "graphify_graph_sample.json"


def test_find_graphify_binary_returns_path_when_installed(monkeypatch):
    """find_graphify_binary returns the graphify path when it is installed."""
    from research_hub.graphify_bridge import find_graphify_binary

    monkeypatch.setattr(
        shutil,
        "which",
        lambda name: "/fake/path/to/graphify" if name == "graphify" else None,
    )

    assert find_graphify_binary() == "/fake/path/to/graphify"


def test_run_graphify_raises_when_binary_missing(monkeypatch, tmp_path):
    """run_graphify raises GraphifyNotInstalled with an actionable message."""
    from research_hub.graphify_bridge import GraphifyNotInstalled, run_graphify

    monkeypatch.setattr(shutil, "which", lambda name: None)
    folder = tmp_path / "src"
    folder.mkdir()

    with pytest.raises(GraphifyNotInstalled, match="graphify CLI not found"):
        run_graphify(folder)


def test_parse_graphify_communities_groups_files_by_community():
    """parse_graphify_communities groups files under named or fallback labels."""
    from research_hub.graphify_bridge import parse_graphify_communities

    result = parse_graphify_communities(FIXTURE_GRAPH)

    assert "topic-alpha" in result
    assert "topic-beta" in result
    assert "community-2" in result
    assert "/abs/path/note1.md" in result["topic-alpha"]
    assert "/abs/path/note2.md" in result["topic-alpha"]
    assert "/abs/path/note3.md" in result["topic-beta"]


def test_map_to_subtopics_matches_imported_files(tmp_path):
    """map_to_subtopics assigns imported files to matching communities."""
    from research_hub.graphify_bridge import map_to_subtopics

    note1 = tmp_path / "note1.md"
    note3 = tmp_path / "note3.md"
    note1.write_text("a", encoding="utf-8")
    note3.write_text("b", encoding="utf-8")

    communities = {
        "topic-alpha": [str(note1)],
        "topic-beta": [str(note3)],
    }

    assignments = map_to_subtopics(communities, [note1, note3])

    assert assignments[str(note1)] == ["topic-alpha"]
    assert assignments[str(note3)] == ["topic-beta"]


def test_run_graphify_subprocess_invocation(monkeypatch, tmp_path):
    """run_graphify returns the expected graph.json path after success."""
    from research_hub.graphify_bridge import run_graphify

    monkeypatch.setattr(shutil, "which", lambda name: "graphify")

    folder = tmp_path / "src"
    folder.mkdir()
    (folder / "note.md").write_text("x", encoding="utf-8")

    out_dir = folder / "graphify-out"
    out_dir.mkdir()
    expected_graph = out_dir / "graph.json"
    expected_graph.write_text(json.dumps({"nodes": [], "edges": []}), encoding="utf-8")

    fake_proc = MagicMock(returncode=0, stdout="ok", stderr="")
    with patch("research_hub.graphify_bridge.subprocess.run", return_value=fake_proc):
        result = run_graphify(folder)

    assert result == expected_graph
