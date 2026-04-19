"""v0.43 - obsidian-bases tests."""
from __future__ import annotations

from pathlib import Path
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
