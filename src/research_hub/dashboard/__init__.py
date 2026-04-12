"""Personal HTML dashboard for the research-hub vault.

Public surface:
- ``generate_dashboard(open_browser=False)`` — write the dashboard to
  ``<vault>/.research_hub/dashboard.html``.
- ``DashboardContext`` — the snapshot every section reads from.
- ``DashboardSection`` (+ ``DEFAULT_SECTIONS``) — extension point.
- ``render_dashboard(ctx)`` — pure render of an in-memory context.

Backwards-compat shims for v0.9.0 callers:
- ``ClusterStats`` — legacy dataclass mirroring the v0.9.0 cluster
  summary used by ``tests/test_dashboard.py``.
- ``collect_vault_state(cfg)`` — legacy dict snapshot.
- ``render_dashboard_html(state)`` — legacy renderer that accepts the
  legacy dict and produces a dashboard. Internally it just delegates
  to ``render_dashboard`` over a constructed ``DashboardContext``.
"""

from __future__ import annotations

import webbrowser
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from research_hub.config import get_config
from research_hub.dashboard.context import (
    ActivityEvent,
    ClusterRow,
    DashboardContext,
    NLMArtifact,
    PaperRow,
    collect_dashboard_context,
)
from research_hub.dashboard.render import (
    render_dashboard,
    render_dashboard_from_config,
)
from research_hub.dashboard.sections import (
    DEFAULT_SECTIONS,
    ActivitySection,
    ClustersSection,
    DashboardSection,
    NotebookLMSection,
    OverviewSection,
    ReadingQueueSection,
)


@dataclass
class ClusterStats:
    """Legacy dataclass kept for backwards compatibility with tests."""

    slug: str
    name: str
    paper_count: int = 0
    status_breakdown: dict[str, int] = field(default_factory=dict)
    zotero_collection_key: str = ""
    notebooklm_notebook: str = ""
    notebooklm_notebook_url: str = ""
    latest_ingested_at: str = ""


def collect_vault_state(cfg) -> dict:
    """Legacy state-dict shape used by v0.9.0 tests.

    The new code uses ``collect_dashboard_context`` which returns a
    typed ``DashboardContext``. This shim flattens that into the old
    dict for the existing test suite.
    """
    ctx = collect_dashboard_context(cfg)
    clusters: dict[str, ClusterStats] = {}
    for c in ctx.clusters:
        breakdown = {
            "unread": c.unread_count,
            "reading": c.reading_count,
            "deep-read": c.deep_read_count,
            "cited": c.cited_count,
        }
        clusters[c.slug] = ClusterStats(
            slug=c.slug,
            name=c.name,
            paper_count=c.paper_count,
            status_breakdown={k: v for k, v in breakdown.items() if v},
            zotero_collection_key=c.zotero_collection_key,
            notebooklm_notebook=c.notebooklm_notebook,
            notebooklm_notebook_url=c.notebooklm_notebook_url,
            latest_ingested_at=c.latest_ingested_at,
        )
    return {
        "vault_root": ctx.vault_root,
        "generated_at": ctx.generated_at,
        "total_papers": ctx.total_papers,
        "total_clusters": ctx.total_clusters,
        "dedup_doi_count": ctx.dedup_doi_count,
        "dedup_title_count": ctx.dedup_title_count,
        "clusters": clusters,
        "nlm_cache": {a.cluster_slug: {"notebook_url": a.notebook_url} for a in ctx.nlm_artifacts},
    }


def render_dashboard_html(state: dict) -> str:
    """Legacy renderer — delegates to the new pipeline.

    Tests construct a ``state`` dict via ``collect_vault_state`` and
    expect ``render_dashboard_html`` to produce a complete HTML page
    that mentions ``research-hub`` and the cluster names. The new
    package can do that by translating the legacy dict back into a
    ``DashboardContext`` and calling ``render_dashboard``.
    """
    cluster_rows: list[ClusterRow] = []
    for stats in state.get("clusters", {}).values():
        cluster_rows.append(
            ClusterRow(
                slug=stats.slug,
                name=stats.name,
                paper_count=stats.paper_count,
                unread_count=stats.status_breakdown.get("unread", 0),
                deep_read_count=stats.status_breakdown.get("deep-read", 0),
                cited_count=stats.status_breakdown.get("cited", 0),
                reading_count=stats.status_breakdown.get("reading", 0),
                zotero_collection_key=stats.zotero_collection_key,
                notebooklm_notebook=stats.notebooklm_notebook,
                notebooklm_notebook_url=stats.notebooklm_notebook_url,
                notebooklm_brief_path="",
                latest_ingested_at=stats.latest_ingested_at,
            )
        )
    ctx = DashboardContext(
        vault_root=state.get("vault_root", ""),
        generated_at=state.get("generated_at", ""),
        persona="researcher",
        total_papers=state.get("total_papers", 0),
        total_clusters=state.get("total_clusters", 0),
        total_unread=sum(c.unread_count for c in cluster_rows),
        papers_this_week=0,
        dedup_doi_count=state.get("dedup_doi_count", 0),
        dedup_title_count=state.get("dedup_title_count", 0),
        nlm_cached_clusters=len(state.get("nlm_cache", {})),
        clusters=sorted(cluster_rows, key=lambda c: (-c.paper_count, c.name.lower())),
    )
    return render_dashboard(ctx)


def generate_dashboard(open_browser: bool = False) -> Path:
    """Generate dashboard HTML and optionally open it in the browser."""
    cfg = get_config()
    html = render_dashboard_from_config(cfg)
    out_path = cfg.research_hub_dir / "dashboard.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    if open_browser:
        webbrowser.open(out_path.as_uri())
    return out_path


__all__ = [
    "ActivityEvent",
    "ActivitySection",
    "ClusterRow",
    "ClustersSection",
    "ClusterStats",
    "DEFAULT_SECTIONS",
    "DashboardContext",
    "DashboardSection",
    "NLMArtifact",
    "NotebookLMSection",
    "OverviewSection",
    "PaperRow",
    "ReadingQueueSection",
    "collect_dashboard_context",
    "collect_vault_state",
    "generate_dashboard",
    "get_config",
    "render_dashboard",
    "render_dashboard_from_config",
    "render_dashboard_html",
]
