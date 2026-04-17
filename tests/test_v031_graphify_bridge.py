"""v0.31 Track C: graphify_bridge tests. All subprocess calls mocked."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

FIXTURE_GRAPH = Path(__file__).parent / "fixtures" / "graphify_graph_sample.json"


def test_find_graphify_binary_deprecated_returns_none(monkeypatch):
    """v0.32: find_graphify_binary is deprecated and always returns None.

    graphify is a coding-skill, not a standalone CLI — see audit_v0.31.md.
    """
    import warnings
    from research_hub.graphify_bridge import find_graphify_binary

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        assert find_graphify_binary() is None


def test_run_graphify_deprecated_raises_with_2step_workflow(monkeypatch, tmp_path):
    """v0.32: run_graphify always raises GraphifyNotInstalled with /graphify guidance."""
    import warnings
    from research_hub.graphify_bridge import GraphifyNotInstalled, run_graphify

    folder = tmp_path / "src"
    folder.mkdir()

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        with pytest.raises(GraphifyNotInstalled, match="graphify cannot be invoked"):
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


def test_run_graphify_v032_no_longer_invokes_subprocess(tmp_path):
    """v0.32: run_graphify no longer invokes subprocess at all (it always raises)."""
    import warnings
    from research_hub.graphify_bridge import run_graphify, GraphifyNotInstalled

    folder = tmp_path / "src"
    folder.mkdir()

    # Even when an output graph.json already exists from a prior run, v0.32's
    # run_graphify never tries to invoke subprocess — it just raises with
    # actionable guidance pointing at --graphify-graph PATH instead.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        with pytest.raises(GraphifyNotInstalled):
            run_graphify(folder)
