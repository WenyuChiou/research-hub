"""Cluster sync status and Zotero-to-Obsidian reconcile helpers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


def _normalize_doi(doi: str) -> str:
    """Match the normalization rule used by research_hub.dedup."""
    if not doi:
        return ""
    normalized = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
    return normalized.strip()


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


def _frontmatter_value(md_path: Path, field_name: str) -> str:
    frontmatter = _read_frontmatter(md_path)
    if not frontmatter:
        return ""
    pattern = rf'^{field_name}:\s*[\'"]?([^\'"\n]*)[\'"]?'
    match = re.search(pattern, frontmatter, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _note_topic_cluster(md_path: Path) -> str:
    """Fast regex read of YAML `topic_cluster` field. Returns '' if missing."""
    return _frontmatter_value(md_path, "topic_cluster")


def _note_doi(md_path: Path) -> str:
    return _normalize_doi(_frontmatter_value(md_path, "doi"))


@dataclass
class ClusterSyncStatus:
    cluster_slug: str
    zotero_count: int = 0
    obsidian_count: int = 0
    nlm_cached_count: int = 0
    in_both: int = 0
    zotero_only: list[str] = field(default_factory=list)
    obsidian_only: list[Path] = field(default_factory=list)
    zotero_collection_key: str = ""
    notebook_url: str = ""
    last_synced: str = ""


def list_cluster_notes(cluster_slug: str, raw_dir: Path) -> list[Path]:
    """Find all Obsidian notes whose YAML topic_cluster matches a slug."""
    if not raw_dir.exists():
        return []
    return [md for md in sorted(raw_dir.rglob("*.md")) if _note_topic_cluster(md) == cluster_slug]


def list_zotero_collection_items(zot, collection_key: str) -> list[dict]:
    """Pull every non-attachment and non-note item from a Zotero collection."""
    items: list[dict] = []
    start = 0
    while True:
        batch = zot.collection_items(
            collection_key,
            start=start,
            limit=100,
            itemType="-attachment || note",
        )
        if not batch:
            break
        items.extend(batch)
        if len(batch) < 100:
            break
        start += 100
    return items


def compute_sync_status(
    cluster,
    zot,
    raw_dir: Path,
    nlm_cache_path: Path | None = None,
) -> ClusterSyncStatus:
    """Build a sync report for one cluster."""
    status = ClusterSyncStatus(
        cluster_slug=cluster.slug,
        zotero_collection_key=cluster.zotero_collection_key or "",
        notebook_url=cluster.notebooklm_notebook_url or "",
    )

    obsidian_notes = list_cluster_notes(cluster.slug, raw_dir)
    obsidian_by_doi = {
        doi: note_path for note_path in obsidian_notes if (doi := _note_doi(note_path))
    }
    status.obsidian_count = len(obsidian_notes)

    if zot is not None and cluster.zotero_collection_key:
        zot_items = list_zotero_collection_items(zot, cluster.zotero_collection_key)
        zot_by_doi: dict[str, str] = {}
        for item in zot_items:
            data = item.get("data", {})
            doi = _normalize_doi(data.get("DOI", ""))
            if doi:
                zot_by_doi[doi] = item.get("key", "")
        status.zotero_count = len(zot_items)

        both = set(obsidian_by_doi) & set(zot_by_doi)
        status.in_both = len(both)

        zot_only_dois = set(zot_by_doi) - set(obsidian_by_doi)
        status.zotero_only = sorted(zot_by_doi[doi] for doi in zot_only_dois if zot_by_doi[doi])

        obsidian_only_dois = set(obsidian_by_doi) - set(zot_by_doi)
        status.obsidian_only = sorted(obsidian_by_doi[doi] for doi in obsidian_only_dois)

    if nlm_cache_path is not None and nlm_cache_path.exists():
        try:
            cache = json.loads(nlm_cache_path.read_text(encoding="utf-8"))
            entry = cache.get(cluster.slug) or {}
            status.nlm_cached_count = int(entry.get("uploaded_doi_count", 0))
            status.notebook_url = entry.get("notebook_url", status.notebook_url)
            status.last_synced = entry.get("last_synced", "")
        except (OSError, TypeError, ValueError):
            pass

    return status


@dataclass
class ReconcileReport:
    cluster_slug: str
    created_notes: list[Path] = field(default_factory=list)
    skipped_existing: int = 0
    errors: list[dict] = field(default_factory=list)
    dry_run: bool = False


def reconcile_zotero_to_obsidian(
    cluster,
    zot,
    cfg,
    dry_run: bool = True,
) -> ReconcileReport:
    """Create missing Obsidian notes for each Zotero item not already in the cluster."""
    from research_hub.zotero.fetch import extract_item_data, make_raw_md, safe_filename

    report = ReconcileReport(cluster_slug=cluster.slug, dry_run=dry_run)
    if not cluster.zotero_collection_key:
        return report

    existing_dois = {_note_doi(note) for note in list_cluster_notes(cluster.slug, cfg.raw)}
    target_dir = cfg.raw / (cluster.obsidian_subfolder or cluster.slug)
    if not dry_run:
        target_dir.mkdir(parents=True, exist_ok=True)

    items = list_zotero_collection_items(zot, cluster.zotero_collection_key)
    planned_paths: set[Path] = set()
    for item in items:
        try:
            item_data = extract_item_data(item)
            if item_data is None:
                continue

            doi_norm = _normalize_doi(item_data.get("doi", ""))
            if doi_norm and doi_norm in existing_dois:
                report.skipped_existing += 1
                continue

            authors = item_data.get("authors", [])
            first_author = authors[0] if authors else "Unknown"
            base_name = safe_filename(
                first_author,
                item_data.get("year", ""),
                item_data.get("title", ""),
            )
            target_path = target_dir / base_name
            counter = 1
            while target_path.exists() or target_path in planned_paths:
                target_path = target_dir / f"{Path(base_name).stem}-{counter}.md"
                counter += 1

            if not dry_run:
                markdown = make_raw_md(
                    item_data,
                    [cluster.zotero_collection_key],
                    [],
                    topic_cluster=cluster.slug,
                    cluster_queries=[cluster.first_query or cluster.name],
                    ingestion_source="sync-reconcile-v0.4.0",
                )
                target_path.write_text(markdown, encoding="utf-8")

            planned_paths.add(target_path)
            if doi_norm:
                existing_dois.add(doi_norm)
            report.created_notes.append(target_path)
        except Exception as exc:  # pragma: no cover - defensive on mixed Zotero data
            report.errors.append({"key": item.get("key", ""), "error": str(exc)})

    return report
