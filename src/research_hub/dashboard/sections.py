"""Dashboard sections — v0.10.0-C tabbed audit + locator layout.

The dashboard answers ONE question: "AI added a bunch of papers — what
did it add, what categories, where are they stored across Zotero /
Obsidian / NotebookLM?" Five tabs:

  HeaderSection      (order 0,  always rendered, holds the tab radios)
  OverviewSection    (order 10, treemap + storage map + recent feed)
  LibrarySection     (order 20, cluster -> paper rows, no status badges)
  BriefingsSection   (order 30, AI brief inline previews)
  DiagnosticsSection (order 40, health + drift + actions)
  ManageSection      (order 50, command-builder forms for cluster CRUD)

Tab switching is pure CSS via radio buttons + ``:checked`` selectors —
zero JavaScript needed for the tab mechanic itself. Each tab panel is
a sibling ``<section>`` whose visibility is controlled by the chosen
radio. The legacy single-section names (Overview / Clusters / Reading
Queue / Activity / NotebookLM) remain at the bottom of this file as
aliases for backwards compat with v0.9.0-G1 imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


# --- helpers ------------------------------------------------------------


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


def _cluster_last_activity(cluster: object) -> str:
    return str(_attr(cluster, "last_activity", "") or _attr(cluster, "latest_ingested_at", ""))


def _zotero_collection_url(library_id: str, collection_key: str) -> str:
    if not collection_key:
        return ""
    if library_id:
        return f"zotero://select/library/collections/{collection_key}"
    return f"zotero://select/library/collections/{collection_key}"


def _obsidian_url(folder_path: str) -> str:
    if not folder_path:
        return ""
    safe = folder_path.replace("\\", "/")
    return f"obsidian://open?path={safe}"


def _all_clusters(data) -> list:
    return list(_attr(data, "clusters", []) or [])


def _all_papers_with_cluster(data) -> list[tuple[object, object]]:
    """Yield (cluster, paper) tuples across all clusters."""
    out: list[tuple[object, object]] = []
    for cluster in _all_clusters(data):
        for paper in _attr(cluster, "papers", []) or []:
            out.append((cluster, paper))
    return out


def _persona(data) -> str:
    return str(_attr(data, "persona", "researcher") or "researcher")


def _show_zotero_column(data) -> bool:
    return _persona(data) != "analyst"


# --- base ---------------------------------------------------------------


@dataclass
class DashboardSection:
    """Base class for all dashboard sections."""

    id: str = ""
    title: str = ""
    order: int = 0

    def render(self, data) -> str:  # pragma: no cover - abstract
        raise NotImplementedError


# --- HeaderSection (tab radios live here) -------------------------------


_TAB_DEFS = [
    ("overview", "Overview"),
    ("library", "Library"),
    ("briefings", "Briefings"),
    ("writing", "Writing"),
    ("diagnostics", "Diagnostics"),
    ("manage", "Manage"),
]


class HeaderSection(DashboardSection):
    id = "header"
    title = "Header"
    order = 0

    def __init__(self) -> None:
        self.id = "header"
        self.title = "Header"
        self.order = 0

    def render(self, data) -> str:
        total_papers = int(_attr(data, "total_papers", 0) or 0)
        total_clusters = int(_attr(data, "total_clusters", 0) or 0)
        briefings = list(_attr(data, "briefings", []) or [])
        last_added = ""
        for cluster in _all_clusters(data):
            ts = _cluster_last_activity(cluster)
            if ts and ts > last_added:
                last_added = ts
        last_added_label = _relative_time(last_added) if last_added else "no activity"
        radios = "".join(
            (
                f'<input type="radio" name="dash-tab" id="dash-tab-{tab_id}" '
                f'class="dash-tab-radio dash-tab-radio-{tab_id}"'
                f'{" checked" if i == 0 else ""}>'
            )
            for i, (tab_id, _label) in enumerate(_TAB_DEFS)
        )
        labels = "".join(
            f'<label for="dash-tab-{tab_id}" class="dash-tab-label dash-tab-label-{tab_id}">{html_escape(label)}</label>'
            for tab_id, label in _TAB_DEFS
        )
        return (
            radios
            + f"""
        <header class="vault-header" id="vault-header">
          <div class="hero-copy">
            <p class="eyebrow">Personal knowledge garden</p>
            <h1 id="vault-title">research-hub vault</h1>
            <p class="stat-strip">{total_papers} papers · {total_clusters} clusters · {len(briefings)} briefings · last added {html_escape(last_added_label)}</p>
          </div>
          <label class="search-label" for="vault-search">Filter library</label>
          <input
            type="search"
            id="vault-search"
            class="vault-search"
            placeholder="Filter clusters, titles, or tags"
            aria-label="Filter library"
          >
        </header>
        <nav class="dash-tabs" role="tablist" aria-label="Dashboard sections">
          {labels}
        </nav>
        """
        )


# --- OverviewSection ----------------------------------------------------


class OverviewSection(DashboardSection):
    id = "overview"
    title = "Overview"
    order = 10

    def __init__(self) -> None:
        self.id = "overview"
        self.title = "Overview"
        self.order = 10

    def render(self, data) -> str:
        clusters = _all_clusters(data)
        treemap = self._render_treemap(clusters)
        storage = self._render_storage_map(clusters, _show_zotero_column(data))
        recent = self._render_recent_additions(data)
        banner = self._render_health_banner(data)
        return f"""
        <section id="tab-overview" class="dash-panel dash-panel-overview" role="tabpanel">
          {banner}
          <div class="overview-grid">
            <article class="card card-treemap">
              <header class="card-heading">
                <h2>Papers per cluster</h2>
                <p class="card-meta">Area is proportional to paper count.</p>
              </header>
              {treemap}
            </article>
            <article class="card card-storage">
              <header class="card-heading">
                <h2>Storage map</h2>
                <p class="card-meta">Where each cluster lives across Zotero, Obsidian, and NotebookLM.</p>
              </header>
              {storage}
            </article>
            <article class="card card-recent">
              <header class="card-heading">
                <h2>Recent additions</h2>
                <p class="card-meta">The 15 most recent papers your AI agent saved into the vault.</p>
              </header>
              {recent}
            </article>
          </div>
        </section>
        """

    def _render_health_banner(self, data) -> str:
        health_badges = list(_attr(data, "health_badges", []) or [])
        problems: list[str] = []
        for badge in health_badges:
            status = str(_attr(badge, "status", "OK") or "OK")
            if status == "FAIL":
                subsystem = str(_attr(badge, "subsystem", "") or "")
                items = list(_attr(badge, "items", []) or [])
                for item in items:
                    if isinstance(item, dict) and item.get("status") == "FAIL":
                        msg = str(item.get("message", "")).strip()
                        remedy = str(item.get("remedy", "")).strip()
                        line = f"{subsystem.title()}: {msg}"
                        if remedy:
                            line += f" — fix: {html_escape(remedy)}"
                        problems.append(html_escape(line))
        if not problems:
            return ""
        items = "".join(f"<li>{p}</li>" for p in problems)
        return f"""
        <div class="debug-banner is-visible" role="alert">
          <strong>Some checks failed.</strong>
          <ul style="margin: 4px 0 0; padding-left: 20px;">{items}</ul>
        </div>
        """

    def _render_treemap(self, clusters: list) -> str:
        if not clusters:
            return '<p class="empty-state">No clusters yet. Run <code>research-hub clusters new --query "topic"</code> to start.</p>'
        # Use sqrt scaling for flex weights so a vault with 7/8/331
        # papers does not collapse the small cells to unreadable
        # widths. Real counts are kept for display.
        counts = [max(_paper_count(c), 1) for c in clusters]
        real_total = sum(counts) or 1
        weights = [round(c ** 0.5, 2) for c in counts]
        cells = "".join(
            self._treemap_cell(cluster, count, weight, real_total)
            for cluster, count, weight in zip(clusters, counts, weights)
        )
        return f'<div class="treemap" role="img" aria-label="Cluster sizes">{cells}</div>'

    def _treemap_cell(self, cluster, count: int, flex_weight: float, real_total: int) -> str:
        slug = html_escape(_attr(cluster, "slug", ""))
        name = html_escape(_attr(cluster, "name", ""))
        share_pct = round((count / real_total) * 100, 1)
        # Use a button instead of a hash-linked anchor: the anchor
        # triggered Chrome's "unsafe attempt to load URL from frame"
        # security check when the page origin is file://. The button
        # falls back to a click handler in script.js that selects the
        # library tab radio without navigating the URL.
        return (
            f'<button type="button" class="treemap-cell" '
            f'data-jump-tab="library" '
            f'style="flex: {flex_weight} 1 0;" '
            f'data-cluster="{slug}" '
            f'aria-label="Jump to {name} in Library tab, {count} papers">'
            f'<span class="treemap-name">{name}</span>'
            f'<span class="treemap-count">{count}</span>'
            f'<span class="treemap-share">{share_pct}% of vault</span>'
            f'</button>'
        )

    def _render_storage_map(self, clusters: list, show_zotero: bool) -> str:
        if not clusters:
            return '<p class="empty-state">No clusters bound yet.</p>'
        rows = "".join(self._storage_row(c, show_zotero) for c in clusters)
        zotero_th = '<th scope="col">Zotero</th>' if show_zotero else ""
        return f"""
        <table class="storage-table">
          <thead>
            <tr>
              <th scope="col">Cluster</th>
              {zotero_th}
              <th scope="col">Obsidian</th>
              <th scope="col">NotebookLM</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
        """

    def _storage_row(self, cluster, show_zotero: bool) -> str:
        name = html_escape(_attr(cluster, "name", ""))
        count = int(_attr(cluster, "paper_count", 0) or _paper_count(cluster))
        slug = html_escape(_attr(cluster, "slug", ""))

        zotero_cell = ""
        if show_zotero:
            zk = str(_attr(cluster, "zotero_collection_key", "") or "")
            if zk:
                href = _zotero_collection_url("", zk)
                zotero_cell = (
                    f'<td class="storage-cell">'
                    f'<span class="storage-name">{html_escape(zk)}</span>'
                    f'<a class="storage-link" href="{html_escape(href)}">↗ Open</a>'
                    f'</td>'
                )
            else:
                zotero_cell = '<td class="storage-cell storage-empty">—</td>'

        obs_folder = f"raw/{slug}"
        obs_href = _obsidian_url(obs_folder)
        obs_cell = (
            f'<td class="storage-cell">'
            f'<span class="storage-name">{html_escape(obs_folder)}</span>'
            f'<a class="storage-link" href="{html_escape(obs_href)}">↗ Open</a>'
            f'</td>'
        )

        nlm_url = str(_attr(cluster, "notebooklm_notebook_url", "") or "")
        nlm_name = str(_attr(cluster, "notebooklm_notebook", "") or "")
        if nlm_url:
            nlm_cell = (
                f'<td class="storage-cell">'
                f'<span class="storage-name">{html_escape(nlm_name or "notebook")}</span>'
                f'<a class="storage-link" href="{html_escape(nlm_url)}" target="_blank" rel="noreferrer noopener">↗ Open</a>'
                f'</td>'
            )
        else:
            nlm_cell = '<td class="storage-cell storage-empty">—</td>'

        return (
            f'<tr>'
            f'<th scope="row" class="storage-cluster"><span class="storage-cluster-name">{name}</span><span class="storage-cluster-count">{count} papers</span></th>'
            f'{zotero_cell}{obs_cell}{nlm_cell}'
            f'</tr>'
        )

    def _render_recent_additions(self, data) -> str:
        rows: list[tuple[object, object, object]] = []
        for cluster in _all_clusters(data):
            for paper in _attr(cluster, "papers", []) or []:
                rows.append((cluster, paper, _attr(paper, "ingested_at", "")))
        if not rows:
            return '<p class="empty-state">No recent additions. Use <code>research-hub add &lt;doi&gt;</code> or have your AI agent ingest papers.</p>'
        rows.sort(key=lambda triple: str(triple[2] or ""), reverse=True)
        rows = rows[:15]
        items = "".join(self._recent_row(c, p, ts) for c, p, ts in rows)
        return f'<ol class="recent-feed">{items}</ol>'

    def _recent_row(self, cluster, paper, ingested_at) -> str:
        cluster_name = html_escape(_attr(cluster, "name", ""))
        cluster_url = str(_attr(cluster, "notebooklm_notebook_url", "") or "")
        title = html_escape(_attr(paper, "title", _attr(paper, "slug", "")))
        authors = html_escape(_attr(paper, "authors", ""))
        year = html_escape(_attr(paper, "year", ""))
        relative = html_escape(_relative_time(str(ingested_at or "")))
        doi = html_escape(_attr(paper, "doi", ""))
        zotero_key = html_escape(_attr(paper, "zotero_key", ""))
        obsidian_path = html_escape(_attr(paper, "obsidian_path", ""))
        return f"""
        <li class="recent-item">
          <div class="recent-meta">
            <span class="recent-time">{relative}</span>
            <span class="recent-cluster">{cluster_name}</span>
          </div>
          <div class="recent-body">
            <p class="recent-title">{title}</p>
            <p class="recent-author">{authors}{(' · ' + year) if year else ''}</p>
          </div>
          <button class="open-btn"
                  type="button"
                  data-doi="{doi}"
                  data-zotero-key="{zotero_key}"
                  data-obsidian-path="{obsidian_path}"
                  data-nlm-url="{html_escape(cluster_url)}"
                  aria-label="Open {title}">↗ Open</button>
        </li>
        """


# --- LibrarySection (cluster -> paper rows, no badges) ------------------


class LibrarySection(DashboardSection):
    id = "library"
    title = "Library"
    order = 20

    def __init__(self) -> None:
        self.id = "library"
        self.title = "Library"
        self.order = 20

    def render(self, data) -> str:
        clusters = _all_clusters(data)
        if not clusters:
            return """
        <section id="tab-library" class="dash-panel dash-panel-library" role="tabpanel">
          <p class="empty-state">No clusters yet. Run <code>research-hub clusters new --query "topic"</code>.</p>
        </section>
        """
        cards = "".join(self._cluster_card(c, _show_zotero_column(data)) for c in clusters)
        return f"""
        <section id="tab-library" class="dash-panel dash-panel-library" role="tabpanel">
          <div class="cluster-stack">{cards}</div>
        </section>
        """

    def _cluster_card(self, cluster, show_zotero: bool) -> str:
        slug = html_escape(_attr(cluster, "slug", ""))
        name = html_escape(_attr(cluster, "name", ""))
        count = int(_attr(cluster, "paper_count", 0) or _paper_count(cluster))
        last_activity = _relative_time(_cluster_last_activity(cluster))
        cluster_bibtex = html_escape(_attr(cluster, "cluster_bibtex", ""))
        has_overview = bool(_attr(cluster, "has_overview", False))
        binding_line = self._binding_line(cluster, show_zotero)
        overview_badge = (
            '<span class="cluster-badge">overview</span>'
            if has_overview
            else '<span class="cluster-badge cluster-badge--missing">no overview</span>'
        )
        overview_href = _obsidian_url(f"hub/{slug}/00_overview.md") if has_overview else ""
        summary_title = (
            f'<h3><a class="binding-link" href="{html_escape(overview_href)}">{name}</a> {overview_badge}</h3>'
            if overview_href
            else f"<h3>{name} {overview_badge}</h3>"
        )

        download_btn = ""
        if show_zotero and cluster_bibtex:
            download_btn = (
                f'<button type="button" class="cluster-cite-btn" '
                f'data-cluster="{slug}" '
                f'data-bibtex="{cluster_bibtex}">Download cluster .bib</button>'
            )

        papers = _attr(cluster, "papers", []) or []
        if not papers:
            paper_list = '<p class="cluster-empty">No papers yet in this cluster.</p>'
        else:
            paper_list = '<ol class="paper-list">' + "".join(
                self._paper_row(slug, p, show_zotero) for p in papers
            ) + '</ol>'

        return f"""
        <details class="cluster-card" data-cluster="{slug}">
          <summary>
            <div class="cluster-summary">
              {summary_title}
              <p>{count} paper{'s' if count != 1 else ''} · last activity {html_escape(last_activity)}</p>
            </div>
          </summary>
          <div class="cluster-body">
            <p class="cluster-bindings">{binding_line}</p>
            <div class="cluster-toolbar">{download_btn}</div>
            {paper_list}
          </div>
        </details>
        """

    def _binding_line(self, cluster, show_zotero: bool) -> str:
        parts: list[str] = []
        if show_zotero:
            zk = str(_attr(cluster, "zotero_collection_key", "") or "")
            if zk:
                parts.append(
                    f'Zotero · <a class="binding-link" href="{html_escape(_zotero_collection_url("", zk))}">{html_escape(zk)}</a>'
                )
            else:
                parts.append("Zotero · unbound")
        slug = str(_attr(cluster, "slug", ""))
        obs_path = f"raw/{slug}"
        parts.append(
            f'Obsidian · <a class="binding-link" href="{html_escape(_obsidian_url(obs_path))}">{html_escape(obs_path)}</a>'
        )
        nlm_url = str(_attr(cluster, "notebooklm_notebook_url", "") or "")
        nlm_name = str(_attr(cluster, "notebooklm_notebook", "") or "")
        if nlm_url:
            parts.append(
                f'NotebookLM · <a class="binding-link" href="{html_escape(nlm_url)}" target="_blank" rel="noreferrer noopener">{html_escape(nlm_name or "notebook")}</a>'
            )
        else:
            parts.append("NotebookLM · unbound")
        return " | ".join(parts)

    def _paper_row(self, cluster_slug: str, paper, show_zotero: bool) -> str:
        slug = html_escape(_attr(paper, "slug", ""))
        title = html_escape(_attr(paper, "title", slug))
        title_lower = html_escape(str(_attr(paper, "title", "")).lower())
        authors = html_escape(_attr(paper, "authors", ""))
        year = html_escape(_attr(paper, "year", ""))
        abstract = html_escape(_truncate(str(_attr(paper, "abstract", "") or ""), 240))
        doi = html_escape(_attr(paper, "doi", ""))
        zotero_key = html_escape(_attr(paper, "zotero_key", ""))
        obsidian_path = html_escape(_attr(paper, "obsidian_path", ""))
        tags_value = " ".join(str(t) for t in (_attr(paper, "tags", []) or [])).lower()
        tags = html_escape(tags_value)
        bibtex = html_escape(_attr(paper, "bibtex", ""))

        cite_button = ""
        if show_zotero and bibtex:
            cite_button = (
                f'<button type="button" class="cite-btn" '
                f'data-bibtex="{bibtex}" '
                f'data-slug="{slug}" '
                f'aria-label="Cite {title}">Cite</button>'
            )

        quote_button = (
            f'<button type="button" class="quote-btn" '
            f'data-slug="{slug}" '
            f'data-title="{title}" '
            f'data-doi="{doi}" '
            f'aria-label="Capture quote from {title}">Quote</button>'
        )
        meta_line = authors + ((" · " + year) if year else "")
        return f"""
        <li class="paper-row"
            data-cluster="{html_escape(cluster_slug)}"
            data-title="{title_lower}"
            data-tags="{tags}">
          <div class="paper-content">
            <p class="paper-author">{meta_line}</p>
            <h4 class="paper-title">{title}</h4>
            <p class="paper-abstract">{abstract}</p>
          </div>
          <div class="paper-actions">
            {cite_button}
            {quote_button}
            <button type="button" class="open-btn"
                    data-doi="{doi}"
                    data-zotero-key="{zotero_key}"
                    data-obsidian-path="{obsidian_path}"
                    data-nlm-url=""
                    aria-label="Open {title}">↗ Open</button>
          </div>
        </li>
        """


# --- BriefingsSection ---------------------------------------------------


class BriefingsSection(DashboardSection):
    id = "briefings"
    title = "Briefings"
    order = 30

    def __init__(self) -> None:
        self.id = "briefings"
        self.title = "Briefings"
        self.order = 30

    def render(self, data) -> str:
        briefings = list(_attr(data, "briefings", []) or [])
        if not briefings:
            return """
        <section id="tab-briefings" class="dash-panel dash-panel-briefings" role="tabpanel">
          <p class="empty-state">No briefings downloaded yet. Generate one with
            <code>research-hub notebooklm generate --cluster &lt;slug&gt; --type brief</code>
            and pull it back with
            <code>research-hub notebooklm download --cluster &lt;slug&gt;</code>.</p>
        </section>
        """
        cards = "".join(self._briefing_card(b) for b in briefings)
        return f"""
        <section id="tab-briefings" class="dash-panel dash-panel-briefings" role="tabpanel">
          <div class="briefing-grid">{cards}</div>
        </section>
        """

    def _briefing_card(self, briefing) -> str:
        cluster_name = html_escape(_attr(briefing, "cluster_name", ""))
        char_count = int(_attr(briefing, "char_count", 0) or 0)
        downloaded_at = html_escape(_relative_time(str(_attr(briefing, "downloaded_at", "") or "")))
        preview = html_escape(_attr(briefing, "preview_text", ""))
        full = html_escape(_attr(briefing, "full_text", ""))
        notebook_url = str(_attr(briefing, "notebook_url", "") or "")
        open_link = ""
        if notebook_url:
            open_link = (
                f'<a class="btn-primary" href="{html_escape(notebook_url)}" '
                f'target="_blank" rel="noreferrer noopener">↗ Open in NotebookLM</a>'
            )
        return f"""
        <article class="briefing-card">
          <header>
            <h3>{cluster_name}</h3>
            <span class="briefing-meta">{char_count} chars · {downloaded_at}</span>
          </header>
          <details>
            <summary>Show preview</summary>
            <p class="briefing-preview">{preview}</p>
            <div class="briefing-actions">
              {open_link}
              <button class="copy-brief-btn" type="button" data-text="{full}">Copy full text</button>
            </div>
          </details>
        </article>
        """


# --- DiagnosticsSection -------------------------------------------------


class DiagnosticsSection(DashboardSection):
    id = "diagnostics"
    title = "Diagnostics"
    order = 40

    def __init__(self) -> None:
        self.id = "diagnostics"
        self.title = "Diagnostics"
        self.order = 40

    def render(self, data) -> str:
        health = list(_attr(data, "health_badges", []) or [])
        drift = list(_attr(data, "drift_alerts", []) or [])
        return f"""
        <section id="tab-diagnostics" class="dash-panel dash-panel-diagnostics" role="tabpanel">
          <div class="diag-grid">
            <article class="card card-health">
              <header class="card-heading">
                <h2>System health</h2>
                <p class="card-meta">Subsystem checks rolled up by service.</p>
              </header>
              {self._health_block(health)}
            </article>
            <article class="card card-drift">
              <header class="card-heading">
                <h2>Drift alerts</h2>
                <p class="card-meta">Manual edits the pipeline noticed but did not fix.</p>
              </header>
              {self._drift_block(drift)}
            </article>
          </div>
        </section>
        """

    def _health_block(self, badges: list) -> str:
        if not badges:
            return '<p class="diag-empty">No health checks available.</p>'
        rows = "".join(self._health_row(b) for b in badges)
        return f'<ul class="health-list">{rows}</ul>'

    def _health_row(self, badge) -> str:
        subsystem = html_escape(_attr(badge, "subsystem", "") or "")
        status = str(_attr(badge, "status", "OK") or "OK")
        summary = html_escape(_attr(badge, "summary", "") or "")
        return (
            f'<li class="health-row health-{status.lower()}">'
            f'<strong class="health-name">{subsystem}</strong>'
            f'<span class="health-status">{html_escape(status)}</span>'
            f'<span class="health-summary">{summary}</span>'
            f'</li>'
        )

    def _drift_block(self, alerts: list) -> str:
        if not alerts:
            return '<p class="diag-empty">No drift detected.</p>'
        return "".join(self._drift_card(a) for a in alerts)

    def _drift_card(self, alert) -> str:
        kind = html_escape(_attr(alert, "kind", "") or "")
        severity = html_escape(str(_attr(alert, "severity", "WARN") or "WARN").lower())
        title = html_escape(_attr(alert, "title", "") or "")
        description = html_escape(_attr(alert, "description", "") or "")
        fix_command = html_escape(_attr(alert, "fix_command", "") or "")
        sample_paths = list(_attr(alert, "sample_paths", []) or [])
        sample_html = ""
        if sample_paths:
            sample_lis = "".join(f"<li><code>{html_escape(p)}</code></li>" for p in sample_paths[:5])
            sample_html = f'<ol class="sample-paths">{sample_lis}</ol>'
        copy_btn = ""
        if fix_command:
            copy_btn = (
                f'<button type="button" class="copy-cmd-btn" data-text="{fix_command}">Copy fix command</button>'
            )
        return f"""
        <div class="drift-card drift-{severity}" data-kind="{kind}">
          <h3>{title}</h3>
          <p>{description}</p>
          {sample_html}
          <div class="drift-actions">{copy_btn}</div>
        </div>
        """


# --- ManageSection (command builder forms for cluster CRUD) -------------


class ManageSection(DashboardSection):
    id = "manage"
    title = "Manage"
    order = 50

    def __init__(self) -> None:
        self.id = "manage"
        self.title = "Manage"
        self.order = 50

    def render(self, data) -> str:
        clusters = _all_clusters(data)
        if not clusters:
            return """
        <section id="tab-manage" class="dash-panel dash-panel-manage" role="tabpanel">
          <p class="empty-state">No clusters to manage yet.</p>
        </section>
        """
        slug_options = "".join(
            f'<option value="{html_escape(_attr(c, "slug", ""))}">{html_escape(_attr(c, "name", ""))}</option>'
            for c in clusters
        )
        cards = "".join(self._manage_card(c, slug_options) for c in clusters)
        return f"""
        <section id="tab-manage" class="dash-panel dash-panel-manage" role="tabpanel">
          <header class="manage-intro">
            <h2>Update categories</h2>
            <p>Each card builds the exact CLI command for the action. Click <em>Copy</em> and paste into your terminal — the dashboard cannot run commands itself.</p>
          </header>
          <div class="manage-grid">{cards}</div>
        </section>
        """

    def _manage_card(self, cluster, slug_options: str) -> str:
        slug = html_escape(_attr(cluster, "slug", ""))
        name = html_escape(_attr(cluster, "name", ""))
        return f"""
        <article class="manage-card" data-cluster="{slug}">
          <header><h3>{name}</h3><code>{slug}</code></header>

          <form class="manage-form" action="javascript:void(0)" data-action="rename" data-slug="{slug}">
            <label>Rename to <input type="text" name="new_name" placeholder="New display name"></label>
            <button type="button" class="manage-build-btn">Copy rename command</button>
          </form>

          <form class="manage-form" action="javascript:void(0)" data-action="merge" data-slug="{slug}">
            <label>Merge into
              <select name="target">
                <option value="">— pick target cluster —</option>
                {slug_options}
              </select>
            </label>
            <button type="button" class="manage-build-btn">Copy merge command</button>
          </form>

          <form class="manage-form" action="javascript:void(0)" data-action="split" data-slug="{slug}">
            <label>Split by query <input type="text" name="query" placeholder="keyword"></label>
            <label>New cluster name <input type="text" name="new_name" placeholder="Sub Topic"></label>
            <button type="button" class="manage-build-btn">Copy split command</button>
          </form>

          <form class="manage-form" action="javascript:void(0)" data-action="bind-zotero" data-slug="{slug}">
            <label>Bind Zotero collection key <input type="text" name="zotero" placeholder="ABCD1234"></label>
            <button type="button" class="manage-build-btn">Copy bind command</button>
          </form>

          <form class="manage-form" action="javascript:void(0)" data-action="bind-nlm" data-slug="{slug}">
            <label>Bind NotebookLM notebook name <input type="text" name="notebooklm" placeholder="My Notebook"></label>
            <button type="button" class="manage-build-btn">Copy bind command</button>
          </form>

          <form class="manage-form" action="javascript:void(0)" data-action="delete" data-slug="{slug}">
            <button type="button" class="manage-build-btn manage-danger">Copy delete dry-run command</button>
          </form>
        </article>
        """


# --- DEFAULT_SECTIONS + legacy aliases ----------------------------------


class DebugSection(DashboardSection):
    """Footer feedback widget — copy a debug snapshot for AI handoff.

    Always rendered (outside any tab) so the user can grab a paste
    blob if anything looks wrong on any panel. The blob includes:
    vault root, persona, totals, the worst health check messages,
    and a list of section IDs the user might want to reference.
    """

    id = "debug"
    title = "Debug"
    order = 100

    def __init__(self) -> None:
        self.id = "debug"
        self.title = "Debug"
        self.order = 100

    def render(self, data) -> str:
        snapshot = self._build_snapshot(data)
        return f"""
        <section class="debug-footer" id="debug-section" role="complementary">
          <h3>Spot a bug? Copy a debug snapshot.</h3>
          <p>The snapshot includes vault summary, persona, health check status,
             and section IDs. Paste it back to the AI assistant along with what
             you saw to get a fix.</p>
          <div class="debug-actions">
            <button type="button" class="debug-btn" id="debug-toggle-btn">Show snapshot</button>
            <button type="button" class="debug-btn" id="debug-copy-btn"
                    data-snapshot="{html_escape(snapshot)}">Copy snapshot to clipboard</button>
          </div>
          <pre class="debug-snapshot" id="debug-snapshot">{html_escape(snapshot)}</pre>
        </section>
        """

    def _build_snapshot(self, data) -> str:
        lines: list[str] = []
        lines.append("=== research-hub dashboard debug snapshot ===")
        lines.append(f"vault_root: {_attr(data, 'vault_root', '')}")
        lines.append(f"generated_at: {_attr(data, 'generated_at', '')}")
        lines.append(f"persona: {_attr(data, 'persona', '')}")
        lines.append(f"total_papers: {_attr(data, 'total_papers', 0)}")
        lines.append(f"total_clusters: {_attr(data, 'total_clusters', 0)}")
        lines.append("clusters:")
        for c in _all_clusters(data):
            lines.append(
                f"  - slug={_attr(c, 'slug', '')!r} "
                f"papers={_paper_count(c)} "
                f"zotero={_attr(c, 'zotero_collection_key', '') or 'unbound'} "
                f"nlm={'bound' if _attr(c, 'notebooklm_notebook_url', '') else 'unbound'}"
            )
        lines.append("health:")
        for badge in _attr(data, "health_badges", []) or []:
            lines.append(
                f"  - {_attr(badge, 'subsystem', '')}: "
                f"{_attr(badge, 'status', '')} {_attr(badge, 'summary', '')}".rstrip()
            )
        lines.append("drift_alerts:")
        for alert in _attr(data, "drift_alerts", []) or []:
            lines.append(
                f"  - {_attr(alert, 'kind', '')}: "
                f"{_attr(alert, 'severity', '')} {_attr(alert, 'title', '')}"
            )
        lines.append("sections: header overview library briefings writing diagnostics manage debug")
        lines.append("Paste this with: 'On the [tab] tab I see [problem]'")
        return "\n".join(lines)


from research_hub.dashboard.writing_section import WritingSection


DEFAULT_SECTIONS: list[DashboardSection] = [
    HeaderSection(),
    OverviewSection(),
    LibrarySection(),
    BriefingsSection(),
    WritingSection(),
    DiagnosticsSection(),
    ManageSection(),
    DebugSection(),
]


# v0.9.0-G1 backward-compat aliases — old imports keep working but the
# rendered output uses the new tabbed layout. New code should NOT use
# these names.
ClustersSection = LibrarySection
ReadingQueueSection = LibrarySection
ActivitySection = DiagnosticsSection
NotebookLMSection = BriefingsSection
BriefingShelfSection = BriefingsSection
ClusterListSection = LibrarySection
