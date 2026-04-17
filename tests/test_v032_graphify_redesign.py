"""v0.32 Track D: graphify redesign tests."""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from types import SimpleNamespace

import pytest


def _make_cfg(tmp_path: Path):
    root = tmp_path / "vault"
    raw = root / "raw"
    research_hub_dir = root / ".research_hub"
    raw.mkdir(parents=True)
    research_hub_dir.mkdir(parents=True)
    return SimpleNamespace(
        root=root,
        raw=raw,
        research_hub_dir=research_hub_dir,
        clusters_file=research_hub_dir / "clusters.yaml",
    )


def test_use_graphify_emits_deprecation_warning(tmp_path):
    """import_folder(use_graphify=True, graphify_graph=None) warns and does nothing."""
    from research_hub.importer import import_folder

    src = tmp_path / "src"
    src.mkdir()
    (src / "n.md").write_text("# Note\n\nbody", encoding="utf-8")

    cfg = _make_cfg(tmp_path)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        report = import_folder(
            cfg,
            src,
            cluster_slug="dep-test",
            extensions=("md",),
            use_graphify=True,
        )

    assert any(
        "--use-graphify" in str(w.message) and "deprecated" in str(w.message).lower()
        for w in caught
    )
    assert report.imported_count == 1


def test_graphify_graph_path_assigns_subtopics(tmp_path):
    """A pre-built graph.json applies subtopics frontmatter to imported notes."""
    from research_hub.importer import import_folder

    src = tmp_path / "src"
    src.mkdir()
    file_a = src / "a.md"
    file_b = src / "b.md"
    file_a.write_text("# A\nbody", encoding="utf-8")
    file_b.write_text("# B\nbody", encoding="utf-8")

    graph = {
        "nodes": [
            {"id": "n1", "community": 0, "source_file": str(file_a.resolve())},
            {"id": "n2", "community": 0, "source_file": str(file_b.resolve())},
        ],
        "communities": {"0": "topic-x"},
    }
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")

    cfg = _make_cfg(tmp_path)

    report = import_folder(
        cfg,
        src,
        cluster_slug="graph-test",
        extensions=("md",),
        graphify_graph=graph_path,
    )

    assert report.imported_count == 2
    for entry in report.entries:
        assert entry.note_path is not None
        text = entry.note_path.read_text(encoding="utf-8")
        assert "topic-x" in text


def test_run_graphify_now_raises_with_actionable_message():
    """v0.32: run_graphify raises with the new 2-step workflow guidance."""
    from research_hub.graphify_bridge import GraphifyNotInstalled, run_graphify

    with pytest.raises(GraphifyNotInstalled) as excinfo:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            run_graphify(Path("/tmp/whatever"))

    msg = str(excinfo.value)
    assert "/graphify" in msg
    assert "--graphify-graph" in msg
