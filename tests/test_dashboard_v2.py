"""Dashboard v2 compatibility tests that remain valid after the rewrite."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from research_hub.clusters import ClusterRegistry
from research_hub.dashboard import (
    DashboardContext,
    collect_dashboard_context,
    render_dashboard,
    render_dashboard_from_config,
)
from research_hub.dashboard.context import _detect_persona
from research_hub.dashboard.sections import html_escape


class StubConfig:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.raw = root / "raw"
        self.research_hub_dir = root / ".research_hub"
        self.clusters_file = self.research_hub_dir / "clusters.yaml"


def _make_config(tmp_path: Path) -> StubConfig:
    root = tmp_path / "vault"
    cfg = StubConfig(root)
    cfg.raw.mkdir(parents=True)
    cfg.research_hub_dir.mkdir(parents=True)
    return cfg


def _write_note(
    cfg: StubConfig,
    cluster_slug: str,
    filename: str,
    *,
    title: str = "Test paper",
    status: str = "unread",
    year: str = "2025",
    doi: str = "10.1/test",
    ingested_at: str = "2026-04-12T10:00:00Z",
) -> Path:
    note_dir = cfg.raw / cluster_slug
    note_dir.mkdir(parents=True, exist_ok=True)
    note_path = note_dir / filename
    note_path.write_text(
        f"""---
title: "{title}"
status: "{status}"
year: "{year}"
doi: "{doi}"
ingested_at: "{ingested_at}"
---
Body
""",
        encoding="utf-8",
    )
    return note_path


def _empty_ctx(**overrides) -> DashboardContext:
    base = DashboardContext(
        vault_root="/vault",
        generated_at="2026-04-12 12:00 UTC",
        persona="researcher",
        total_papers=0,
        total_clusters=0,
        total_unread=0,
        papers_this_week=0,
        dedup_doi_count=0,
        dedup_title_count=0,
        nlm_cached_clusters=0,
    )
    return replace(base, **overrides)


def test_collect_dashboard_context_loads_clusters_and_papers(tmp_path):
    cfg = _make_config(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    _write_note(cfg, "agents", "p1.md", status="reading")
    _write_note(cfg, "agents", "p2.md", status="deep-read")
    _write_note(cfg, "agents", "p3.md", status="cited")

    ctx = collect_dashboard_context(cfg)

    assert ctx.total_papers == 3
    assert ctx.total_clusters == 1
    assert ctx.total_unread == 0
    assert len(ctx.papers) == 3
    cluster = ctx.clusters[0]
    assert cluster.deep_read_count == 1
    assert cluster.cited_count == 1
    assert cluster.reading_count == 1


def test_collect_dashboard_context_papers_this_week_counts_only_recent(tmp_path):
    cfg = _make_config(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    recent = (now - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    old = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    _write_note(cfg, "agents", "fresh.md", ingested_at=recent)
    _write_note(cfg, "agents", "stale.md", ingested_at=old)

    ctx = collect_dashboard_context(cfg)

    assert ctx.papers_this_week == 1


def test_detect_persona_env_var(monkeypatch, tmp_path):
    cfg = _make_config(tmp_path)
    monkeypatch.setenv("RESEARCH_HUB_NO_ZOTERO", "1")
    assert _detect_persona(cfg) == "analyst"
    monkeypatch.delenv("RESEARCH_HUB_NO_ZOTERO", raising=False)
    assert _detect_persona(cfg) == "researcher"


def test_collect_dashboard_context_reads_nlm_artifacts(tmp_path):
    cfg = _make_config(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    _write_note(cfg, "agents", "p1.md")
    (cfg.research_hub_dir / "nlm_cache.json").write_text(
        json.dumps(
            {
                "agents": {
                    "notebook_url": "https://notebooklm.google.com/test",
                    "artifacts": {
                        "brief": {
                            "path": str(tmp_path / "brief.txt"),
                            "downloaded_at": "2026-04-12T12:00:00Z",
                            "char_count": 421,
                            "titles": ["A title"],
                        }
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    ctx = collect_dashboard_context(cfg)

    assert ctx.nlm_cached_clusters == 1
    assert len(ctx.nlm_artifacts) == 1
    assert ctx.nlm_artifacts[0].char_count == 421
    assert ctx.nlm_artifacts[0].titles == ["A title"]


@pytest.mark.skip("rewritten in v0.10")
def test_render_dashboard_is_self_contained():
    ctx = _empty_ctx()
    html = render_dashboard(ctx)
    assert "<link " not in html


@pytest.mark.skip("rewritten in v0.10")
def test_render_dashboard_escapes_user_data():
    ctx = _empty_ctx()
    html = render_dashboard(ctx)
    assert "<script>alert(1)</script>" not in html


@pytest.mark.skip("rewritten in v0.10")
def test_render_dashboard_persona_label():
    researcher_html = render_dashboard(_empty_ctx(persona="researcher"))
    analyst_html = render_dashboard(_empty_ctx(persona="analyst"))
    assert "Researcher persona" in researcher_html
    assert "Analyst persona" in analyst_html


@pytest.mark.skip("rewritten in v0.10")
def test_render_dashboard_includes_search_input_and_script():
    ctx = _empty_ctx()
    html = render_dashboard(ctx)
    assert "vault-search" in html


@pytest.mark.skip("rewritten in v0.10")
def test_render_dashboard_from_config_walks_real_vault(tmp_path):
    cfg = _make_config(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    _write_note(cfg, "agents", "p1.md")
    html = render_dashboard_from_config(cfg)
    assert "Agents" in html


def test_html_escape_handles_none_and_int():
    assert html_escape(None) == ""
    assert html_escape(42) == "42"
    assert html_escape("<a>") == "&lt;a&gt;"
