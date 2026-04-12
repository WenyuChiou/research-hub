"""Dashboard v2 tests — DashboardContext, sections, render pipeline."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from research_hub.clusters import ClusterRegistry
from research_hub.dashboard import (
    ActivityEvent,
    ActivitySection,
    ClusterRow,
    ClustersSection,
    DashboardContext,
    DashboardSection,
    NLMArtifact,
    NotebookLMSection,
    OverviewSection,
    PaperRow,
    ReadingQueueSection,
    collect_dashboard_context,
    render_dashboard,
    render_dashboard_from_config,
)
from research_hub.dashboard.sections import html_escape
from research_hub.dashboard.context import _detect_persona


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


# --- DashboardContext loading -------------------------------------------


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


# --- Section rendering --------------------------------------------------


def test_overview_section_renders_stat_cards():
    ctx = _empty_ctx(total_papers=42, total_clusters=5, total_unread=12, papers_this_week=3)
    html = OverviewSection().render(ctx)
    assert "42" in html
    assert "Papers" in html
    assert "Clusters" in html
    assert "Unread" in html
    assert "+3" in html


def test_overview_section_hides_nlm_card_for_analyst():
    ctx = _empty_ctx(persona="analyst", nlm_cached_clusters=4)
    html = OverviewSection().render(ctx)
    assert "NotebookLM linked" not in html


def test_clusters_section_empty_state():
    ctx = _empty_ctx()
    html = ClustersSection().render(ctx)
    assert "No clusters yet" in html
    assert "research-hub clusters new" in html


def test_clusters_section_renders_progress_bar():
    cluster = ClusterRow(
        slug="agents",
        name="Agents",
        paper_count=10,
        unread_count=4,
        deep_read_count=3,
        cited_count=2,
        reading_count=1,
        zotero_collection_key="ABCD",
        notebooklm_notebook="Agents",
        notebooklm_notebook_url="https://notebooklm.google.com/agents",
        notebooklm_brief_path="",
        latest_ingested_at="2026-04-12T10:00:00Z",
    )
    ctx = _empty_ctx(clusters=[cluster], total_clusters=1, total_papers=10, total_unread=4)
    html = ClustersSection().render(ctx)
    assert '<progress class="cluster-progress" value="6" max="10"' in html
    assert "https://notebooklm.google.com/agents" in html
    assert "deep-read 3" in html


def test_reading_queue_section_emits_paper_rows():
    ctx = _empty_ctx(
        total_papers=2,
        papers=[
            PaperRow(
                slug="p1",
                title="Paper One",
                cluster_slug="agents",
                cluster_name="Agents",
                year="2025",
                status="unread",
                doi="10.1/p1",
                ingested_at="2026-04-12T10:00:00Z",
                obsidian_path="",
            ),
            PaperRow(
                slug="p2",
                title="Paper Two",
                cluster_slug="agents",
                cluster_name="Agents",
                year="2024",
                status="deep-read",
                doi="10.1/p2",
                ingested_at="2026-04-11T10:00:00Z",
                obsidian_path="",
            ),
        ],
    )
    html = ReadingQueueSection().render(ctx)
    assert "Paper One" in html
    assert "Paper Two" in html
    assert "data-status=\"unread\"" in html
    assert "data-status=\"deep-read\"" in html
    # Every paper has a copy button with the right CLI command embedded.
    assert "research-hub mark p1 --status deep-read" in html
    assert "research-hub mark p2 --status deep-read" in html
    # Filter chips are present.
    assert 'data-status="all"' in html


def test_reading_queue_section_empty_state():
    ctx = _empty_ctx()
    html = ReadingQueueSection().render(ctx)
    assert "Add papers via" in html


def test_activity_section_renders_recent_events():
    ctx = _empty_ctx(
        activity=[
            ActivityEvent(
                timestamp="2026-04-12T10:00:00Z",
                cluster="agents",
                action="ingested",
                title="Test Paper",
                doi="10.1/test",
            )
        ]
    )
    html = ActivitySection().render(ctx)
    assert "Test Paper" in html
    assert "ingested" in html
    assert "<ol class=\"activity-feed\">" in html


def test_notebooklm_section_omitted_when_empty():
    ctx = _empty_ctx()
    html = NotebookLMSection().render(ctx)
    assert html == ""


def test_notebooklm_section_omitted_for_analyst_persona():
    ctx = _empty_ctx(
        persona="analyst",
        nlm_artifacts=[
            NLMArtifact(
                cluster_slug="x",
                cluster_name="X",
                notebook_url="",
                brief_path="/tmp/brief.txt",
                downloaded_at="2026-04-12T12:00:00Z",
                char_count=100,
            )
        ],
    )
    html = NotebookLMSection().render(ctx)
    assert html == ""


def test_notebooklm_section_renders_cards_for_researcher():
    ctx = _empty_ctx(
        nlm_artifacts=[
            NLMArtifact(
                cluster_slug="agents",
                cluster_name="Agents",
                notebook_url="https://notebooklm.google.com/n",
                brief_path="C:/v/.research_hub/artifacts/agents/brief-1.txt",
                downloaded_at="2026-04-12T12:00:00Z",
                char_count=421,
            )
        ]
    )
    html = NotebookLMSection().render(ctx)
    assert "Agents" in html
    assert "421 chars" in html
    assert "https://notebooklm.google.com/n" in html


# --- render_dashboard composition ---------------------------------------


def test_render_dashboard_is_self_contained():
    ctx = _empty_ctx()
    html = render_dashboard(ctx)
    assert "<link " not in html
    assert "<script src=" not in html
    assert "{{ STYLE }}" not in html
    assert "{{ BODY }}" not in html
    assert "{{ VAULT_DATA_JSON }}" not in html
    assert "research-hub" in html


def test_render_dashboard_escapes_user_data():
    cluster = ClusterRow(
        slug="x",
        name="<script>alert(1)</script>",
        paper_count=0,
        unread_count=0,
        deep_read_count=0,
        cited_count=0,
        reading_count=0,
        zotero_collection_key="",
        notebooklm_notebook="",
        notebooklm_notebook_url="",
        notebooklm_brief_path="",
        latest_ingested_at="",
    )
    ctx = _empty_ctx(clusters=[cluster], total_clusters=1)
    html = render_dashboard(ctx)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_render_dashboard_persona_label():
    researcher_html = render_dashboard(_empty_ctx(persona="researcher"))
    analyst_html = render_dashboard(_empty_ctx(persona="analyst"))
    assert "Researcher persona" in researcher_html
    assert "Analyst persona" in analyst_html


def test_render_dashboard_includes_search_input_and_script():
    ctx = _empty_ctx()
    html = render_dashboard(ctx)
    assert 'id="search-input"' in html
    assert "navigator.clipboard" in html  # script body inlined
    assert "VAULT_DATA" in html


def test_render_dashboard_from_config_walks_real_vault(tmp_path):
    cfg = _make_config(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    _write_note(cfg, "agents", "p1.md")
    html = render_dashboard_from_config(cfg)
    assert "Agents" in html
    assert "p1" in html


def test_html_escape_handles_none_and_int():
    assert html_escape(None) == ""
    assert html_escape(42) == "42"
    assert html_escape("<a>") == "&lt;a&gt;"
