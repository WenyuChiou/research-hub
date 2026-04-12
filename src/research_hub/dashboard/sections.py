"""Dashboard sections — one class per visual block.

Each section is a small, pure render function that takes a
``DashboardContext`` and returns an HTML fragment. ``render.py``
composes them into the final document. Adding a new section means
writing one class and appending it to ``DEFAULT_SECTIONS``.
"""

from __future__ import annotations

from dataclasses import dataclass

from research_hub.dashboard.context import (
    ActivityEvent,
    ClusterRow,
    DashboardContext,
    NLMArtifact,
    PaperRow,
)


def html_escape(value: object) -> str:
    """HTML-escape any value, including ints and None."""
    if value is None:
        return ""
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


@dataclass
class DashboardSection:
    """Base class. Subclasses override ``render``."""

    id: str = ""
    title: str = ""
    order: int = 0

    def render(self, ctx: DashboardContext) -> str:  # pragma: no cover - abstract
        raise NotImplementedError


# --- Section 1: Overview (stat cards) -----------------------------------


class OverviewSection(DashboardSection):
    id = "overview"
    title = "Overview"
    order = 10

    def __init__(self) -> None:
        self.id = "overview"
        self.title = "Overview"
        self.order = 10

    def render(self, ctx: DashboardContext) -> str:
        cards = [
            ("📄", ctx.total_papers, "Papers"),
            ("📂", ctx.total_clusters, "Clusters"),
            ("⏳", ctx.total_unread, "Unread"),
            ("🆕", f"+{ctx.papers_this_week}", "This week"),
            ("🔁", ctx.dedup_doi_count, "DOIs indexed"),
        ]
        if ctx.persona != "analyst":
            cards.append(("📓", ctx.nlm_cached_clusters, "NotebookLM linked"))
        items = "".join(
            f"""
            <div class="stat-card">
              <dt class="stat-icon" aria-hidden="true">{html_escape(icon)}</dt>
              <dd class="stat-value">{html_escape(value)}</dd>
              <dd class="stat-label">{html_escape(label)}</dd>
            </div>
            """
            for icon, value, label in cards
        )
        return f"""
        <section id="overview" aria-labelledby="overview-heading">
          <h2 id="overview-heading" class="visually-hidden">Overview</h2>
          <dl class="stats-grid">{items}</dl>
        </section>
        """


# --- Section 2: Clusters (expandable list) ------------------------------


class ClustersSection(DashboardSection):
    id = "clusters"
    title = "Clusters"
    order = 20

    def __init__(self) -> None:
        self.id = "clusters"
        self.title = "Clusters"
        self.order = 20

    def render(self, ctx: DashboardContext) -> str:
        if not ctx.clusters:
            return f"""
        <section id="clusters" aria-labelledby="clusters-heading">
          <h2 id="clusters-heading">Clusters</h2>
          <p class="empty-state">No clusters yet. Run
            <code>research-hub clusters new --query "topic"</code>
            to create one.</p>
        </section>
        """
        rows = "".join(self._row(c, ctx) for c in ctx.clusters)
        return f"""
        <section id="clusters" aria-labelledby="clusters-heading">
          <h2 id="clusters-heading">Clusters</h2>
          <div class="cluster-list">{rows}</div>
        </section>
        """

    def _row(self, c: ClusterRow, ctx: DashboardContext) -> str:
        progress_max = max(c.paper_count, 1)
        progress_value = c.paper_count - c.unread_count
        nlm_chip = ""
        if ctx.persona != "analyst":
            if c.notebooklm_notebook_url:
                nlm_chip = (
                    f'<a class="chip chip-link" '
                    f'href="{html_escape(c.notebooklm_notebook_url)}" '
                    f'target="_blank" rel="noreferrer noopener">NLM ✓</a>'
                )
            elif c.notebooklm_notebook:
                nlm_chip = '<span class="chip chip-muted">NLM —</span>'
        zotero_chip = (
            f'<span class="chip chip-muted">Zotero {html_escape(c.zotero_collection_key)}</span>'
            if c.zotero_collection_key
            else '<span class="chip chip-muted">unbound</span>'
        )
        last_added = c.latest_ingested_at[:10] if c.latest_ingested_at else "—"
        return f"""
        <details class="cluster-card" data-cluster="{html_escape(c.slug)}">
          <summary>
            <span class="cluster-name">{html_escape(c.name)}</span>
            <span class="cluster-meta">
              {c.paper_count} papers · {c.unread_count} unread · last {html_escape(last_added)}
            </span>
            <progress class="cluster-progress" value="{progress_value}" max="{progress_max}"
                      aria-label="Reading progress for {html_escape(c.name)}"></progress>
          </summary>
          <div class="cluster-body">
            <div class="cluster-chips">
              {zotero_chip}
              {nlm_chip}
              <span class="chip chip-muted">slug: <code>{html_escape(c.slug)}</code></span>
            </div>
            <div class="cluster-counts">
              <span class="status-pill status-unread">unread {c.unread_count}</span>
              <span class="status-pill status-reading">reading {c.reading_count}</span>
              <span class="status-pill status-deep-read">deep-read {c.deep_read_count}</span>
              <span class="status-pill status-cited">cited {c.cited_count}</span>
            </div>
          </div>
        </details>
        """


# --- Section 3: Reading Queue (filterable paper list) -------------------


class ReadingQueueSection(DashboardSection):
    id = "reading-queue"
    title = "Reading queue"
    order = 30

    def __init__(self) -> None:
        self.id = "reading-queue"
        self.title = "Reading queue"
        self.order = 30

    def render(self, ctx: DashboardContext) -> str:
        if not ctx.papers:
            return f"""
        <section id="reading-queue" aria-labelledby="reading-queue-heading">
          <h2 id="reading-queue-heading">Reading queue</h2>
          <p class="empty-state">Add papers via
            <code>research-hub add &lt;doi&gt;</code>.</p>
        </section>
        """
        rows = "".join(self._row(p) for p in ctx.papers)
        chips = "".join(
            f'<button type="button" class="filter-chip" data-status="{html_escape(s)}">{label}</button>'
            for s, label in [
                ("all", "All"),
                ("unread", "Unread"),
                ("reading", "Reading"),
                ("deep-read", "Deep-read"),
                ("cited", "Cited"),
            ]
        )
        return f"""
        <section id="reading-queue" aria-labelledby="reading-queue-heading">
          <h2 id="reading-queue-heading">Reading queue</h2>
          <div class="filter-bar" role="group" aria-label="Filter by status">{chips}</div>
          <div class="reading-queue-wrap">
            <table class="reading-queue">
              <thead>
                <tr>
                  <th data-sort="title" tabindex="0" role="columnheader" aria-sort="none">Title <span class="sort-arrow"></span></th>
                  <th data-sort="cluster" tabindex="0" role="columnheader" aria-sort="none">Cluster <span class="sort-arrow"></span></th>
                  <th data-sort="year" tabindex="0" role="columnheader" aria-sort="none">Year <span class="sort-arrow"></span></th>
                  <th data-sort="status" tabindex="0" role="columnheader" aria-sort="none">Status <span class="sort-arrow"></span></th>
                  <th>Mark</th>
                </tr>
              </thead>
              <tbody id="paper-rows">{rows}</tbody>
            </table>
          </div>
          <button type="button" id="show-more" class="show-more" hidden>Show more</button>
        </section>
        """

    def _row(self, p: PaperRow) -> str:
        copy_cmd = f"research-hub mark {p.slug} --status deep-read"
        return f"""
        <tr class="paper-row" tabindex="0"
            data-title="{html_escape(p.title.lower())}"
            data-cluster="{html_escape(p.cluster_slug)}"
            data-year="{html_escape(p.year)}"
            data-status="{html_escape(p.status)}">
          <td><span class="paper-title">{html_escape(p.title)}</span>
              <code class="paper-slug">{html_escape(p.slug)}</code></td>
          <td><span class="cluster-tag">{html_escape(p.cluster_name)}</span></td>
          <td>{html_escape(p.year)}</td>
          <td><span class="status-pill status-{html_escape(p.status)}">{html_escape(p.status)}</span></td>
          <td><button type="button" class="copy-button"
                      data-copy="{html_escape(copy_cmd)}"
                      aria-label="Copy mark command for {html_escape(p.title)}">Copy ⧉</button></td>
        </tr>
        """


# --- Section 4: Activity feed -------------------------------------------


class ActivitySection(DashboardSection):
    id = "activity"
    title = "Recent activity"
    order = 40

    def __init__(self) -> None:
        self.id = "activity"
        self.title = "Recent activity"
        self.order = 40

    def render(self, ctx: DashboardContext) -> str:
        if not ctx.activity:
            return f"""
        <section id="activity" aria-labelledby="activity-heading">
          <h2 id="activity-heading">Recent activity</h2>
          <p class="empty-state">No pipeline runs recorded yet.</p>
        </section>
        """
        items = "".join(self._row(e) for e in ctx.activity)
        return f"""
        <section id="activity" aria-labelledby="activity-heading">
          <h2 id="activity-heading">Recent activity</h2>
          <ol class="activity-feed">{items}</ol>
        </section>
        """

    def _row(self, e: ActivityEvent) -> str:
        ts = (e.timestamp or "")[:16].replace("T", " ")
        action_class = "activity-error" if e.error else f"activity-{html_escape(e.action)}"
        return f"""
        <li class="activity-item {action_class}">
          <span class="activity-ts">{html_escape(ts)}</span>
          <span class="activity-action">{html_escape(e.action or 'event')}</span>
          <span class="activity-cluster">{html_escape(e.cluster)}</span>
          <span class="activity-title">{html_escape(e.title)}</span>
        </li>
        """


# --- Section 5: NotebookLM artifacts ------------------------------------


class NotebookLMSection(DashboardSection):
    id = "notebooklm"
    title = "NotebookLM artifacts"
    order = 50

    def __init__(self) -> None:
        self.id = "notebooklm"
        self.title = "NotebookLM artifacts"
        self.order = 50

    def render(self, ctx: DashboardContext) -> str:
        if not ctx.show_nlm_section:
            return ""
        cards = "".join(self._card(a) for a in ctx.nlm_artifacts)
        return f"""
        <section id="notebooklm" aria-labelledby="notebooklm-heading">
          <h2 id="notebooklm-heading">NotebookLM artifacts</h2>
          <div class="nlm-grid">{cards}</div>
        </section>
        """

    def _card(self, a: NLMArtifact) -> str:
        downloaded = (a.downloaded_at or "")[:16].replace("T", " ")
        link_html = ""
        if a.notebook_url:
            link_html = (
                f'<a class="nlm-link" href="{html_escape(a.notebook_url)}" '
                'target="_blank" rel="noreferrer noopener">Open notebook</a>'
            )
        return f"""
        <article class="nlm-card" data-cluster="{html_escape(a.cluster_slug)}">
          <header>
            <h3>{html_escape(a.cluster_name)}</h3>
            <span class="nlm-meta">briefing · {a.char_count} chars · {html_escape(downloaded)}</span>
          </header>
          <code class="nlm-path">{html_escape(a.brief_path)}</code>
          <div class="nlm-actions">{link_html}</div>
        </article>
        """


DEFAULT_SECTIONS: list[DashboardSection] = [
    OverviewSection(),
    ClustersSection(),
    ReadingQueueSection(),
    ActivitySection(),
    NotebookLMSection(),
]
