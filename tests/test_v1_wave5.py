"""Wave 5: F3b (cluster groups) + F4b (cross-cluster gap analysis)."""
from __future__ import annotations

import io
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cfg(tmp_path: Path) -> SimpleNamespace:
    raw = tmp_path / "raw"
    raw.mkdir()
    research_hub_dir = tmp_path / ".research_hub"
    research_hub_dir.mkdir()
    return SimpleNamespace(
        raw=raw,
        root=tmp_path,
        clusters_file=tmp_path / "clusters.yaml",
        research_hub_dir=research_hub_dir,
    )


def _write_clusters_yaml(tmp_path: Path, clusters: list[dict]) -> None:
    """Write a minimal clusters.yaml with optional group fields."""
    import yaml

    payload = {
        "schema_version": "1.0",
        "clusters": {
            c["slug"]: {k: v for k, v in c.items() if k != "slug"}
            for c in clusters
        },
    }
    (tmp_path / "clusters.yaml").write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _write_paper(cluster_dir: Path, stem: str, **kwargs) -> None:
    cluster_dir.mkdir(parents=True, exist_ok=True)
    title = kwargs.get("title", stem)
    doi = kwargs.get("doi", "")
    year = kwargs.get("year", 2022)
    abstract = kwargs.get("abstract", "")
    fm = (
        f"---\ntitle: {title}\ndoi: {doi}\nyear: {year}\nabstract: {abstract}\n---\n\n"
        f"# {title}\n"
    )
    (cluster_dir / f"{stem}.md").write_text(fm, encoding="utf-8")


# ---------------------------------------------------------------------------
# F3b — Cluster.group field
# ---------------------------------------------------------------------------


def test_cluster_group_field_has_empty_default() -> None:
    """Cluster.group defaults to empty string."""
    from research_hub.clusters import Cluster

    c = Cluster(slug="floods", name="Floods")
    assert c.group == ""


def test_cluster_group_persists_through_yaml_roundtrip(tmp_path: Path) -> None:
    """group field survives save → load cycle."""
    from research_hub.clusters import ClusterRegistry

    _write_clusters_yaml(tmp_path, [
        {"slug": "floods", "name": "Floods", "group": "water-resources"},
        {"slug": "llm-agents", "name": "LLM Agents", "group": ""},
    ])
    registry = ClusterRegistry(tmp_path / "clusters.yaml")
    assert registry.get("floods").group == "water-resources"
    assert registry.get("llm-agents").group == ""


def test_cluster_group_missing_from_yaml_defaults_empty(tmp_path: Path) -> None:
    """Old YAML without group field: group defaults to ''."""
    from research_hub.clusters import ClusterRegistry

    _write_clusters_yaml(tmp_path, [
        {"slug": "floods", "name": "Floods"},  # no group key
    ])
    registry = ClusterRegistry(tmp_path / "clusters.yaml")
    cluster = registry.get("floods")
    assert cluster.group == ""


# ---------------------------------------------------------------------------
# F3b — clusters set-group CLI
# ---------------------------------------------------------------------------


def test_clusters_set_group_saves_to_registry(tmp_path: Path) -> None:
    """_clusters_set_group writes the group to clusters.yaml and prints confirmation."""
    from research_hub.cli import _clusters_set_group
    from research_hub.clusters import ClusterRegistry

    _write_clusters_yaml(tmp_path, [{"slug": "floods", "name": "Floods"}])

    with patch("research_hub.cli.get_config") as mock_cfg:
        mock_cfg.return_value = SimpleNamespace(
            clusters_file=tmp_path / "clusters.yaml"
        )
        captured = io.StringIO()
        with patch("sys.stdout", captured):
            rc = _clusters_set_group("floods", "water-resources")

    assert rc == 0
    assert "water-resources" in captured.getvalue()

    # Verify persisted
    registry = ClusterRegistry(tmp_path / "clusters.yaml")
    assert registry.get("floods").group == "water-resources"


def test_clusters_set_group_clears_when_empty_string(tmp_path: Path) -> None:
    """_clusters_set_group with '' clears the group field."""
    from research_hub.cli import _clusters_set_group
    from research_hub.clusters import ClusterRegistry

    _write_clusters_yaml(tmp_path, [
        {"slug": "floods", "name": "Floods", "group": "water-resources"}
    ])

    with patch("research_hub.cli.get_config") as mock_cfg:
        mock_cfg.return_value = SimpleNamespace(
            clusters_file=tmp_path / "clusters.yaml"
        )
        rc = _clusters_set_group("floods", "")

    assert rc == 0
    registry = ClusterRegistry(tmp_path / "clusters.yaml")
    assert registry.get("floods").group == ""


def test_clusters_set_group_missing_slug_returns_1(tmp_path: Path) -> None:
    """_clusters_set_group returns 1 when slug not found."""
    from research_hub.cli import _clusters_set_group

    _write_clusters_yaml(tmp_path, [])

    with patch("research_hub.cli.get_config") as mock_cfg:
        mock_cfg.return_value = SimpleNamespace(
            clusters_file=tmp_path / "clusters.yaml"
        )
        captured_err = io.StringIO()
        with patch("sys.stderr", captured_err):
            rc = _clusters_set_group("nonexistent", "some-group")

    assert rc == 1
    assert "not found" in captured_err.getvalue()


# ---------------------------------------------------------------------------
# F3b — clusters list grouped output
# ---------------------------------------------------------------------------


def test_clusters_list_grouped_shows_headers(tmp_path: Path, capsys) -> None:
    """_clusters_list prints group headers when groups are set."""
    from research_hub.cli import _clusters_list

    _write_clusters_yaml(tmp_path, [
        {"slug": "floods", "name": "Floods", "group": "water"},
        {"slug": "llm-agents", "name": "LLM Agents", "group": "ai"},
        {"slug": "policy", "name": "Policy", "group": ""},
    ])

    with patch("research_hub.cli.get_config") as mock_cfg:
        mock_cfg.return_value = SimpleNamespace(
            clusters_file=tmp_path / "clusters.yaml"
        )
        _clusters_list()

    out = capsys.readouterr().out
    assert "[ai]" in out
    assert "[water]" in out
    # ungrouped at end
    assert "(ungrouped)" in out
    # named groups before ungrouped in output
    assert out.index("[ai]") < out.index("(ungrouped)")


def test_clusters_list_flat_when_no_groups(tmp_path: Path, capsys) -> None:
    """_clusters_list falls back to flat list when no clusters have groups."""
    from research_hub.cli import _clusters_list

    _write_clusters_yaml(tmp_path, [
        {"slug": "floods", "name": "Floods"},
        {"slug": "policy", "name": "Policy"},
    ])

    with patch("research_hub.cli.get_config") as mock_cfg:
        mock_cfg.return_value = SimpleNamespace(
            clusters_file=tmp_path / "clusters.yaml"
        )
        _clusters_list()

    out = capsys.readouterr().out
    assert "floods" in out
    assert "policy" in out
    assert "[" not in out  # no group headers


# ---------------------------------------------------------------------------
# F4b — emit_cross_cluster_gap_prompt
# ---------------------------------------------------------------------------


def test_emit_cross_cluster_gap_prompt_contains_both_clusters(tmp_path: Path) -> None:
    """emit_cross_cluster_gap_prompt embeds paper titles from both clusters."""
    from research_hub.gap_analysis import (
        ClusterDigest,
        PaperDigestEntry,
        emit_cross_cluster_gap_prompt,
    )

    digest_a = ClusterDigest(
        slug="floods", name="Floods", paper_count=1,
        papers=[PaperDigestEntry(title="Flood Risk Paper", summary="We study floods.")]
    )
    digest_b = ClusterDigest(
        slug="llm-agents", name="LLM Agents", paper_count=1,
        papers=[PaperDigestEntry(title="LLM Agent Paper", summary="We study agents.")]
    )
    prompt = emit_cross_cluster_gap_prompt(digest_a, digest_b)

    assert "Flood Risk Paper" in prompt
    assert "LLM Agent Paper" in prompt
    assert "floods" in prompt
    assert "llm-agents" in prompt


def test_emit_cross_cluster_gap_prompt_required_sections() -> None:
    """emit_cross_cluster_gap_prompt output contains all required section headings."""
    from research_hub.gap_analysis import ClusterDigest, emit_cross_cluster_gap_prompt

    digest_a = ClusterDigest(slug="a", name="A", paper_count=0)
    digest_b = ClusterDigest(slug="b", name="B", paper_count=0)
    prompt = emit_cross_cluster_gap_prompt(digest_a, digest_b)

    assert "Cluster A Covers That B Does Not" in prompt
    assert "Cluster B Covers That A Does Not" in prompt
    assert "Intersection Gaps" in prompt
    assert "Bridging Research Directions" in prompt
    assert "evidence-anchored" in prompt or "evidence" in prompt.lower()


# ---------------------------------------------------------------------------
# F4b — cross_cluster_gap (result writing)
# ---------------------------------------------------------------------------


def test_cross_cluster_gap_writes_file(tmp_path: Path) -> None:
    """cross_cluster_gap writes A-x-B-gaps.md under hub/_cross-cluster/."""
    from research_hub.gap_analysis import cross_cluster_gap

    cfg = _make_cfg(tmp_path)
    # Ensure hub dirs exist
    (tmp_path / "hub" / "_cross-cluster").mkdir(parents=True)

    gap_md = "### What A Covers That B Does Not\n- Topic X (Papers A1)\n"
    result = cross_cluster_gap(cfg, "floods", "llm-agents", gap_md)

    assert result.written is True
    assert result.gap_path is not None
    assert result.gap_path.exists()
    content = result.gap_path.read_text(encoding="utf-8")
    assert "floods" in content
    assert "llm-agents" in content
    assert "Topic X" in content


def test_cross_cluster_gap_filename_convention(tmp_path: Path) -> None:
    """cross_cluster_gap uses <A>-x-<B>-gaps.md filename."""
    from research_hub.gap_analysis import cross_cluster_gap

    cfg = _make_cfg(tmp_path)
    (tmp_path / "hub" / "_cross-cluster").mkdir(parents=True)

    result = cross_cluster_gap(cfg, "floods", "llm-agents", "gap content")
    assert result.gap_path.name == "floods-x-llm-agents-gaps.md"


def test_cross_cluster_gap_updates_both_overviews(tmp_path: Path) -> None:
    """cross_cluster_gap appends ## Cross-Cluster Analysis to each cluster's 00_overview.md."""
    from research_hub.gap_analysis import cross_cluster_gap

    cfg = _make_cfg(tmp_path)
    (tmp_path / "hub" / "_cross-cluster").mkdir(parents=True)
    hub_a = tmp_path / "hub" / "floods"
    hub_a.mkdir(parents=True)
    hub_b = tmp_path / "hub" / "llm-agents"
    hub_b.mkdir(parents=True)

    overview_a = hub_a / "00_overview.md"
    overview_b = hub_b / "00_overview.md"
    overview_a.write_text("# Floods\n\nSome content.\n", encoding="utf-8")
    overview_b.write_text("# LLM Agents\n\nSome content.\n", encoding="utf-8")

    result = cross_cluster_gap(cfg, "floods", "llm-agents", "### Cross content")

    assert result.overview_a_updated is True
    assert result.overview_b_updated is True
    assert "## Cross-Cluster Analysis" in overview_a.read_text(encoding="utf-8")
    assert "## Cross-Cluster Analysis" in overview_b.read_text(encoding="utf-8")


def test_cross_cluster_gap_no_duplicate_overview_section(tmp_path: Path) -> None:
    """cross_cluster_gap does not duplicate ## Cross-Cluster Analysis."""
    from research_hub.gap_analysis import cross_cluster_gap

    cfg = _make_cfg(tmp_path)
    (tmp_path / "hub" / "_cross-cluster").mkdir(parents=True)
    hub_a = tmp_path / "hub" / "floods"
    hub_a.mkdir()
    overview_a = hub_a / "00_overview.md"
    original = "# Floods\n\n## Cross-Cluster Analysis\n\nAlready here.\n"
    overview_a.write_text(original, encoding="utf-8")

    cross_cluster_gap(cfg, "floods", "llm-agents", "content")

    assert overview_a.read_text(encoding="utf-8") == original


# ---------------------------------------------------------------------------
# F4b — _cmd_paper_gaps with --compare
# ---------------------------------------------------------------------------


def test_cmd_paper_gaps_compare_no_llm_saves_prompt(tmp_path: Path, capsys) -> None:
    """paper gaps --cluster A --compare B --no-llm saves cross-cluster prompt (both clusters non-empty)."""
    from research_hub.cli import _cmd_paper_gaps

    cfg = _make_cfg(tmp_path)
    _write_paper(cfg.raw / "floods", "p1", title="Flood Study")
    _write_paper(cfg.raw / "llm-agents", "p2", title="Agent Study")

    args = SimpleNamespace(
        cluster="floods", compare_cluster="llm-agents", no_llm=True, llm_cli=None
    )
    _cmd_paper_gaps(cfg, args)

    # Prompt file must exist since both clusters have papers
    prompt_path = (
        tmp_path / ".research_hub" / "artifacts"
        / "floods-x-llm-agents" / "gap-analysis-prompt.md"
    )
    assert prompt_path.exists(), f"Expected cross-cluster prompt at {prompt_path}"


def test_cmd_paper_gaps_compare_with_mock_llm(tmp_path: Path, capsys) -> None:
    """paper gaps --cluster A --compare B invokes LLM and writes cross-cluster file."""
    from research_hub.cli import _cmd_paper_gaps

    cfg = _make_cfg(tmp_path)
    _write_paper(cfg.raw / "floods", "p1", title="Flood Study")
    _write_paper(cfg.raw / "llm-agents", "p2", title="Agent Study")
    (tmp_path / "hub" / "_cross-cluster").mkdir(parents=True)

    gap_response = (
        "### What Cluster A Covers That B Does Not\n"
        "- Flood risk modeling (Papers A1)\n"
    )

    with (
        patch("research_hub.llm_cli.detect_llm_cli", return_value="claude"),
        patch("research_hub.llm_cli.invoke_llm_cli", return_value=gap_response),
    ):
        args = SimpleNamespace(
            cluster="floods", compare_cluster="llm-agents", no_llm=False, llm_cli=None
        )
        _cmd_paper_gaps(cfg, args)

    out = capsys.readouterr().out
    assert "floods" in out or "gap" in out.lower()
