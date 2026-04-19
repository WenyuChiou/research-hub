"""v0.43 - obsidian-bases tests."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import yaml

from research_hub.obsidian_bases import (
    ClusterBaseInputs,
    base_path_for_cluster,
    build_cluster_base,
    write_cluster_base,
)


def test_build_cluster_base_returns_valid_yaml():
    inputs = ClusterBaseInputs(cluster_slug="x", cluster_name="X")
    out = build_cluster_base(inputs)
    parsed = yaml.safe_load(out)
    assert parsed is not None
    assert "filters" in parsed
    assert "formulas" in parsed
    assert "views" in parsed


def test_build_cluster_base_has_4_views():
    inputs = ClusterBaseInputs(cluster_slug="x", cluster_name="X")
    parsed = yaml.safe_load(build_cluster_base(inputs))
    view_names = [v["name"] for v in parsed["views"]]
    assert view_names == ["Papers", "Crystals", "Open Questions", "Recent activity"]


def test_build_cluster_base_filters_use_topic_cluster():
    inputs = ClusterBaseInputs(cluster_slug="my-cluster", cluster_name="My")
    parsed = yaml.safe_load(build_cluster_base(inputs))
    top_filters = parsed["filters"]["and"]
    assert any('topic_cluster == "my-cluster"' in f for f in top_filters)


def test_build_cluster_base_includes_formulas():
    inputs = ClusterBaseInputs(cluster_slug="x", cluster_name="X")
    parsed = yaml.safe_load(build_cluster_base(inputs))
    formulas = parsed["formulas"]
    assert "days_since_ingested" in formulas
    assert "paper_count" in formulas


def test_build_cluster_base_papers_view_groups_by_year_desc():
    inputs = ClusterBaseInputs(cluster_slug="x", cluster_name="X")
    parsed = yaml.safe_load(build_cluster_base(inputs))
    papers_view = next(v for v in parsed["views"] if v["name"] == "Papers")
    assert papers_view["groupBy"]["property"] == "year"
    assert papers_view["groupBy"]["direction"] == "DESC"


def test_base_path_for_cluster(tmp_path):
    p = base_path_for_cluster(tmp_path / "hub", "test-cluster")
    assert p == tmp_path / "hub" / "test-cluster" / "test-cluster.base"


def test_write_cluster_base_creates_file(tmp_path):
    path, written = write_cluster_base(
        hub_root=tmp_path / "hub",
        cluster_slug="alpha",
        cluster_name="Alpha",
    )
    assert path.exists()
    assert written is True
    assert path.read_text(encoding="utf-8").startswith(("filters:", "---"))


def test_write_cluster_base_idempotent_unless_force(tmp_path):
    path, written1 = write_cluster_base(hub_root=tmp_path / "hub", cluster_slug="x", cluster_name="X")
    assert path.exists()
    assert written1 is True
    _, written2 = write_cluster_base(hub_root=tmp_path / "hub", cluster_slug="x", cluster_name="X")
    assert written2 is False
    _, written3 = write_cluster_base(hub_root=tmp_path / "hub", cluster_slug="x", cluster_name="X", force=True)
    assert written3 is True


def test_cli_bases_emit_stdout(monkeypatch, capsys):
    """CLI: research-hub bases emit --cluster X --stdout prints content."""
    from research_hub import cli as cli_module

    fake_cluster = MagicMock(slug="my-cluster", name="My Cluster", obsidian_subfolder="my-cluster")
    fake_cfg = MagicMock(hub=Path("/tmp/hub"), clusters_file=Path("/tmp/clusters.yaml"))

    monkeypatch.setattr(cli_module, "get_config", lambda: fake_cfg)
    fake_registry = MagicMock()
    fake_registry.get.return_value = fake_cluster
    monkeypatch.setattr(cli_module, "ClusterRegistry", lambda *a, **kw: fake_registry)

    rc = cli_module._bases_emit(cluster_slug="my-cluster", stdout=True, force=False)
    assert rc == 0
    out = capsys.readouterr().out
    assert "views:" in out


def test_cli_bases_emit_unknown_cluster(monkeypatch, capsys):
    from research_hub import cli as cli_module

    fake_cfg = MagicMock(hub=Path("/tmp/hub"), clusters_file=Path("/tmp/clusters.yaml"))
    monkeypatch.setattr(cli_module, "get_config", lambda: fake_cfg)
    fake_registry = MagicMock()
    fake_registry.get.return_value = None
    monkeypatch.setattr(cli_module, "ClusterRegistry", lambda *a, **kw: fake_registry)

    rc = cli_module._bases_emit(cluster_slug="nope", stdout=False, force=False)
    assert rc == 1
    out = capsys.readouterr().out
    assert "not found" in out.lower()


def test_mcp_emit_cluster_base(monkeypatch, tmp_path):
    """MCP tool returns structured dict."""
    from research_hub import mcp_server as m
    from tests._mcp_helpers import _get_mcp_tool

    fake_cluster = MagicMock(slug="x", name="X", obsidian_subfolder="x")
    fake_cfg = MagicMock(hub=tmp_path / "hub", clusters_file=tmp_path / "clusters.yaml")
    monkeypatch.setattr(m, "get_config", lambda: fake_cfg)

    fake_registry = MagicMock()
    fake_registry.get.return_value = fake_cluster
    monkeypatch.setattr("research_hub.clusters.ClusterRegistry", lambda *a, **kw: fake_registry)

    tool = _get_mcp_tool(m.mcp, "emit_cluster_base")
    result = tool.fn(cluster_slug="x")
    assert result["ok"] is True
    assert "x.base" in result["path"]
    assert result["bytes"] > 0
    assert result["action"] in {"created", "exists"}


def test_run_pipeline_refreshes_base_on_success(monkeypatch, tmp_path):
    from research_hub import pipeline

    cfg = SimpleNamespace(
        root=tmp_path,
        raw=tmp_path / "raw",
        hub=tmp_path / "hub",
        logs=tmp_path / "logs",
        research_hub_dir=tmp_path / ".research_hub",
        clusters_file=tmp_path / ".research_hub" / "clusters.yaml",
        zotero_default_collection="COLL",
        zotero_collections={"COLL": {"name": "Collection"}},
        zotero_library_id="123",
    )
    for path in (cfg.raw, cfg.hub, cfg.logs, cfg.research_hub_dir):
        path.mkdir(parents=True, exist_ok=True)
    (cfg.root / "papers_input.json").write_text("[]", encoding="utf-8")

    cluster = SimpleNamespace(
        slug="alpha",
        name="Alpha",
        obsidian_subfolder="alpha",
        zotero_collection_key="COLL",
        first_query="",
    )
    monkeypatch.setenv("RESEARCH_HUB_NO_ZOTERO", "1")
    monkeypatch.setattr(pipeline, "get_config", lambda: cfg)
    monkeypatch.setattr(
        pipeline,
        "ClusterRegistry",
        lambda path: SimpleNamespace(get=lambda slug: cluster if slug == "alpha" else None),
    )
    monkeypatch.setattr(pipeline, "_load_or_build_dedup", lambda *args, **kwargs: SimpleNamespace(save=lambda path: None))
    monkeypatch.setattr(pipeline, "Manifest", lambda path: SimpleNamespace(append=lambda entry: None))
    calls: list[dict] = []
    monkeypatch.setattr(
        "research_hub.obsidian_bases.write_cluster_base",
        lambda **kwargs: (calls.append(kwargs) or (Path(kwargs["hub_root"]) / kwargs["cluster_slug"] / "alpha.base", True)),
    )

    assert pipeline.run_pipeline(dry_run=False, cluster_slug="alpha", verify=False) == 0
    assert calls and calls[0]["cluster_slug"] == "alpha"
    assert calls[0]["force"] is True


def test_run_pipeline_base_refresh_failure_is_non_fatal(monkeypatch, tmp_path):
    from research_hub import pipeline

    cfg = SimpleNamespace(
        root=tmp_path,
        raw=tmp_path / "raw",
        hub=tmp_path / "hub",
        logs=tmp_path / "logs",
        research_hub_dir=tmp_path / ".research_hub",
        clusters_file=tmp_path / ".research_hub" / "clusters.yaml",
        zotero_default_collection="COLL",
        zotero_collections={"COLL": {"name": "Collection"}},
        zotero_library_id="123",
    )
    for path in (cfg.raw, cfg.hub, cfg.logs, cfg.research_hub_dir):
        path.mkdir(parents=True, exist_ok=True)
    (cfg.root / "papers_input.json").write_text("[]", encoding="utf-8")

    cluster = SimpleNamespace(
        slug="alpha",
        name="Alpha",
        obsidian_subfolder="alpha",
        zotero_collection_key="COLL",
        first_query="",
    )
    monkeypatch.setenv("RESEARCH_HUB_NO_ZOTERO", "1")
    monkeypatch.setattr(pipeline, "get_config", lambda: cfg)
    monkeypatch.setattr(
        pipeline,
        "ClusterRegistry",
        lambda path: SimpleNamespace(get=lambda slug: cluster if slug == "alpha" else None),
    )
    monkeypatch.setattr(pipeline, "_load_or_build_dedup", lambda *args, **kwargs: SimpleNamespace(save=lambda path: None))
    monkeypatch.setattr(pipeline, "Manifest", lambda path: SimpleNamespace(append=lambda entry: None))
    monkeypatch.setattr(
        "research_hub.obsidian_bases.write_cluster_base",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("no base")),
    )

    assert pipeline.run_pipeline(dry_run=False, cluster_slug="alpha", verify=False) == 0


def test_topic_build_refreshes_base(monkeypatch, tmp_path):
    from research_hub import topic

    cfg = SimpleNamespace(
        raw=tmp_path / "raw",
        hub=tmp_path / "hub",
        clusters_file=tmp_path / ".research_hub" / "clusters.yaml",
    )
    (cfg.raw / "alpha").mkdir(parents=True, exist_ok=True)
    cfg.hub.mkdir(parents=True, exist_ok=True)
    note = cfg.raw / "alpha" / "paper-a.md"
    note.write_text(
        "---\n"
        'title: "Paper A"\n'
        'authors: "Doe, Jane"\n'
        'year: "2024"\n'
        'doi: "10.1/a"\n'
        "subtopics:\n"
        "  - benchmarks\n"
        "---\n\n"
        "## Abstract\n\nA.\n",
        encoding="utf-8",
    )

    cluster = SimpleNamespace(slug="alpha", name="Alpha", obsidian_subfolder="alpha")
    monkeypatch.setattr(
        "research_hub.clusters.ClusterRegistry",
        lambda path: SimpleNamespace(get=lambda slug: cluster if slug == "alpha" else None),
    )
    calls: list[dict] = []
    monkeypatch.setattr(
        "research_hub.obsidian_bases.write_cluster_base",
        lambda **kwargs: (calls.append(kwargs) or (Path(kwargs["hub_root"]) / kwargs["cluster_slug"] / "alpha.base", True)),
    )

    written = topic.build_subtopic_notes(cfg, "alpha")

    assert written
    assert calls and calls[0]["cluster_slug"] == "alpha"
    assert calls[0]["force"] is True
