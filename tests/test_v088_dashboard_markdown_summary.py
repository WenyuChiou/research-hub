"""v0.88 #11 — dashboard markdown summary (Obsidian-internal landing surface)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from research_hub.dashboard.markdown_summary import (
    _cluster_stats,
    render_dashboard_markdown_summary,
    write_dashboard_markdown_summary,
)


def _seed_paper(
    raw_dir: Path,
    stem: str,
    *,
    status: str = "unread",
    summarize_status: str = "done",
) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"{stem}.md").write_text(
        f'---\ntitle: "x"\nstatus: {status}\nsummarize_status: {summarize_status}\n---\n# x\n',
        encoding="utf-8",
    )


def _seed_registry(vault: Path, slugs: list[str]) -> None:
    p = vault / ".research_hub" / "clusters.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({"clusters": {slug: {"name": slug, "first_query": ""} for slug in slugs}}),
        encoding="utf-8",
    )


def _cfg(vault: Path) -> SimpleNamespace:
    return SimpleNamespace(
        root=vault,
        clusters_file=vault / ".research_hub" / "clusters.yaml",
    )


def test_cluster_stats_counts_papers_and_unread(tmp_path: Path) -> None:
    raw = tmp_path / "raw" / "demo"
    _seed_paper(raw, "a", status="unread", summarize_status="done")
    _seed_paper(raw, "b", status="unread", summarize_status="pending")
    _seed_paper(raw, "c", status="read", summarize_status="done")
    # Should NOT count the overview file
    (raw / "00_overview.md").write_text("# overview", encoding="utf-8")

    stats = _cluster_stats(tmp_path, "demo")
    assert stats["papers"] == 3
    assert stats["unread"] == 2
    assert stats["pending_summary"] == 1
    assert stats["brief_exists"] is False


def test_cluster_stats_detects_brief(tmp_path: Path) -> None:
    hub = tmp_path / "hub" / "demo"
    hub.mkdir(parents=True)
    (hub / "notebooklm-brief-20260101T000000Z.md").write_text("...", encoding="utf-8")
    stats = _cluster_stats(tmp_path, "demo")
    assert stats["brief_exists"] is True


def test_cluster_stats_handles_missing_raw(tmp_path: Path) -> None:
    stats = _cluster_stats(tmp_path, "missing")
    assert stats == {"papers": 0, "unread": 0, "pending_summary": 0, "brief_exists": False}


def test_render_includes_canonical_sections(tmp_path: Path) -> None:
    _seed_paper(tmp_path / "raw" / "demo", "a")
    _seed_registry(tmp_path, ["demo"])
    text = render_dashboard_markdown_summary(_cfg(tmp_path))
    assert "## Clusters" in text
    assert "## Backlog" in text
    assert "## Quick commands" in text
    assert "type: dashboard-summary" in text


def test_render_emits_table_with_per_cluster_row(tmp_path: Path) -> None:
    _seed_paper(tmp_path / "raw" / "alpha-cluster", "p1", status="unread")
    _seed_paper(tmp_path / "raw" / "alpha-cluster", "p2", status="unread")
    _seed_paper(tmp_path / "raw" / "beta-cluster", "p3", status="read")
    _seed_registry(tmp_path, ["alpha-cluster", "beta-cluster"])

    text = render_dashboard_markdown_summary(_cfg(tmp_path))
    assert "alpha-cluster" in text
    assert "beta-cluster" in text
    # Totals row
    assert "**total**" in text


def test_render_backlog_zero_uses_green_state(tmp_path: Path) -> None:
    _seed_paper(tmp_path / "raw" / "demo", "a", summarize_status="done")
    _seed_registry(tmp_path, ["demo"])
    text = render_dashboard_markdown_summary(_cfg(tmp_path))
    assert "Papers awaiting summary: **0** ✅" in text


def test_render_backlog_nonzero_includes_clear_command(tmp_path: Path) -> None:
    _seed_paper(tmp_path / "raw" / "demo", "a", summarize_status="pending")
    _seed_paper(tmp_path / "raw" / "demo", "b", summarize_status="pending")
    _seed_registry(tmp_path, ["demo"])
    text = render_dashboard_markdown_summary(_cfg(tmp_path))
    assert "Papers awaiting summary: **2**" in text
    assert "research-hub paper summarize --pending" in text


def test_render_handles_no_clusters(tmp_path: Path) -> None:
    _seed_registry(tmp_path, [])
    text = render_dashboard_markdown_summary(_cfg(tmp_path))
    assert "(no clusters)" in text


def test_write_creates_file_at_default_path(tmp_path: Path) -> None:
    _seed_paper(tmp_path / "raw" / "demo", "a")
    _seed_registry(tmp_path, ["demo"])
    path = write_dashboard_markdown_summary(_cfg(tmp_path))
    assert path == tmp_path / ".research_hub" / "dashboard-summary.md"
    assert path.exists()
    assert "## Clusters" in path.read_text(encoding="utf-8")


def test_write_respects_explicit_out_path(tmp_path: Path) -> None:
    _seed_paper(tmp_path / "raw" / "demo", "a")
    _seed_registry(tmp_path, ["demo"])
    target = tmp_path / "custom" / "dash.md"
    path = write_dashboard_markdown_summary(_cfg(tmp_path), out_path=target)
    assert path == target
    assert path.exists()
