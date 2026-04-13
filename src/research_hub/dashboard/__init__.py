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


def generate_dashboard(
    open_browser: bool = False,
    *,
    refresh_seconds: int = 0,
) -> Path:
    """Generate dashboard HTML and optionally open it in the browser.

    ``refresh_seconds`` injects a meta-refresh so an already-open
    browser tab will auto-reload at that cadence. ``0`` (default) emits
    no refresh meta — the file stays static. Used by ``--watch`` mode.

    Only instantiates a Zotero client when both ``api_key`` AND
    ``library_id`` are loadable. Otherwise the cite buttons fall back
    to frontmatter-built BibTeX (always present, never partial).
    """
    cfg = get_config()
    zot = None
    if not getattr(cfg, "no_zotero", False):
        try:
            from research_hub.zotero.client import _load_credentials

            api_key, lib_id, _lib_type = _load_credentials()
            if api_key and lib_id:
                from research_hub.zotero.client import ZoteroDualClient

                zot = ZoteroDualClient()
        except Exception:
            zot = None
    html = render_dashboard_from_config(cfg, zot=zot, refresh_seconds=refresh_seconds)
    out_path = cfg.research_hub_dir / "dashboard.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    if open_browser:
        webbrowser.open(out_path.as_uri())
    return out_path


def watch_dashboard(
    poll_seconds: float = 5.0,
    refresh_seconds: int = 10,
    open_browser: bool = True,
) -> None:
    """Regenerate the dashboard whenever vault state files change.

    Polls ``manifest.jsonl``, ``dedup_index.json``, ``nlm_cache.json``,
    and ``clusters.yaml`` for mtime changes. Re-runs ``generate_dashboard``
    on any change. The emitted HTML carries a meta-refresh of
    ``refresh_seconds`` so the open browser tab reloads itself.

    Press Ctrl+C to stop.
    """
    import time

    cfg = get_config()
    watch_paths = [
        cfg.research_hub_dir / "manifest.jsonl",
        cfg.research_hub_dir / "dedup_index.json",
        cfg.research_hub_dir / "nlm_cache.json",
        cfg.clusters_file,
        cfg.raw,
    ]

    def _state_signature() -> tuple:
        sig: list = []
        for p in watch_paths:
            try:
                if p.is_dir():
                    # Hash of (file count, max mtime) for the raw notes folder
                    files = list(p.rglob("*.md"))
                    sig.append(("dir", len(files), max((f.stat().st_mtime for f in files), default=0)))
                else:
                    sig.append(("file", p.stat().st_mtime if p.exists() else 0))
            except OSError:
                sig.append(("err",))
        return tuple(sig)

    print(
        f"Watching vault state ({len(watch_paths)} paths). "
        f"Re-render on change · meta-refresh {refresh_seconds}s · Ctrl+C to stop."
    )
    out_path = generate_dashboard(open_browser=open_browser, refresh_seconds=refresh_seconds)
    print(f"  initial render → {out_path}")
    last = _state_signature()
    try:
        while True:
            time.sleep(poll_seconds)
            current = _state_signature()
            if current != last:
                last = current
                out_path = generate_dashboard(open_browser=False, refresh_seconds=refresh_seconds)
                from datetime import datetime, timezone

                stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
                print(f"  [{stamp}] vault changed → re-rendered")
    except KeyboardInterrupt:
        print("\nStopped watching.")


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
    "watch_dashboard",
]
