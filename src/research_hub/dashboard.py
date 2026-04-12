"""Generate a personal HTML dashboard from the user's vault state."""

from __future__ import annotations

import json
import re
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from research_hub.clusters import ClusterRegistry
from research_hub.config import get_config
from research_hub.dedup import DedupIndex


@dataclass
class ClusterStats:
    slug: str
    name: str
    paper_count: int = 0
    status_breakdown: dict[str, int] = field(default_factory=dict)
    zotero_collection_key: str = ""
    notebooklm_notebook: str = ""
    notebooklm_notebook_url: str = ""
    latest_ingested_at: str = ""


def _read_frontmatter(md_path: Path) -> str:
    try:
        text = md_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    if end < 0:
        return ""
    return text[3:end]


def collect_vault_state(cfg) -> dict:
    """Walk the vault and collect the state needed by the dashboard."""
    registry = ClusterRegistry(cfg.clusters_file)
    dedup = DedupIndex.load(cfg.research_hub_dir / "dedup_index.json")
    nlm_cache: dict[str, dict] = {}
    nlm_cache_path = cfg.research_hub_dir / "nlm_cache.json"
    if nlm_cache_path.exists():
        try:
            loaded = json.loads(nlm_cache_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                nlm_cache = loaded
        except (OSError, json.JSONDecodeError, TypeError):
            nlm_cache = {}

    clusters: dict[str, ClusterStats] = {}
    for slug, cluster in registry.clusters.items():
        cached = nlm_cache.get(slug, {})
        clusters[slug] = ClusterStats(
            slug=slug,
            name=cluster.name,
            zotero_collection_key=cluster.zotero_collection_key or "",
            notebooklm_notebook=cluster.notebooklm_notebook or "",
            notebooklm_notebook_url=cluster.notebooklm_notebook_url
            or cached.get("notebook_url", ""),
        )

    for subdir in cfg.raw.glob("*"):
        if not subdir.is_dir():
            continue
        cluster_stats = clusters.get(subdir.name)
        if cluster_stats is None:
            continue
        latest = ""
        for md_path in subdir.glob("*.md"):
            frontmatter = _read_frontmatter(md_path)
            if not frontmatter:
                continue
            cluster_stats.paper_count += 1
            status_match = re.search(r'^status:\s*"?([^"\n]+)"?', frontmatter, re.MULTILINE)
            status = status_match.group(1).strip() if status_match else "unread"
            cluster_stats.status_breakdown[status] = (
                cluster_stats.status_breakdown.get(status, 0) + 1
            )
            ingested_match = re.search(
                r'^ingested_at:\s*"?([^"\n]+)"?', frontmatter, re.MULTILINE
            )
            if ingested_match:
                ingested_at = ingested_match.group(1).strip()
                if ingested_at > latest:
                    latest = ingested_at
        cluster_stats.latest_ingested_at = latest

    return {
        "vault_root": str(cfg.root),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "total_papers": sum(cluster.paper_count for cluster in clusters.values()),
        "total_clusters": len(clusters),
        "dedup_doi_count": len(dedup.doi_to_hits),
        "dedup_title_count": len(dedup.title_to_hits),
        "clusters": clusters,
        "nlm_cache": nlm_cache,
    }


def render_dashboard_html(state: dict) -> str:
    """Render collected state into a single self-contained HTML page."""
    css = """
    :root {
      color-scheme: dark;
      --bg: #0a0d12;
      --bg-alt: #111722;
      --bg-elev: #182131;
      --fg: #eef3fb;
      --fg-mute: #93a0b5;
      --accent: #6fb1ff;
      --accent-strong: #4e96eb;
      --green: #79d48a;
      --yellow: #e7c85d;
      --red: #f08a8a;
      --border: #223044;
      --shadow: 0 18px 50px rgba(0, 0, 0, 0.28);
    }
    * { box-sizing: border-box; }
    html, body { margin: 0; padding: 0; background:
      radial-gradient(circle at top, rgba(111, 177, 255, 0.15), transparent 35%),
      linear-gradient(180deg, #0a0d12 0%, #0d1118 100%);
      color: var(--fg);
      font-family: "Segoe UI", system-ui, sans-serif;
      font-size: 14px;
      line-height: 1.5;
    }
    a { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }
    code { font-family: "Cascadia Mono", "SFMono-Regular", Consolas, monospace; }
    .wrap { max-width: 1240px; margin: 0 auto; padding: 32px 20px 48px; }
    .hero { display: grid; gap: 16px; padding: 28px; border: 1px solid var(--border);
      border-radius: 20px; background: rgba(17, 23, 34, 0.88); box-shadow: var(--shadow); }
    .hero h1 { margin: 0; font-size: 32px; line-height: 1.1; }
    .hero p { margin: 0; color: var(--fg-mute); }
    .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 16px; margin: 24px 0 32px; }
    .stat { padding: 18px; border: 1px solid var(--border); border-radius: 16px;
      background: rgba(17, 23, 34, 0.9); }
    .stat-num { font-size: 32px; font-weight: 700; color: var(--accent); }
    .stat-label { color: var(--fg-mute); font-size: 12px; text-transform: uppercase;
      letter-spacing: 0.08em; }
    section { margin-top: 32px; }
    h2 { margin: 0 0 14px; font-size: 18px; }
    .panel { overflow: auto; border: 1px solid var(--border); border-radius: 18px;
      background: rgba(17, 23, 34, 0.92); box-shadow: var(--shadow); }
    table { width: 100%; border-collapse: collapse; }
    th, td { padding: 12px 14px; text-align: left; border-bottom: 1px solid var(--border);
      vertical-align: top; }
    th { font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em;
      color: var(--fg-mute); background: rgba(24, 33, 49, 0.9); }
    tr:hover { background: rgba(24, 33, 49, 0.55); }
    .badge { display: inline-block; padding: 3px 8px; margin: 0 6px 6px 0;
      border-radius: 999px; background: var(--bg-elev); color: var(--fg-mute); font-size: 11px; }
    .badge-deep-read { background: rgba(121, 212, 138, 0.16); color: var(--green); }
    .badge-cited { background: rgba(111, 177, 255, 0.18); color: var(--accent); }
    .badge-reading { background: rgba(231, 200, 93, 0.18); color: var(--yellow); }
    .badge-unread { background: rgba(147, 160, 181, 0.15); color: var(--fg-mute); }
    .empty { padding: 28px; text-align: center; color: var(--fg-mute); }
    footer { margin-top: 32px; padding-top: 20px; border-top: 1px solid var(--border);
      color: var(--fg-mute); text-align: center; }
    @media (max-width: 720px) {
      .wrap { padding: 20px 14px 32px; }
      .hero { padding: 22px; }
      .hero h1 { font-size: 26px; }
    }
    """

    rows: list[str] = []
    sorted_clusters = sorted(state["clusters"].values(), key=lambda cluster: (-cluster.paper_count, cluster.name.lower()))
    for cluster in sorted_clusters:
        badges: list[str] = []
        for status in ("deep-read", "cited", "reading", "unread"):
            count = cluster.status_breakdown.get(status, 0)
            if count:
                badges.append(
                    f'<span class="badge badge-{_html_escape(status)}">{_html_escape(status)}: {count}</span>'
                )
        notebooklm = ""
        if cluster.notebooklm_notebook_url:
            notebooklm = (
                f'<a href="{_html_escape(cluster.notebooklm_notebook_url)}" '
                'target="_blank" rel="noreferrer">Open NotebookLM</a>'
            )
        elif cluster.notebooklm_notebook:
            notebooklm = f'<span class="badge">{_html_escape(cluster.notebooklm_notebook)}</span>'
        last_added = cluster.latest_ingested_at[:10] if cluster.latest_ingested_at else "-"
        zotero = _html_escape(cluster.zotero_collection_key) if cluster.zotero_collection_key else '<span class="badge">unbound</span>'
        rows.append(
            f"""
            <tr>
              <td><strong>{_html_escape(cluster.name)}</strong><br><code>{_html_escape(cluster.slug)}</code></td>
              <td>{cluster.paper_count}</td>
              <td>{''.join(badges) or '<span class="badge">empty</span>'}</td>
              <td>{zotero}</td>
              <td>{notebooklm or '<span class="badge">none</span>'}</td>
              <td><code>{_html_escape(last_added)}</code></td>
            </tr>
            """
        )

    if rows:
        cluster_table = (
            "<div class=\"panel\"><table><thead><tr>"
            "<th>Cluster</th><th>Papers</th><th>Reading status</th><th>Zotero</th>"
            "<th>NotebookLM</th><th>Last added</th></tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table></div>"
        )
    else:
        cluster_table = (
            '<div class="panel"><div class="empty">No clusters yet. '
            'Run <code>research-hub clusters new</code></div></div>'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>research-hub dashboard</title>
  <style>{css}</style>
</head>
<body>
  <main class="wrap">
    <header class="hero">
      <div>
        <h1>research-hub</h1>
        <p>Personal vault dashboard generated from local state.</p>
      </div>
      <p>Vault: <code>{_html_escape(state["vault_root"])}</code> | Generated {state["generated_at"]}</p>
    </header>

    <section class="stats" aria-label="Vault statistics">
      <article class="stat"><div class="stat-num">{state["total_papers"]}</div><div class="stat-label">Papers in vault</div></article>
      <article class="stat"><div class="stat-num">{state["total_clusters"]}</div><div class="stat-label">Topic clusters</div></article>
      <article class="stat"><div class="stat-num">{state["dedup_doi_count"]}</div><div class="stat-label">Indexed DOIs</div></article>
      <article class="stat"><div class="stat-num">{state["dedup_title_count"]}</div><div class="stat-label">Indexed titles</div></article>
    </section>

    <section>
      <h2>Clusters</h2>
      {cluster_table}
    </section>

    <footer>Generated by <code>research-hub dashboard</code> | v0.9.0</footer>
  </main>
</body>
</html>"""


def _html_escape(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def generate_dashboard(open_browser: bool = False) -> Path:
    """Generate dashboard HTML and optionally open it in the browser."""
    cfg = get_config()
    state = collect_vault_state(cfg)
    html = render_dashboard_html(state)
    out_path = cfg.research_hub_dir / "dashboard.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    if open_browser:
        webbrowser.open(out_path.as_uri())
    return out_path
