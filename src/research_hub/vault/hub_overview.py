"""Populate cluster hub overview notes and MOC entry points."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from research_hub.security import safe_join


OVERVIEW_FILENAME = "00_overview.md"
PAPERS_BY_YEAR_FILENAME = "01_papers_by_year.md"
PAPERS_HEADING = "Papers in this cluster"
BRIEF_HEADING = "NotebookLM brief"
MOC_HEADING = "Related MOCs"
PAPER_PAGINATION_THRESHOLD = 30
RECENT_PAPERS_LIMIT = 12
FIT_SCORE_PAPERS_LIMIT = 20
REBUILD_DEBOUNCE_THRESHOLD = 10

_H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)
_SCAFFOLD_MARKERS = (
    # Mojibake from a legacy cp950 ↔ UTF-8 round-trip — kept so older
    # vaults whose 00_overview.md still has the corrupted bytes are
    # still recognised as scaffold and refreshed cleanly.
    "銝?啣?亥店",
    "?其??亥店撖思?",
    # Real Chinese openings written by topic.py for fresh clusters
    # (TL;DR line ~29 / line ~101 and 核心問題 line ~35 / line ~107).
    # Mirror cluster_overview.py:_CHINESE_TEMPLATE_MARKER for the TL;DR side.
    "一到兩句話",
    "用一句話寫下",
    "TODO",
    "[TODO]",
)
_MOJIBAKE_MARKERS = (
    "銝",
    "蝭",
    "敹",
    "隢",
    "撱",
    "璁",
    "閰",
    "憿",
    "蝺",
    "箔",
    "摮",
    "瘨",
    "閬",
    "謕",
)


def populate_overview(
    *,
    cluster_slug: str,
    vault_root: Path,
    brief_md_path: Path | None = None,
    moc_links: list[str] | None = None,
    force_rebuild: bool = False,
) -> Path:
    """Idempotently populate ``hub/<cluster_slug>/00_overview.md``."""

    root = Path(vault_root)
    overview_path = _overview_path(root, cluster_slug)
    overview_path.parent.mkdir(parents=True, exist_ok=True)
    current_paper_count = len(_paper_note_paths(root, cluster_slug))

    if _should_debounce_overview_rebuild(
        root,
        cluster_slug,
        current_paper_count=current_paper_count,
        overview_path=overview_path,
        force_rebuild=force_rebuild,
    ):
        return overview_path

    if overview_path.exists():
        existing = overview_path.read_text(encoding="utf-8", errors="ignore")
        preamble, section_text = _split_preamble(existing)
    else:
        preamble = _default_preamble(cluster_slug)
        section_text = ""

    existing_sections = _parse_overview_sections(section_text)
    scaffold_keys = {
        heading
        for heading, body in existing_sections.items()
        if _is_scaffold_body(body)
    }

    tldr_body = existing_sections.get("TL;DR", "")
    if "TL;DR" not in existing_sections or "TL;DR" in scaffold_keys:
        tldr_body = _render_tldr(_overview_tldr(root, cluster_slug, brief_md_path))

    paper_body = _render_papers_section(root, cluster_slug)
    brief_body = _generated_brief_body(brief_md_path)
    if brief_body is None:
        brief_body = _keep_existing_body(existing_sections, scaffold_keys, BRIEF_HEADING)
    moc_body = _generated_moc_body(moc_links)
    if moc_body is None:
        moc_body = _keep_existing_body(existing_sections, scaffold_keys, MOC_HEADING)

    preserved: dict[str, str] = {}
    for heading, body in existing_sections.items():
        if heading in scaffold_keys:
            continue
        if heading in {"TL;DR", PAPERS_HEADING, BRIEF_HEADING, MOC_HEADING}:
            continue
        preserved[heading] = body

    generated: dict[str, str] = {
        "TL;DR": tldr_body,
        PAPERS_HEADING: paper_body,
    }
    if brief_body:
        generated[BRIEF_HEADING] = brief_body
    if moc_body:
        generated[MOC_HEADING] = moc_body

    sections = _merge_sections(existing_sections, preserved, generated)
    rendered_sections = _render_overview(sections, scaffold_keys=set())
    new_text = _join_preamble_and_sections(preamble, rendered_sections)
    if not overview_path.exists() or overview_path.read_text(encoding="utf-8", errors="ignore") != new_text:
        overview_path.write_text(new_text, encoding="utf-8")
    _write_rebuild_marker(root, cluster_slug, current_paper_count, since_last_rebuild=0)
    return overview_path


def ensure_moc(vault_root: Path, name: str, *, description: str = "") -> Path:
    """Create ``hub/_moc/<name>.md`` if missing and return its path."""

    root = Path(vault_root)
    moc_dir = safe_join(root, "hub", "_moc")
    moc_dir.mkdir(parents=True, exist_ok=True)
    path = safe_join(moc_dir, f"{name}.md")
    if path.exists():
        return path

    topic_slug = _topic_slug(name)
    frontmatter = "\n".join(
        [
            "---",
            "type: moc",
            f"name: {name}",
            f'tags: ["topic:{topic_slug}", "type:moc"]',
            "---",
            "",
        ]
    )
    body = (
        f"# {name}\n\n"
        f"{description.strip()}\n\n"
        "## Clusters tagged with this MOC\n\n"
        "(populated by sync)\n"
    )
    path.write_text(frontmatter + body, encoding="utf-8")
    return path


HOME_FILENAME = "_HOME.md"
_HOME_SECTION_RE = re.compile(
    r"(##[ \t]+)(Start here|Clusters|Reading queue|Recent NotebookLM briefs|Dashboard)([ \t]*\n)(.*?)(?=^##[ \t]|\Z)",
    re.MULTILINE | re.DOTALL,
)


def populate_home(cfg) -> Path:
    """v0.88 #7: write/refresh `<vault>/_HOME.md` as the canonical
    Obsidian landing page.

    Generated sections (replaced on each call, idempotent):
    - ## Clusters
    - ## Reading queue (top 5 unread, year DESC)
    - ## Recent NotebookLM briefs (latest 3 brief mirrors)
    - ## Dashboard (file:// link to .research_hub/dashboard.html)

    Frontmatter is written ONCE; if the file exists, frontmatter is
    preserved verbatim. User-added sections (anything not in the
    generated-headings list above) are preserved.
    """
    from research_hub.clusters import ClusterRegistry

    vault_root = Path(cfg.root)
    home_path = vault_root / HOME_FILENAME

    registry = ClusterRegistry(cfg.clusters_file)
    clusters = list(registry.list())

    # F3b: build cluster entries, grouping by the group field when any group is set
    def _cluster_entry(cluster) -> str:
        _slug = (cluster.slug or "").strip()
        _name = (cluster.name or _slug).strip()
        _paper_count = _count_papers(vault_root, _slug)
        _cluster_queries = [str(getattr(cluster, "first_query", "") or "")]
        _moc_links = derive_moc_links(_slug, cluster_queries=_cluster_queries)
        _moc_tail = ""
        if _moc_links:
            _moc_wikilinks = " / ".join(f"[[{m}]]" for m in _moc_links)
            _moc_tail = f" — {_moc_wikilinks}"
        return f"- [[{_slug}/00_overview|{_name}]] ({_paper_count} papers){_moc_tail}"

    active_clusters = [
        c for c in clusters
        if (c.slug or "").strip()
        and getattr(c, "status", "active") != "archived"
    ]
    has_groups = any(getattr(c, "group", "") for c in active_clusters)
    if has_groups:
        _grouped: dict[str, list] = {}
        for cluster in active_clusters:
            g = (getattr(cluster, "group", "") or "").strip()
            _grouped.setdefault(g, []).append(cluster)
        # Named groups alphabetically, ungrouped last
        _sorted_groups = sorted(g for g in _grouped if g)
        if "" in _grouped:
            _sorted_groups.append("")
        cluster_lines: list[str] = []
        for g in _sorted_groups:
            label = g if g else "Other"
            cluster_lines.append(f"### {label}")
            cluster_lines.extend(_cluster_entry(c) for c in _grouped[g])
            cluster_lines.append("")
        clusters_body = "\n".join(cluster_lines).strip() or "(no clusters yet)"
    else:
        cluster_lines = [_cluster_entry(c) for c in active_clusters]
        clusters_body = "\n".join(cluster_lines) if cluster_lines else "(no clusters yet)"

    reading_queue_body = _render_home_reading_queue(vault_root, clusters, limit=5)
    briefs_body = _render_home_recent_briefs(vault_root, clusters, limit=3)
    # v0.89.1: prefer the live HTTP dashboard (works on iOS Obsidian
    # too if the user is on the same network) and the in-vault markdown
    # mirror (always works, mobile-friendly). The previous file:///C:/...
    # link only worked on the same desktop where serve --dashboard had
    # written the static HTML, and broke entirely on iOS — W3 audit
    # finding from the v0.88.9 pass.
    dashboard_body = (
        "- [Dashboard (live)](http://127.0.0.1:8765/) "
        "(start with `research-hub serve --dashboard`)\n"
        "- [Markdown summary](.research_hub/dashboard-summary.md) "
        "(Obsidian-internal, works on iOS / mobile)"
    )

    # Phase B / v1.1 (W3 discoverability): a ≤3-tap "Start here"
    # wayfinding block at the very top of _HOME.md. Prepend-only —
    # existing sections are neither removed nor reordered.
    start_here_body = (
        "1. **Pick a cluster** → see [[#Clusters]] below.\n"
        "2. **What to read next** → [[#Reading queue]].\n"
        "3. **Full dashboard** → [[#Dashboard]] "
        "(live HTTP, or the iOS-friendly markdown mirror).\n"
        "\n"
        "_New here?_ `research-hub init --sample` for a demo vault, "
        "or `research-hub serve --dashboard` then press "
        "<kbd>⌘/Ctrl</kbd>+<kbd>K</kbd> for the command palette."
    )

    sections = {
        "Start here": start_here_body,
        "Clusters": clusters_body,
        "Reading queue": reading_queue_body,
        "Recent NotebookLM briefs": briefs_body,
        "Dashboard": dashboard_body,
    }

    if home_path.exists():
        text = home_path.read_text(encoding="utf-8")
        new_text = _refresh_home_sections(text, sections)
    else:
        new_text = _build_home_from_scratch(sections)

    home_path.write_text(new_text, encoding="utf-8")
    return home_path


def _count_papers(vault_root: Path, cluster_slug: str) -> int:
    raw = vault_root / "raw" / cluster_slug
    if not raw.exists():
        return 0
    return sum(
        1 for p in raw.glob("*.md")
        if p.name not in {"00_overview.md", "index.md"}
    )


def _render_home_reading_queue(vault_root: Path, clusters, limit: int) -> str:
    candidates: list[tuple[int, str, str, str]] = []  # (-year, slug, stem, title-or-stem)
    for cluster in clusters:
        slug = (cluster.slug or "").strip()
        if not slug:
            continue
        raw = vault_root / "raw" / slug
        if not raw.exists():
            continue
        for note_path in raw.glob("*.md"):
            if note_path.name in {"00_overview.md", "index.md"}:
                continue
            meta = _read_frontmatter(note_path)
            status = str(meta.get("status", "") or "").strip().lower()
            if status != "unread":
                continue
            year = _year_value(meta.get("year"))
            stem = note_path.stem
            title = str(meta.get("title", "") or stem)
            candidates.append((-year, slug, stem, title))
    if not candidates:
        return "(no unread papers — all clusters caught up)"
    candidates.sort()
    lines = []
    for _, slug, stem, title in candidates[:limit]:
        title_trim = title.strip()
        if len(title_trim) > 80:
            title_trim = title_trim[:77].rstrip() + "..."
        lines.append(f"- [[{stem}|{title_trim}]] ({slug})")
    return "\n".join(lines)


def _render_home_recent_briefs(vault_root: Path, clusters, limit: int) -> str:
    found: list[tuple[str, str, Path]] = []  # (timestamp-from-name, slug, path)
    for cluster in clusters:
        slug = (cluster.slug or "").strip()
        if not slug:
            continue
        brief = latest_brief_md(vault_root, slug)
        if brief is None:
            continue
        # filename pattern: notebooklm-brief-<UTC-timestamp>.md
        ts = brief.stem.removeprefix("notebooklm-brief-")
        found.append((ts, slug, brief))
    if not found:
        return "(no NotebookLM briefs downloaded yet)"
    found.sort(reverse=True)
    lines = []
    for ts, slug, brief in found[:limit]:
        lines.append(f"- [[{brief.stem}]] ({slug} — generated {ts[:8]})")
    return "\n".join(lines)


def _refresh_home_sections(text: str, sections: dict[str, str]) -> str:
    """Idempotently replace the 4 generated sections in an existing _HOME.md."""
    def replace(match: re.Match[str]) -> str:
        heading_name = match.group(2)
        new_body = sections.get(heading_name)
        if new_body is None:
            return match.group(0)
        return f"{match.group(1)}{heading_name}{match.group(3)}\n{new_body}\n\n"

    # Phase B / v1.1: existing _HOME.md files predate the "Start
    # here" block — the regex can only REPLACE a section that's
    # already present, so inject it once (prepend, right after the
    # `# Research Hub` title). Subsequent passes refresh it in place
    # via the regex (idempotent). Prepend-only: no existing section
    # is moved or dropped.
    if "## Start here" not in text and "Start here" in sections:
        block = f"## Start here\n{sections['Start here']}\n\n"
        m = re.search(r"^#[ \t]+.*\n", text, re.MULTILINE)
        if m:
            text = text[: m.end()] + "\n" + block + text[m.end():]
        else:
            # No `# ` H1 (hand-edited vault). NEVER prepend above a
            # leading `---\n…\n---\n` frontmatter block — that would
            # corrupt Obsidian YAML parsing. Insert after it; only
            # absolute-top when there is no frontmatter at all.
            fm = re.match(r"^---\n.*?\n---\n", text, re.DOTALL)
            if fm:
                text = text[: fm.end()] + "\n" + block + text[fm.end():]
            else:
                text = block + text

    new_text = _HOME_SECTION_RE.sub(replace, text)
    # Normalize trailing newlines so subsequent passes don't drift.
    return new_text.rstrip("\n") + "\n"


def _build_home_from_scratch(sections: dict[str, str]) -> str:
    body_parts = ["# Research Hub", ""]
    for heading in ("Start here", "Clusters", "Reading queue", "Recent NotebookLM briefs", "Dashboard"):
        body_parts.append(f"## {heading}")
        body_parts.append("")
        body_parts.append(sections[heading])
        body_parts.append("")
    return (
        "---\n"
        "type: home\n"
        'aliases: ["Home", "🏠"]\n'
        "---\n\n"
        + "\n".join(body_parts).rstrip()
        + "\n"
    )


_MOC_CLUSTERS_HEADING = "Clusters tagged with this MOC"
# v0.88 #4: `[ \t]*\n` (not `\s*\n`) so the regex doesn't eat blank lines AFTER
# the heading. With `\s*\n`, each populate_moc() run would consume one more
# trailing blank into group(1) and then re-emit it, drifting non-idempotent.
_MOC_CLUSTERS_SECTION_RE = re.compile(
    rf"(##[ \t]+{re.escape(_MOC_CLUSTERS_HEADING)}[ \t]*\n)(.*?)(?=^##[ \t]|\Z)",
    re.MULTILINE | re.DOTALL,
)


def populate_moc(
    vault_root: Path,
    name: str,
    cluster_slugs: list[str],
) -> Path:
    """v0.88 #4: write the actual list of clusters into a MOC note's body.

    `ensure_moc` only creates the file with a `(populated by sync)`
    placeholder. This function fills that section with the real
    `[[<cluster>/00_overview]]` wikilinks so the MOC becomes a navigable
    hub-of-hubs instead of an orphan stub.

    Idempotent: re-running with the same cluster_slugs produces
    byte-identical output. The MOC frontmatter and any other body
    sections the user may have written are preserved.
    """
    root = Path(vault_root)
    path = safe_join(root, "hub", "_moc", f"{name}.md")
    if not path.exists():
        ensure_moc(root, name)

    text = path.read_text(encoding="utf-8")
    # Build the new section body.
    if cluster_slugs:
        bullets = "\n".join(
            f"- [[{slug}/00_overview|{slug}]]"
            for slug in sorted(set(cluster_slugs))
        )
        new_body = bullets + "\n"
    else:
        new_body = "(no clusters reference this MOC yet)\n"

    if _MOC_CLUSTERS_SECTION_RE.search(text):
        updated = _MOC_CLUSTERS_SECTION_RE.sub(
            lambda m: m.group(1) + "\n" + new_body + "\n",
            text,
            count=1,
        )
    else:
        # The heading is missing — append it at the end.
        sep = "" if text.endswith("\n") else "\n"
        updated = f"{text}{sep}\n## {_MOC_CLUSTERS_HEADING}\n\n{new_body}\n"

    if updated != text:
        path.write_text(updated, encoding="utf-8")
    return path


def populate_all_mocs(cfg) -> list[tuple[str, Path]]:
    """v0.88 #4: for every MOC referenced by any cluster, write its
    Clusters list. Mirrors `populate_all_overviews` over the MOC plane.

    Returns list of (moc_name, path) tuples for each MOC populated.
    """
    from research_hub.clusters import ClusterRegistry

    registry = ClusterRegistry(cfg.clusters_file)
    vault_root = Path(cfg.root)
    moc_to_clusters: dict[str, list[str]] = {}
    for cluster in registry.list():
        slug = (cluster.slug or "").strip()
        if not slug:
            continue
        # Skip archived clusters — do not include them in MOC pages.
        if getattr(cluster, "status", "active") == "archived":
            continue
        moc_links = derive_moc_links(
            slug,
            cluster_queries=[str(getattr(cluster, "first_query", "") or "")],
            moc_links=list(getattr(cluster, "moc_links", []) or []),
        )
        for moc_name in moc_links:
            moc_to_clusters.setdefault(moc_name, []).append(slug)

    written: list[tuple[str, Path]] = []
    for moc_name, slugs in moc_to_clusters.items():
        path = populate_moc(vault_root, moc_name, slugs)
        written.append((moc_name, path))
    return written


def derive_moc_links(
    cluster_slug: str,
    cluster_queries: list[str] | None = None,
    moc_links: list[str] | None = None,
) -> list[str]:
    """Return v0.87 default MOC names for a cluster."""

    links: list[str] = []
    for name in moc_links or []:
        _append_unique(links, str(name).strip())
    text_parts = [cluster_slug, *(cluster_queries or [])]
    haystack = " ".join(str(part) for part in text_parts if part).lower()
    if "llm" in haystack or "large language model" in haystack or "agent" in haystack:
        _append_unique(links, "LLM-Agents")
    # v0.88.5: broaden water-resources heuristic so flood / hydrology /
    # drainage / river / drought / rainfall clusters also link to the
    # Water-Resources MOC. Without this, a "ml-flood-forecasting" cluster
    # got no MOC links and ended up isolated in the graph view.
    water_keywords = (
        "water", "flood", "hydro", "rainfall", "river", "drainage",
        "drought", "sociohydrology", "stormwater", "reservoir",
    )
    if any(kw in haystack for kw in water_keywords):
        _append_unique(links, "Water-Resources")
    return links


def latest_brief_md(vault_root: Path, cluster_slug: str) -> Path | None:
    """Return the most-recent NotebookLM brief markdown mirror for a cluster.

    Mirrors are written by `notebooklm download --type brief` to
    `hub/<slug>/notebooklm-brief-<UTC-timestamp>.md`. Sorted by
    filename so the lexicographic order matches chronological order.
    Returns None when no brief mirror exists yet.
    """
    hub_dir = vault_root / "hub" / cluster_slug
    if not hub_dir.exists():
        return None
    candidates = sorted(hub_dir.glob("notebooklm-brief-*.md"))
    return candidates[-1] if candidates else None


def populate_all_overviews(
    cfg,
    *,
    cluster_slug_filter: str | None = None,
    force_rebuild: bool = False,
) -> list[tuple[str, Path]]:
    """Re-run populate_overview + ensure_moc for every cluster in the registry.

    Use cases (v0.87.1 §5):
    - Backfill clusters that were ingested BEFORE v0.87's
      post-ingest hub-overview hook landed.
    - Bulk refresh after a template change to the overview scaffold.
    - One-shot CLI: `research-hub hub rebuild-overviews`.

    For each cluster: look up the latest brief mirror (if any), derive
    MOC links from slug + cluster.first_query, ensure_moc them, then
    populate_overview. Returns list of (slug, overview_path) tuples.

    Errors per cluster are caught and logged; one bad cluster does
    not stop the rest.
    """
    from research_hub.clusters import ClusterRegistry

    registry = ClusterRegistry(cfg.clusters_file)
    vault_root = Path(cfg.root)
    written: list[tuple[str, Path]] = []
    for cluster in registry.list():
        slug = (cluster.slug or "").strip()
        if not slug:
            continue
        if cluster_slug_filter and slug != cluster_slug_filter:
            continue
        try:
            cluster_queries = [str(getattr(cluster, "first_query", "") or "")]
            moc_links = derive_moc_links(
                slug,
                cluster_queries=cluster_queries,
                moc_links=list(getattr(cluster, "moc_links", []) or []),
            )
            for name in moc_links:
                ensure_moc(vault_root, name)
            brief_md = latest_brief_md(vault_root, slug)
            overview_path = populate_overview(
                cluster_slug=slug,
                vault_root=vault_root,
                brief_md_path=brief_md,
                moc_links=moc_links,
                force_rebuild=force_rebuild,
            )
            written.append((slug, overview_path))
        except Exception as exc:  # noqa: BLE001 — surface per-cluster failures, continue with rest
            written.append((slug, Path(f"<error: {exc}>")))
    # v0.88 #4: now that every cluster's overview is up-to-date, refresh
    # the MOC bodies so each MOC lists its member clusters.
    # v0.90.0 G1#3 fix: log MOC/_HOME failures to stderr instead of silent
    # pass — pre-fix swallow left stale MOCs + stale _HOME.md after every
    # rebuild on partial failure with zero signal to the caller. Still
    # non-fatal (per-cluster overview writes succeeded), just visible.
    try:
        populate_all_mocs(cfg)
    except Exception as exc:  # noqa: BLE001
        print(
            f"  [vault] WARN populate_all_mocs failed; MOC pages may be stale: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
    # v0.88 #7: refresh vault-root _HOME.md as the canonical landing page.
    try:
        populate_home(cfg)
    except Exception as exc:  # noqa: BLE001
        print(
            f"  [vault] WARN populate_home failed; _HOME.md may be stale: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
    return written


def _parse_overview_sections(md: str) -> dict[str, str]:
    """Parse level-2 overview sections into an ordered mapping."""

    sections: dict[str, str] = {}
    matches = list(_H2_RE.finditer(md))
    for index, match in enumerate(matches):
        heading = match.group(1).strip().rstrip("#").strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(md)
        sections[heading] = md[start:end].strip("\n")
    return sections


def _render_overview(sections: dict[str, str], *, scaffold_keys: set[str]) -> str:
    """Render section mapping back to markdown, omitting scaffold keys."""

    rendered: list[str] = []
    for heading, body in sections.items():
        if heading in scaffold_keys:
            continue
        body_text = body.rstrip()
        if not body_text:
            continue
        rendered.append(f"## {heading}\n\n{body_text}")
    return "\n\n".join(rendered).rstrip() + ("\n" if rendered else "")


def _paper_bullet(note_path: Path) -> str:
    """Build the overview bullet wikilink for a paper note."""

    meta = _read_frontmatter(note_path)
    title = _single_line(meta.get("title") or note_path.stem)
    return f"- [[{note_path.stem}]]: *{title}*"


def _paper_alias_bullet(note_path: Path) -> str:
    meta = _read_frontmatter(note_path)
    title = _single_line(meta.get("title") or note_path.stem)
    return f"- [[{note_path.stem}|{title}]]"


def _overview_path(vault_root: Path, cluster_slug: str) -> Path:
    return safe_join(vault_root, "hub", cluster_slug, OVERVIEW_FILENAME)


def _raw_cluster_dir(vault_root: Path, cluster_slug: str) -> Path:
    return safe_join(vault_root, "raw", cluster_slug)


def _papers_by_year_path(vault_root: Path, cluster_slug: str) -> Path:
    return safe_join(vault_root, "hub", cluster_slug, PAPERS_BY_YEAR_FILENAME)


def _rebuild_marker_path(vault_root: Path, cluster_slug: str) -> Path:
    return safe_join(
        vault_root,
        ".research_hub",
        "clusters",
        f"{cluster_slug}.rebuild_marker.json",
    )


def _paper_note_paths(vault_root: Path, cluster_slug: str) -> list[Path]:
    raw_dir = _raw_cluster_dir(vault_root, cluster_slug)
    if not raw_dir.exists():
        return []
    return [
        path
        for path in raw_dir.glob("*.md")
        if path.name not in {OVERVIEW_FILENAME, "index.md"}
    ]


def _should_debounce_overview_rebuild(
    vault_root: Path,
    cluster_slug: str,
    *,
    current_paper_count: int,
    overview_path: Path,
    force_rebuild: bool,
) -> bool:
    if force_rebuild:
        return False
    if not overview_path.exists():
        return False
    sidecar_missing = not _papers_by_year_path(vault_root, cluster_slug).exists()
    if current_paper_count > PAPER_PAGINATION_THRESHOLD and sidecar_missing:
        return False

    marker_path = _rebuild_marker_path(vault_root, cluster_slug)
    marker = _read_rebuild_marker(marker_path)
    if not marker:
        return False

    last_count = _nonnegative_int(
        marker.get("last_rebuild_paper_count"),
        current_paper_count,
    )
    if current_paper_count < last_count:
        return False

    marker_since = _nonnegative_int(marker.get("since_last_rebuild"), 0)
    paper_delta = current_paper_count - last_count
    since_last_rebuild = max(marker_since, paper_delta)
    if since_last_rebuild >= REBUILD_DEBOUNCE_THRESHOLD:
        return False

    if since_last_rebuild != marker_since:
        _write_rebuild_marker(
            vault_root,
            cluster_slug,
            last_count,
            since_last_rebuild=since_last_rebuild,
            last_rebuild_at=str(marker.get("last_rebuild_at", "") or _utc_now_iso()),
        )
    return True


def _read_rebuild_marker(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_rebuild_marker(
    vault_root: Path,
    cluster_slug: str,
    last_rebuild_paper_count: int,
    *,
    since_last_rebuild: int,
    last_rebuild_at: str | None = None,
) -> Path:
    path = _rebuild_marker_path(vault_root, cluster_slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_rebuild_at": last_rebuild_at or _utc_now_iso(),
        "last_rebuild_paper_count": int(last_rebuild_paper_count),
        "since_last_rebuild": int(since_last_rebuild),
    }
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def _split_preamble(md: str) -> tuple[str, str]:
    match = _H2_RE.search(md)
    if not match:
        return md.rstrip(), ""
    return md[: match.start()].rstrip(), md[match.start() :]


def _join_preamble_and_sections(preamble: str, rendered_sections: str) -> str:
    parts = [part.rstrip() for part in (preamble, rendered_sections) if part.strip()]
    return "\n\n".join(parts).rstrip() + "\n"


def _default_preamble(cluster_slug: str) -> str:
    title = cluster_slug.replace("-", " ").strip().title() or cluster_slug
    return "\n".join(
        [
            "---",
            "type: topic-overview",
            f"cluster: {cluster_slug}",
            f"title: {title}",
            "status: draft",
            "---",
            "",
            f"# {title}",
        ]
    )


def _merge_sections(
    existing_sections: dict[str, str],
    preserved: dict[str, str],
    generated: dict[str, str],
) -> dict[str, str]:
    final: dict[str, str] = {}
    inserted_generated = False

    def insert_generated() -> None:
        nonlocal inserted_generated
        if inserted_generated:
            return
        for heading, body in generated.items():
            final[heading] = body
        inserted_generated = True

    if "TL;DR" not in existing_sections:
        insert_generated()
    for heading in existing_sections:
        if heading == "TL;DR":
            insert_generated()
            continue
        if heading in preserved:
            final[heading] = preserved[heading]
    insert_generated()
    return final


def _keep_existing_body(
    existing_sections: dict[str, str],
    scaffold_keys: set[str],
    heading: str,
) -> str | None:
    if heading in existing_sections and heading not in scaffold_keys:
        body = existing_sections[heading].strip()
        return body or None
    return None


def _render_tldr(text: str) -> str:
    clean = text.strip() or "No cluster summary available yet."
    quote_lines = [f"> {line}" if line else ">" for line in clean.splitlines()]
    return "\n".join(["> [!abstract]", *quote_lines, "^tldr"])


def _overview_tldr(vault_root: Path, cluster_slug: str, brief_md_path: Path | None) -> str:
    if brief_md_path is not None and Path(brief_md_path).exists():
        summary = _brief_summary(Path(brief_md_path))
        if summary:
            return summary[:200]
    query = _cluster_query_fallback(vault_root, cluster_slug)
    return query or cluster_slug.replace("-", " ")


def _brief_summary(brief_md_path: Path) -> str:
    text = brief_md_path.read_text(encoding="utf-8", errors="ignore")
    body = _strip_frontmatter(text)
    match = re.search(
        r"^#{1,3}\s+(Executive Summary|Summary|TL;DR)\s*$",
        body,
        re.IGNORECASE | re.MULTILINE,
    )
    if match:
        next_heading = re.search(r"^#{1,3}\s+", body[match.end() :], re.MULTILINE)
        end = match.end() + next_heading.start() if next_heading else len(body)
        candidate = body[match.end() : end]
        summary = _plain_text(candidate)
        if summary:
            return summary
    return _plain_text(body)


def _strip_frontmatter(text: str) -> str:
    return _FRONTMATTER_RE.sub("", text, count=1).lstrip()


def _plain_text(markdown: str) -> str:
    lines: list[str] = []
    in_fence = False
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not line:
            continue
        line = re.sub(r"^#{1,6}\s+", "", line)
        line = re.sub(r"^[-*+]\s+", "", line)
        line = re.sub(r"^>\s?", "", line)
        line = re.sub(r"\*\*(.*?)\*\*", r"\1", line)
        line = re.sub(r"\*(.*?)\*", r"\1", line)
        lines.append(line)
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def _cluster_query_fallback(vault_root: Path, cluster_slug: str) -> str:
    json_path = vault_root / ".research_hub" / "clusters" / f"{cluster_slug}.json"
    if json_path.exists():
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        for key in ("cluster_queries", "queries"):
            values = data.get(key)
            if isinstance(values, list) and values:
                return str(values[0]).strip()
        for key in ("first_query", "query", "name", "description"):
            value = str(data.get(key, "") or "").strip()
            if value:
                return value

    yaml_path = vault_root / ".research_hub" / "clusters.yaml"
    if yaml_path.exists():
        yaml_value = _cluster_query_from_yaml(yaml_path, cluster_slug)
        if yaml_value:
            return yaml_value
    return ""


def _cluster_query_from_yaml(path: Path, cluster_slug: str) -> str:
    try:
        import yaml

        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        cluster = (payload.get("clusters") or {}).get(cluster_slug) or {}
        for key in ("cluster_queries", "queries"):
            values = cluster.get(key)
            if isinstance(values, list) and values:
                return str(values[0]).strip()
        return str(cluster.get("first_query") or cluster.get("name") or "").strip()
    except Exception:
        text = path.read_text(encoding="utf-8", errors="ignore")
        pattern = re.compile(
            rf"^\s{{2}}{re.escape(cluster_slug)}:\s*\n(?P<body>(?:^\s{{4}}.*\n?)*)",
            re.MULTILINE,
        )
        match = pattern.search(text)
        if not match:
            return ""
        first_query = re.search(r"^\s{4}first_query:\s*(.+?)\s*$", match.group("body"), re.MULTILINE)
        return first_query.group(1).strip().strip('"').strip("'") if first_query else ""


_AUTO_CALLOUT_PREFIX = (
    "> [!info] Auto-generated by `populate_overview`. Edits here will be overwritten"
    " on the next `vault rebuild-overviews` run — write hand-curated content under"
    " the user sections (TL;DR, 核心問題, 必讀論文) instead.\n\n"
)


def _wrap_auto_section(body: str) -> str:
    """v0.88 #8: prepend an Obsidian callout to every auto-generated section
    body so readers visually distinguish them from user-owned sections.

    The callout text is idempotent — if the body already starts with the
    callout, no second copy is prepended."""
    if not body:
        return body
    if body.lstrip().startswith("> [!info] Auto-generated by `populate_overview`"):
        return body
    return _AUTO_CALLOUT_PREFIX + body


def _render_papers_section(vault_root: Path, cluster_slug: str) -> str:
    notes = _paper_note_paths(vault_root, cluster_slug)
    if not notes:
        return _wrap_auto_section("(no papers found)")
    notes.sort(key=_paper_sort_key)
    if len(notes) > PAPER_PAGINATION_THRESHOLD:
        _render_papers_by_year_sidecar(vault_root, cluster_slug)
        recent = notes[:RECENT_PAPERS_LIMIT]
        fit_score_ranked = sorted(notes, key=_fit_score_sort_key)[
            :FIT_SCORE_PAPERS_LIMIT
        ]
        full_list = "\n".join(f"> {_paper_bullet(path)}" for path in notes)
        body = "\n\n".join(
            [
                f"### Recent (top {RECENT_PAPERS_LIMIT})\n\n"
                + "\n".join(_paper_bullet(path) for path in recent),
                f"### Most-cited (top {FIT_SCORE_PAPERS_LIMIT} by fit score)\n\n"
                + "\n".join(_paper_bullet(path) for path in fit_score_ranked),
                f"Full list by year: [[{PAPERS_BY_YEAR_FILENAME[:-3]}|Papers by year]]",
                f"> [!details]- Full list ({len(notes)} papers)\n{full_list}",
            ]
        )
        return _wrap_auto_section(body)
    bullets = "\n".join(_paper_bullet(path) for path in notes)
    return _wrap_auto_section(bullets)


def _render_papers_by_year_sidecar(vault_root: Path, cluster_slug: str) -> Path:
    notes = _paper_note_paths(vault_root, cluster_slug)
    notes.sort(key=_paper_sort_key)
    path = _papers_by_year_path(vault_root, cluster_slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    generated_at = _existing_generated_at(path) or _utc_now_iso()

    grouped: dict[int, list[Path]] = {}
    for note_path in notes:
        year = _year_value(_read_frontmatter(note_path).get("year"))
        grouped.setdefault(year, []).append(note_path)

    parts = [
        "---",
        "type: papers-by-year",
        f"cluster: {cluster_slug}",
        f"generated_at: {generated_at}",
        f"total_papers: {len(notes)}",
        "---",
        "",
        f"# Papers by year - {cluster_slug}",
        "",
        "> [!info] Auto-generated. Edits will be overwritten.",
        "",
    ]
    for year in sorted(grouped, reverse=True):
        year_label = str(year) if year else "Unknown"
        year_notes = grouped[year]
        parts.append(f"## {year_label} ({len(year_notes)} papers)")
        parts.append("")
        parts.extend(_paper_alias_bullet(note_path) for note_path in year_notes)
        parts.append("")

    text = "\n".join(parts).rstrip() + "\n"
    if not path.exists() or path.read_text(encoding="utf-8", errors="ignore") != text:
        path.write_text(text, encoding="utf-8")
    return path


def _paper_sort_key(note_path: Path) -> tuple[int, float, str, str]:
    meta = _read_frontmatter(note_path)
    year = _year_value(meta.get("year"))
    ingested_at = _timestamp_value(meta.get("ingested_at"))
    author = _first_author(meta.get("authors"))
    return (-year, -ingested_at, author.lower(), note_path.stem)


def _fit_score_sort_key(note_path: Path) -> tuple[float, tuple[int, float, str, str]]:
    meta = _read_frontmatter(note_path)
    return (-_score_value(meta), _paper_sort_key(note_path))


def _generated_brief_body(brief_md_path: Path | None) -> str | None:
    if brief_md_path is None or not Path(brief_md_path).exists():
        return None
    return _wrap_auto_section(f"- [[{Path(brief_md_path).stem}]]")


def _generated_moc_body(moc_links: list[str] | None) -> str | None:
    links = [name.strip() for name in (moc_links or []) if name and name.strip()]
    if not links:
        return None
    unique = list(dict.fromkeys(links))
    body = "\n".join(f"- [[{name}]]" for name in unique)
    return _wrap_auto_section(body)


def _read_frontmatter(note_path: Path) -> dict[str, Any]:
    try:
        text = note_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {}
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}
    return _parse_simple_yaml(match.group(1))


def _parse_simple_yaml(frontmatter: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for raw_line in frontmatter.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        data[key.strip()] = _parse_scalar(value.strip())
    return data


def _parse_scalar(value: str) -> Any:
    if value in {"", "null", "Null", "NULL", "~"}:
        return ""
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip('"').strip("'") for item in inner.split(",")]
    return value.strip().strip('"').strip("'")


def _existing_generated_at(path: Path) -> str:
    if not path.exists():
        return ""
    value = _read_frontmatter(path).get("generated_at")
    return str(value or "").strip()


def _year_value(value: Any) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


def _nonnegative_int(value: Any, default: int) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def _score_value(meta: dict[str, Any]) -> float:
    for key in ("fit_score", "score", "relevance_score"):
        value = meta.get(key)
        if value is None:
            continue
        try:
            return float(str(value).strip())
        except (TypeError, ValueError):
            continue
    return 0.0


def _timestamp_value(value: Any) -> float:
    raw = str(value or "").strip()
    if not raw:
        return 0.0
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).timestamp()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _first_author(value: Any) -> str:
    if isinstance(value, list):
        raw = str(value[0]) if value else ""
    else:
        raw = str(value or "")
    first = raw.split(";")[0].strip()
    return first.split(",")[0].strip() or first


def _is_scaffold_body(body: str) -> bool:
    text = body.strip()
    if not text:
        return True
    upper = text.upper()
    if any(marker.upper() in upper for marker in _SCAFFOLD_MARKERS):
        return True
    if any(marker in text for marker in _MOJIBAKE_MARKERS):
        return True
    meaningful = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("^"):
            continue
        normalized = re.sub(r"[\s|\-:*>#`_\[\]().!]+", "", stripped)
        if normalized:
            meaningful.append(normalized)
    return not meaningful


def _single_line(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _topic_slug(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return normalized or "moc"


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)
