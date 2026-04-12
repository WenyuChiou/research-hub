"""Dashboard sections for the v0.10 personal knowledge garden layout."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


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


def _attr(obj: object, name: str, default: object = "") -> object:
    return getattr(obj, name, default)


def _bool_status(value: bool) -> str:
    return "status-yes" if value else "status-no"


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].strip()
    return (cut or text[:limit]).rstrip(" .,;:") + "..."


def _relative_time(value: str) -> str:
    if not value:
        return "unknown"
    try:
        ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - ts
    seconds = max(int(delta.total_seconds()), 0)
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    days = seconds // 86400
    if days < 30:
        return f"{days} day{'s' if days != 1 else ''} ago"
    months = days // 30
    if months < 12:
        return f"{months} month{'s' if months != 1 else ''} ago"
    years = days // 365
    return f"{years} year{'s' if years != 1 else ''} ago"


def _paper_count(cluster: object) -> int:
    papers = _attr(cluster, "papers", None)
    if isinstance(papers, list):
        return len(papers)
    return int(_attr(cluster, "paper_count", 0) or 0)


def _cluster_new_this_week(cluster: object) -> int:
    if hasattr(cluster, "new_this_week"):
        return int(_attr(cluster, "new_this_week", 0) or 0)
    return 0


def _cluster_last_activity(cluster: object) -> str:
    return str(_attr(cluster, "last_activity", "") or _attr(cluster, "latest_ingested_at", ""))


def _cluster_notebook_url(cluster: object) -> str:
    return str(_attr(cluster, "notebooklm_notebook_url", "") or "")


@dataclass
class DashboardSection:
    """Base class for all dashboard sections."""

    id: str = ""
    title: str = ""
    order: int = 0

    def render(self, data) -> str:  # pragma: no cover - abstract
        raise NotImplementedError


class HeaderSection(DashboardSection):
    id = "header"
    title = "Header"
    order = 10

    def __init__(self) -> None:
        self.id = "header"
        self.title = "Header"
        self.order = 10

    def render(self, data) -> str:
        stat_strip = (
            f"{int(_attr(data, 'total_papers', 0) or 0)} papers "
            f"· {int(_attr(data, 'total_clusters', 0) or 0)} clusters "
            f"· +{int(_attr(data, 'papers_this_week', 0) or 0)} this week"
        )
        return f"""
        <section id="vault-header" aria-labelledby="vault-title">
          <div class="hero-copy">
            <p class="eyebrow">Personal knowledge garden</p>
            <h1 id="vault-title">research-hub vault</h1>
            <p class="stat-strip">{html_escape(stat_strip)}</p>
          </div>
          <label class="search-label" for="vault-search">Search the vault</label>
          <input type="search" id="vault-search" class="vault-search"
                 placeholder="Search clusters, titles, or tags"
                 aria-label="Search clusters, titles, or tags">
        </section>
        """


class ClusterListSection(DashboardSection):
    id = "clusters"
    title = "Clusters"
    order = 20

    def __init__(self) -> None:
        self.id = "clusters"
        self.title = "Clusters"
        self.order = 20

    def render(self, data) -> str:
        clusters = list(_attr(data, "clusters", []) or [])
        clusters.sort(key=lambda item: _cluster_last_activity(item), reverse=True)
        first_open_slug = ""
        for cluster in clusters:
            if _cluster_new_this_week(cluster) > 0:
                first_open_slug = str(_attr(cluster, "slug", ""))
                break
        cards = "".join(self._render_cluster(cluster, data, first_open_slug) for cluster in clusters)
        empty = ""
        if not clusters:
            empty = (
                '<p class="empty-state">No clusters yet. '
                'Run <code>research-hub clusters new --query &quot;topic&quot;</code> to create one.</p>'
            )
        return f"""
        <section id="cluster-list" aria-labelledby="cluster-list-heading">
          <div class="section-heading">
            <h2 id="cluster-list-heading">Clusters</h2>
            <p class="section-meta">Browse active topics and inspect paper-level coverage.</p>
          </div>
          <div class="cluster-stack">{cards or empty}</div>
        </section>
        """

    def _render_cluster(self, cluster, data, first_open_slug: str) -> str:
        slug = str(_attr(cluster, "slug", ""))
        name = str(_attr(cluster, "name", slug))
        paper_count = _paper_count(cluster)
        new_this_week = _cluster_new_this_week(cluster)
        open_attr = " open" if slug and slug == first_open_slug else ""
        summary_suffix = f" +{new_this_week} new" if new_this_week > 0 else ""
        last_activity = _relative_time(_cluster_last_activity(cluster))
        status_parts = []
        if bool(_attr(data, "show_zotero_column", False)):
            status_parts.append(f"Z {int(_attr(cluster, 'zotero_count', 0) or 0)}")
        status_parts.extend(
            [
                f"O {int(_attr(cluster, 'obsidian_count', 0) or 0)}",
                f"N {int(_attr(cluster, 'nlm_count', 0) or 0)}",
            ]
        )
        notebook_link = ""
        notebook_url = _cluster_notebook_url(cluster)
        if notebook_url:
            notebook_link = (
                f'<a class="cluster-link" href="{html_escape(notebook_url)}" '
                'target="_blank" rel="noreferrer noopener">Open notebook</a>'
            )
        cluster_cite = ""
        if bool(_attr(data, "show_cite_buttons", False)):
            cluster_cite = (
                f'<button class="cluster-cite-btn" data-cluster="{html_escape(slug)}" '
                f'data-bibtex="{html_escape(_attr(cluster, "cluster_bibtex", ""))}">'
                "Download cluster .bib</button>"
            )
        papers = list(_attr(cluster, "papers", []) or [])
        if not papers:
            empty_line = (
                "Run <code>research-hub add &lt;doi&gt;</code> to populate this cluster"
                if hasattr(cluster, "papers")
                else "No papers in this legacy snapshot."
            )
            return f"""
            <details class="cluster-card" data-cluster="{html_escape(slug)}"{open_attr}>
              <summary>
                <div class="cluster-summary">
                  <h3>{html_escape(name)}</h3>
                  <p>{paper_count} papers{html_escape(summary_suffix)}</p>
                </div>
                <div class="cluster-summary-meta">
                  <code>{html_escape(' · '.join(status_parts))}</code>
                  <span class="cluster-last-activity">{html_escape(last_activity)}</span>
                </div>
              </summary>
              <div class="cluster-body">
                <div class="cluster-toolbar">{cluster_cite}{notebook_link}</div>
                <p class="cluster-empty">{empty_line}</p>
              </div>
            </details>
            """
        items = "".join(
            self._render_paper(paper, slug, notebook_url, bool(_attr(data, "show_cite_buttons", False)))
            for paper in papers
        )
        return f"""
        <details class="cluster-card" data-cluster="{html_escape(slug)}"{open_attr}>
          <summary>
            <div class="cluster-summary">
              <h3>{html_escape(name)}</h3>
              <p>{paper_count} papers{html_escape(summary_suffix)}</p>
            </div>
            <div class="cluster-summary-meta">
              <code>{html_escape(' · '.join(status_parts))}</code>
              <span class="cluster-last-activity">{html_escape(last_activity)}</span>
            </div>
          </summary>
          <div class="cluster-body">
            <div class="cluster-toolbar">{cluster_cite}{notebook_link}</div>
            <ol class="paper-list">{items}</ol>
          </div>
        </details>
        """

    def _render_paper(self, paper, cluster_slug: str, notebook_url: str, show_cite: bool) -> str:
        tags = [str(tag) for tag in (_attr(paper, "tags", []) or [])]
        abstract = _truncate(str(_attr(paper, "abstract", "") or ""), 240)
        cite_button = ""
        if show_cite:
            cite_button = (
                f'<button class="cite-btn" data-bibtex="{html_escape(_attr(paper, "bibtex", ""))}" '
                f'data-slug="{html_escape(_attr(paper, "slug", "paper"))}" '
                f'aria-label="Cite {html_escape(_attr(paper, "title", ""))}">Cite</button>'
            )
        zotero_badge = ""
        if show_cite:
            zotero_badge = (
                f'<span class="status-badge {_bool_status(bool(_attr(paper, "in_zotero", False)))}" title="Zotero">Z</span>'
            )
        return f"""
        <li class="paper-row" data-cluster="{html_escape(cluster_slug)}"
            data-title="{html_escape(str(_attr(paper, 'title', '')).lower())}"
            data-tags="{html_escape(' '.join(tags).lower())}">
          <div class="paper-content">
            <div class="paper-meta">
              <strong class="paper-authors">{html_escape(_attr(paper, "authors", ""))}</strong>
              <span class="paper-year">{html_escape(_attr(paper, "year", ""))}</span>
            </div>
            <h3 class="paper-title">{html_escape(_attr(paper, "title", ""))}</h3>
            <p class="paper-abstract">{html_escape(abstract)}</p>
            <div class="paper-status-row">
              {zotero_badge}
              <span class="status-badge {_bool_status(bool(_attr(paper, "in_obsidian", False)))}" title="Obsidian">O</span>
              <span class="status-badge {_bool_status(bool(_attr(paper, "in_nlm", False)))}" title="NotebookLM">N</span>
              <span class="reading-status status-{html_escape(_attr(paper, "status", "unread"))}">{html_escape(_attr(paper, "status", "unread"))}</span>
            </div>
          </div>
          <div class="paper-actions">
            {cite_button}
            <button class="open-btn" data-doi="{html_escape(_attr(paper, 'doi', ''))}"
                    data-zotero-key="{html_escape(_attr(paper, 'zotero_key', ''))}"
                    data-obsidian-path="{html_escape(_attr(paper, 'obsidian_path', ''))}"
                    data-nlm-url="{html_escape(notebook_url)}"
                    aria-label="Open {html_escape(_attr(paper, 'title', ''))}">Open</button>
          </div>
        </li>
        """


class BriefingShelfSection(DashboardSection):
    id = "briefings"
    title = "AI Briefings"
    order = 30

    def __init__(self) -> None:
        self.id = "briefings"
        self.title = "AI Briefings"
        self.order = 30

    def render(self, data) -> str:
        briefings = list(_attr(data, "briefings", []) or [])
        if not briefings and hasattr(data, "nlm_artifacts"):
            for artifact in list(_attr(data, "nlm_artifacts", []) or []):
                briefings.append(
                    type(
                        "LegacyBriefing",
                        (),
                        {
                            "cluster_name": _attr(artifact, "cluster_name", ""),
                            "char_count": int(_attr(artifact, "char_count", 0) or 0),
                            "downloaded_at": _attr(artifact, "downloaded_at", ""),
                            "preview_text": "",
                            "notebook_url": _attr(artifact, "notebook_url", ""),
                            "full_text": "",
                        },
                    )()
                )
        if not briefings:
            cards = """
            <article class="briefing-card briefing-empty">
              <p>No briefings downloaded yet. Run <code>research-hub notebooklm download --cluster &lt;slug&gt;</code> to fetch one.</p>
            </article>
            """
        else:
            cards = "".join(self._render_briefing(briefing) for briefing in briefings)
        return f"""
        <section id="briefings" aria-labelledby="briefings-heading">
          <div class="section-heading">
            <h2 id="briefings-heading">AI Briefings</h2>
            <p class="section-meta">NotebookLM outputs kept close to the source clusters.</p>
          </div>
          <div class="briefing-grid">{cards}</div>
        </section>
        """

    def _render_briefing(self, briefing) -> str:
        preview_text = str(_attr(briefing, "preview_text", "") or "")
        return f"""
        <article class="briefing-card">
          <header>
            <h3>{html_escape(_attr(briefing, "cluster_name", ""))}</h3>
            <span class="briefing-meta">{int(_attr(briefing, "char_count", 0) or 0)} chars · {html_escape(_relative_time(str(_attr(briefing, "downloaded_at", "") or '')))}</span>
          </header>
          <details>
            <summary>Show preview</summary>
            <p class="briefing-preview">{html_escape(preview_text)}</p>
            <div class="briefing-actions">
              <a class="btn-primary" href="{html_escape(_attr(briefing, 'notebook_url', ''))}" target="_blank"
                 rel="noreferrer noopener">Open in NotebookLM</a>
              <button class="copy-brief-btn"
                      data-text="{html_escape(_attr(briefing, 'full_text', ''))}">Copy full text</button>
            </div>
          </details>
        </article>
        """


class DiagnosticsSection(DashboardSection):
    id = "diagnostics"
    title = "Diagnostics"
    order = 90

    def __init__(self) -> None:
        self.id = "diagnostics"
        self.title = "Diagnostics"
        self.order = 90

    def render(self, data) -> str:
        badges = list(_attr(data, "health_badges", []) or [])
        alerts = list(_attr(data, "drift_alerts", []) or [])
        badge_items = "".join(
            f'<li class="health-{str(_attr(badge, "status", "WARN")).lower()}">'
            f'{html_escape(_attr(badge, "subsystem", ""))} '
            f'{html_escape(_attr(badge, "status", ""))} '
            f'{html_escape(_attr(badge, "summary", ""))}</li>'
            for badge in badges
        )
        if not badge_items:
            badge_items = '<li class="health-warn">No health badges reported.</li>'
        if alerts:
            drift_html = "".join(self._render_alert(alert) for alert in alerts)
        else:
            drift_html = '<p class="diag-empty">No drift detected.</p>'
        return f"""
        <section id="diagnostics">
          <details>
            <summary>Diagnostics - health, drift, and pending actions</summary>
            <div class="diag-grid">
              <div class="diag-health">
                <h3>System health</h3>
                <ul>{badge_items}</ul>
              </div>
              <div class="diag-drift">
                <h3>Drift alerts</h3>
                {drift_html}
              </div>
            </div>
          </details>
        </section>
        """

    def _render_alert(self, alert) -> str:
        samples = "".join(f"<li>{html_escape(path)}</li>" for path in list(_attr(alert, "sample_paths", []) or []))
        fix_command = str(_attr(alert, "fix_command", "") or "")
        copy_button = ""
        if fix_command:
            copy_button = f'<button class="copy-brief-btn" data-text="{html_escape(fix_command)}">Copy fix command</button>'
        return f"""
        <article class="drift-card drift-{str(_attr(alert, "severity", "WARN")).lower()}">
          <h4>{html_escape(_attr(alert, "title", ""))}</h4>
          <p>{html_escape(_attr(alert, "description", ""))}</p>
          <ul class="sample-paths">{samples}</ul>
          <div class="drift-actions">
            <code>{html_escape(fix_command)}</code>
            {copy_button}
          </div>
        </article>
        """


DEFAULT_SECTIONS: list[DashboardSection] = [
    HeaderSection(),
    ClusterListSection(),
    BriefingShelfSection(),
    DiagnosticsSection(),
]

OverviewSection = HeaderSection
ClustersSection = ClusterListSection
ReadingQueueSection = BriefingShelfSection
ActivitySection = DiagnosticsSection
NotebookLMSection = BriefingShelfSection
