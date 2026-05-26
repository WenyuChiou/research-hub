"""v0.88 #5 — backfill `## Hub` section into existing paper notes.

V4 audit (Agent 4 post-v0.87) finding: every paper note has 11
wikilinks to cluster siblings (Related Papers section) but ZERO
wikilinks pointing UP to the cluster overview or MOC. The graph
view shows two tight blobs with isolated overview/MOC nodes
floating beside them — the hub-and-spoke mental model is broken.

This module backfills a `## Hub` section right after `## Related
Concepts` (if present) or right before `## Notes & Annotations` (if
present) — i.e. between metadata-derived sections and user-content
sections. Idempotent: re-running on a note that already has the
section is a no-op.

The Hub section looks like:

    ## Hub

    - Cluster: [[<cluster-slug>/00_overview|<cluster-slug>]]
    - MOC: [[LLM-Agents]]
    - MOC: [[Water-Resources]]

Decision (V088_PLAN.md §5): one bullet per MOC, prefix "MOC:" so
the user can scan visually. Cluster line uses pipe-alias form so
graph view shows the slug, not the verbose `slug/00_overview` path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from research_hub.vault.hub_overview import derive_moc_links


_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)
_TOPIC_CLUSTER_RE = re.compile(r'^topic_cluster:\s*"?([^"\n]+)"?\s*$', re.MULTILINE)
_HUB_SECTION_RE = re.compile(r"^##[ \t]+Hub[ \t]*\n", re.MULTILINE)
# Inject Hub section before any of these sections, in priority order.
_BEFORE_HEADINGS = (
    "Notes & Annotations",
    "Summary",  # auto-generated summary block from §4
)


@dataclass(frozen=True)
class HubMigrationResult:
    path: Path
    action: str  # "added" | "already_present" | "skipped_no_topic_cluster" | "skipped_no_frontmatter"


def _build_hub_section(cluster_slug: str, moc_links: list[str]) -> str:
    lines = [f"- Cluster: [[{cluster_slug}/00_overview|{cluster_slug}]]"]
    for moc in moc_links:
        moc_clean = str(moc).strip()
        if moc_clean:
            lines.append(f"- MOC: [[{moc_clean}]]")
    return "\n## Hub\n\n" + "\n".join(lines) + "\n"


def migrate_one_note(
    path: Path,
    *,
    cluster_moc_links_map: dict[str, list[str]] | None = None,
) -> HubMigrationResult:
    """Inject `## Hub` section into one paper note. Idempotent.

    ``cluster_moc_links_map`` lets the caller pre-load each cluster's
    explicit `moc_links` (from `clusters.yaml`) so the auto-derived
    sub-MOC suppression rule in `derive_moc_links` actually fires for
    backfilled notes. Without this map, the generated `## Hub` block
    would emit the slug-derived sub-MOC instead of the user override.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return HubMigrationResult(path=path, action="skipped_no_frontmatter")

    fm = _FRONTMATTER_RE.search(text)
    if not fm:
        return HubMigrationResult(path=path, action="skipped_no_frontmatter")
    tc = _TOPIC_CLUSTER_RE.search(fm.group(1))
    if not tc or not tc.group(1).strip():
        return HubMigrationResult(path=path, action="skipped_no_topic_cluster")
    cluster_slug = tc.group(1).strip()

    if _HUB_SECTION_RE.search(text):
        return HubMigrationResult(path=path, action="already_present")

    explicit_moc_links = list((cluster_moc_links_map or {}).get(cluster_slug, []))
    moc_links = derive_moc_links(cluster_slug, moc_links=explicit_moc_links)
    hub_section = _build_hub_section(cluster_slug, moc_links)

    # Find injection point: before any of the user-facing sections, after
    # the metadata sections.
    insertion_index = -1
    for heading in _BEFORE_HEADINGS:
        m = re.search(rf"^##[ \t]+{re.escape(heading)}[ \t]*$", text, re.MULTILINE)
        if m and (insertion_index == -1 or m.start() < insertion_index):
            insertion_index = m.start()

    if insertion_index >= 0:
        new_text = text[:insertion_index] + hub_section + "\n" + text[insertion_index:]
    else:
        # No anchor — append at end (before final `---` source line if any).
        # Conservative: just append before the final newline.
        if text.endswith("\n"):
            new_text = text.rstrip("\n") + "\n" + hub_section
        else:
            new_text = text + "\n" + hub_section

    path.write_text(new_text, encoding="utf-8")
    return HubMigrationResult(path=path, action="added")


def migrate_all(
    vault_root: Path,
    *,
    cluster_slug_filter: str | None = None,
    dry_run: bool = False,
    cluster_moc_links_map: dict[str, list[str]] | None = None,
) -> list[HubMigrationResult]:
    """Walk raw/*/*.md and ensure each has a `## Hub` section.

    ``cluster_moc_links_map`` is forwarded to `migrate_one_note` so
    explicit `LLM-Agents-*` / `Water-Resources-*` overrides set in
    `clusters.yaml` are honoured during backfill. Callers (CLI) should
    pre-build this map by walking ClusterRegistry once.
    """
    raw_root = vault_root / "raw"
    if not raw_root.exists():
        return []
    results: list[HubMigrationResult] = []
    pattern = f"{cluster_slug_filter}/*.md" if cluster_slug_filter else "*/*.md"
    for note in sorted(raw_root.glob(pattern)):
        if dry_run:
            # Simulate without writing.
            try:
                text = note.read_text(encoding="utf-8")
            except OSError:
                results.append(HubMigrationResult(path=note, action="skipped_no_frontmatter"))
                continue
            if not _FRONTMATTER_RE.search(text):
                results.append(HubMigrationResult(path=note, action="skipped_no_frontmatter"))
                continue
            if not _TOPIC_CLUSTER_RE.search(text):
                results.append(HubMigrationResult(path=note, action="skipped_no_topic_cluster"))
                continue
            if _HUB_SECTION_RE.search(text):
                results.append(HubMigrationResult(path=note, action="already_present"))
                continue
            results.append(HubMigrationResult(path=note, action="added"))
        else:
            results.append(
                migrate_one_note(
                    note,
                    cluster_moc_links_map=cluster_moc_links_map,
                )
            )
    return results
