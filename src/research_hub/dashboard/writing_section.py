from __future__ import annotations

from collections import defaultdict

from research_hub.dashboard.sections import DashboardSection, _attr, html_escape
from research_hub.writing import build_inline_citation, build_markdown_citation


class WritingSection(DashboardSection):
    """Writing tab: captured quotes + cited-status papers."""

    id = "writing"
    title = "Writing"
    order = 35

    def __init__(self) -> None:
        self.id = "writing"
        self.title = "Writing"
        self.order = 35

    def render(self, data) -> str:
        quotes = list(_attr(data, "quotes", []) or [])
        cited = self._find_cited_papers(data)
        if not quotes and not cited:
            return """
        <section id="tab-writing" class="dash-panel dash-panel-writing" role="tabpanel">
          <div class="writing-empty">
            <p class="empty-state">No captured quotes yet and no papers are marked cited.</p>
            <p class="section-meta">Use the Quote button in Library to capture excerpts while you draft.</p>
          </div>
        </section>
        """

        quote_groups = self._group_quotes(quotes)
        cited_groups = self._group_cited(cited)
        composer = self._composer_panel(data, quotes)
        quote_html = (
            "".join(self._quote_group(name, items) for name, items in quote_groups.items())
            if quote_groups
            else '<p class="empty-state">No captured quotes yet.</p>'
        )
        cited_html = (
            "".join(self._cited_group(name, items) for name, items in cited_groups.items())
            if cited_groups
            else '<p class="empty-state">No papers are marked <code>cited</code> yet.</p>'
        )
        return f"""
        <section id="tab-writing" class="dash-panel dash-panel-writing" role="tabpanel">
          <div class="writing-grid">
            <article class="card writing-column">
              <header class="card-heading">
                <h2>Captured quotes</h2>
                <p class="card-meta">Saved excerpts ready to copy into a draft.</p>
              </header>
              <div class="writing-stack">{quote_html}</div>
              <div class="writing-cited-block">
                <header class="card-heading">
                  <h2>Cited papers</h2>
                  <p class="card-meta">Notes already marked <code>cited</code> in frontmatter.</p>
                </header>
                <div class="writing-stack">{cited_html}</div>
              </div>
            </article>
            {composer}
          </div>
        </section>
        """

    def _find_cited_papers(self, data) -> list:
        out = []
        for cluster in _attr(data, "clusters", []) or []:
            for paper in _attr(cluster, "papers", []) or []:
                if _attr(paper, "status", "") == "cited":
                    out.append((cluster, paper))
        return out

    def _group_quotes(self, quotes: list) -> dict[str, list]:
        grouped: dict[str, list] = defaultdict(list)
        for quote in quotes:
            cluster_name = str(_attr(quote, "cluster_name", "") or _attr(quote, "cluster_slug", "") or "Unassigned")
            grouped[cluster_name].append(quote)
        return dict(sorted(grouped.items(), key=lambda item: item[0].lower()))

    def _group_cited(self, cited: list[tuple[object, object]]) -> dict[str, list]:
        grouped: dict[str, list] = defaultdict(list)
        for cluster, paper in cited:
            grouped[str(_attr(cluster, "name", "") or "Unassigned")].append((cluster, paper))
        return dict(sorted(grouped.items(), key=lambda item: item[0].lower()))

    def _quote_group(self, cluster_name: str, quotes: list) -> str:
        cards = "".join(self._quote_card(quote) for quote in quotes)
        return f"""
        <section class="writing-group">
          <header class="writing-group-header">
            <span class="writing-cluster-tag">{html_escape(cluster_name)}</span>
            <span class="writing-group-count">{len(quotes)} quote{'s' if len(quotes) != 1 else ''}</span>
          </header>
          <div class="writing-stack">{cards}</div>
        </section>
        """

    def _quote_card(self, quote) -> str:
        page = str(_attr(quote, "page", "") or "").strip()
        text = str(_attr(quote, "text", "") or "").strip()
        title = str(_attr(quote, "title", _attr(quote, "slug", "")) or "")
        inline = build_inline_citation(
            {
                "authors": _attr(quote, "authors", ""),
                "year": _attr(quote, "year", ""),
                "slug": _attr(quote, "slug", ""),
                "title": title,
            }
        )
        markdown = build_markdown_citation(
            {
                "authors": _attr(quote, "authors", ""),
                "year": _attr(quote, "year", ""),
                "doi": _attr(quote, "doi", ""),
                "title": title,
            }
        )
        markdown_payload = f'> {text.replace(chr(10), chr(10) + "> ")}'
        if page:
            markdown_payload += f"\n>\n> Source: {markdown}, p. {page}"
        else:
            markdown_payload += f"\n>\n> Source: {markdown}"
        delete_cmd = (
            f'research-hub quote remove "{_attr(quote, "slug", "")}" '
            f'--at "{_attr(quote, "captured_at", "")}"'
        )
        page_badge = f'<span class="writing-quote-page">p. {html_escape(page)}</span>' if page else ""
        note = str(_attr(quote, "context_note", "") or "").strip()
        note_html = f'<p class="writing-quote-note">{html_escape(note)}</p>' if note else ""
        return f"""
        <article class="writing-quote-card" data-select-id="{html_escape(_attr(quote, "slug", ""))}">
          <header class="writing-quote-header">
            <div>
              <h3>{html_escape(title)}</h3>
              <p class="writing-quote-meta">{html_escape(_attr(quote, "authors", ""))}</p>
            </div>
            {page_badge}
          </header>
          <blockquote class="writing-quote-text">{html_escape(text)}</blockquote>
          {note_html}
          <div class="writing-quote-actions">
            <button type="button" class="copy-cmd-btn" data-text="{html_escape(markdown_payload)}">Copy as markdown</button>
            <button type="button" class="copy-cmd-btn" data-text="{html_escape(inline + (', p. ' + page if page else ''))}">Copy inline</button>
            <button type="button" class="copy-cmd-btn" data-text="{html_escape(delete_cmd)}">Delete</button>
          </div>
        </article>
        """

    def _cited_group(self, cluster_name: str, cited: list[tuple[object, object]]) -> str:
        items = "".join(self._cited_item(cluster, paper) for cluster, paper in cited)
        return f"""
        <section class="writing-group">
          <header class="writing-group-header">
            <span class="writing-cluster-tag">{html_escape(cluster_name)}</span>
            <span class="writing-group-count">{len(cited)} cited</span>
          </header>
          <div class="writing-stack">{items}</div>
        </section>
        """

    def _cited_item(self, cluster, paper) -> str:
        citation = build_markdown_citation(
            {
                "authors": _attr(paper, "authors", ""),
                "year": _attr(paper, "year", ""),
                "doi": _attr(paper, "doi", ""),
                "title": _attr(paper, "title", _attr(paper, "slug", "")),
            }
        )
        return f"""
        <article class="writing-cited-card">
          <h3>{html_escape(_attr(paper, "title", _attr(paper, "slug", "")))}</h3>
          <p class="writing-quote-meta">{html_escape(_attr(paper, "authors", ""))}</p>
          <p class="writing-cited-links">
            <span class="writing-cited-status">Marked cited</span>
            <button type="button" class="copy-cmd-btn" data-text="{html_escape(citation)}">Copy citation</button>
            <button type="button" class="copy-cmd-btn" data-text="{html_escape('research-hub cite --inline ' + str(_attr(paper, 'slug', '')))}">Copy inline command</button>
          </p>
        </article>
        """

    def _composer_panel(self, data, quotes: list) -> str:
        clusters = list(_attr(data, "clusters", []) or [])
        cluster_options = "".join(
            (
                f'<option value="{html_escape(_attr(cluster, "slug", ""))}">'
                f'{html_escape(_attr(cluster, "name", _attr(cluster, "slug", "")))}'
                "</option>"
            )
            for cluster in clusters
        )
        quote_options = self._composer_quote_options(clusters, quotes)
        return f"""
        <article class="composer-panel">
          <h3>Compose draft</h3>
          <form class="composer-form" action="javascript:void(0)">
            <label>Cluster
              <select name="cluster">
                {cluster_options}
              </select>
            </label>
            <label>Outline (one section per line, leave blank for single "Notes" section)
              <textarea name="outline" rows="4" placeholder="Introduction&#10;Methods&#10;Findings"></textarea>
            </label>
            <fieldset class="composer-style">
              <legend>Citation style</legend>
              <label><input type="radio" name="style" value="apa" checked> APA</label>
              <label><input type="radio" name="style" value="chicago"> Chicago</label>
              <label><input type="radio" name="style" value="mla"> MLA</label>
              <label><input type="radio" name="style" value="latex"> LaTeX</label>
            </fieldset>
            <label>
              <input type="checkbox" name="include_bibliography" checked> Include bibliography
            </label>
            <div class="composer-quote-list">
              {quote_options}
            </div>
            <button type="button" class="composer-build-btn manage-build-btn">Build draft command</button>
          </form>
          <pre class="composer-cmd-preview" hidden></pre>
        </article>
        """

    def _composer_quote_options(self, clusters: list, quotes: list) -> str:
        cluster_name_by_slug = {
            str(_attr(cluster, "slug", "") or ""): str(_attr(cluster, "name", "") or "")
            for cluster in clusters
        }
        grouped: dict[str, dict[str, object]] = {}
        for quote in quotes:
            slug = str(_attr(quote, "slug", "") or "").strip()
            if not slug:
                continue
            if slug in grouped:
                continue
            cluster_slug = str(_attr(quote, "cluster_slug", "") or "").strip()
            grouped[slug] = {
                "cluster_slug": cluster_slug,
                "cluster_name": cluster_name_by_slug.get(
                    cluster_slug,
                    str(_attr(quote, "cluster_name", "") or cluster_slug or "Unassigned"),
                ),
                "title": str(_attr(quote, "title", slug) or slug),
                "authors": str(_attr(quote, "authors", "") or ""),
            }
        if not grouped:
            return '<p class="empty-state">No captured quotes available for draft composition yet.</p>'

        rows = []
        for slug, item in sorted(grouped.items(), key=lambda pair: str(pair[1]["title"]).lower()):
            meta = html_escape(str(item["authors"] or item["cluster_name"]))
            rows.append(
                f"""
                <label class="composer-quote-option" data-select-id="{html_escape(slug)}" data-cluster="{html_escape(str(item["cluster_slug"]))}">
                  <input type="checkbox" checked data-slug="{html_escape(slug)}" data-cluster="{html_escape(str(item["cluster_slug"]))}">
                  <span><strong>{html_escape(str(item["title"]))}</strong><br>{meta}</span>
                </label>
                """
            )
        return "".join(rows)
