"""Reconcile Zotero + Obsidian + dedup_index for a cluster.

Used after a partial pipeline failure to recover orphaned Zotero items,
rebuild missing Obsidian notes, and prune stale dedup entries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


def _frontmatter_value(md_path: Path, field_name: str) -> str:
    try:
        text = md_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    if end < 0:
        return ""
    frontmatter = text[3:end]
    pattern = rf'^{field_name}:\s*[\'"]?([^\'"\n]*)[\'"]?'
    match = re.search(pattern, frontmatter, re.MULTILINE)
    return match.group(1).strip() if match else ""


@dataclass
class RepairReport:
    cluster_slug: str
    dry_run: bool
    zotero_orphans: list[dict] = field(default_factory=list)
    obsidian_orphans: list[str] = field(default_factory=list)
    stale_dedup: list[str] = field(default_factory=list)
    created_notes: list[str] = field(default_factory=list)
    folder_mismatches: list[str] = field(default_factory=list)
    duplicate_dois: list[dict[str, object]] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"Repair report for cluster '{self.cluster_slug}' ({'dry-run' if self.dry_run else 'executed'}):",
            f"  Zotero orphans (no Obsidian note):   {len(self.zotero_orphans)}",
            f"  Obsidian orphans (no Zotero item):   {len(self.obsidian_orphans)}",
            f"  Stale dedup entries:                 {len(self.stale_dedup)}",
        ]
        if not self.dry_run:
            lines.append(f"  Created Obsidian notes:            {len(self.created_notes)}")
        return "\n".join(lines)


def _iter_collection_items(zot, collection_key: str) -> list[dict]:
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


def _target_note_path(target_dir: Path, base_name: str) -> Path:
    target_path = target_dir / base_name
    counter = 1
    while target_path.exists():
        target_path = target_dir / f"{Path(base_name).stem}-{counter}.md"
        counter += 1
    return target_path


def _prune_stale_doi(index, doi: str) -> None:
    from research_hub.utils.doi import normalize_doi

    normalized = normalize_doi(doi)
    if not normalized:
        return
    if normalized in index.doi_to_hits:
        del index.doi_to_hits[normalized]
    for title_key in list(index.title_to_hits.keys()):
        kept = [hit for hit in index.title_to_hits[title_key] if normalize_doi(hit.doi) != normalized]
        if kept:
            index.title_to_hits[title_key] = kept
        else:
            del index.title_to_hits[title_key]


def repair_cluster(cfg, cluster_slug: str, *, dry_run: bool = True) -> RepairReport:
    """Reconcile Zotero, Obsidian, and dedup_index for one cluster."""
    from research_hub.clusters import ClusterRegistry
    from research_hub.dedup import DedupHit, DedupIndex
    from research_hub.manifest import Manifest, new_entry
    from research_hub.utils.doi import normalize_doi
    from research_hub.zotero.client import ZoteroDualClient
    from research_hub.zotero.fetch import extract_item_data, make_raw_md, safe_filename

    registry = ClusterRegistry(cfg.clusters_file)
    cluster = registry.get(cluster_slug)
    if cluster is None:
        raise ValueError(f"Cluster not found: {cluster_slug}")

    report = RepairReport(cluster_slug=cluster_slug, dry_run=dry_run)
    dedup_path = cfg.research_hub_dir / "dedup_index.json"
    dedup = DedupIndex.load(dedup_path)
    manifest = Manifest(cfg.research_hub_dir / "manifest.jsonl")
    action_query = cluster.first_query or cluster.name or cluster.slug

    raw_dir = cfg.raw / (cluster.obsidian_subfolder or cluster.slug)
    note_paths = sorted(raw_dir.glob("*.md")) if raw_dir.exists() else []
    notes_by_doi: dict[str, Path] = {}
    for note_path in note_paths:
        topic_cluster = _frontmatter_value(note_path, "topic_cluster")
        if topic_cluster and topic_cluster != cluster.slug:
            report.folder_mismatches.append(str(note_path))
        doi = normalize_doi(_frontmatter_value(note_path, "doi"))
        if doi:
            notes_by_doi[doi] = note_path

    zotero_by_doi: dict[str, dict] = {}
    if cluster.zotero_collection_key:
        dual = ZoteroDualClient()
        zot_read = getattr(dual, "web", dual)
        for item in _iter_collection_items(zot_read, cluster.zotero_collection_key):
            data = item.get("data", {})
            doi = normalize_doi(data.get("DOI", ""))
            if doi:
                zotero_by_doi[doi] = item

    for doi, item in sorted(zotero_by_doi.items()):
        if doi in notes_by_doi:
            continue
        item_data = extract_item_data(item)
        if item_data is None:
            continue
        orphan = {
            "doi": doi,
            "key": item.get("key", ""),
            "title": item_data.get("title", ""),
        }
        report.zotero_orphans.append(orphan)
        if dry_run:
            continue
        raw_dir.mkdir(parents=True, exist_ok=True)
        authors = item_data.get("authors", [])
        first_author = authors[0] if authors else "Unknown"
        base_name = safe_filename(first_author, item_data.get("year", ""), item_data.get("title", ""))
        target_path = _target_note_path(raw_dir, base_name)
        markdown = make_raw_md(
            item_data,
            [cluster.zotero_collection_key],
            [],
            topic_cluster=cluster.slug,
            cluster_queries=[cluster.first_query or cluster.name],
            ingestion_source="pipeline-repair-v0.12.0",
        )
        target_path.write_text(markdown, encoding="utf-8")
        report.created_notes.append(str(target_path))
        manifest.append(
            new_entry(
                cluster.slug,
                action_query,
                "repair_created_note",
                doi=doi,
                title=item_data.get("title", ""),
                zotero_key=item.get("key", ""),
                obsidian_path=str(target_path),
            )
        )
        notes_by_doi[doi] = target_path

    for doi, note_path in sorted(notes_by_doi.items()):
        if doi not in zotero_by_doi:
            report.obsidian_orphans.append(str(note_path))

    if not dry_run:
        for doi, item in zotero_by_doi.items():
            data = item.get("data", {})
            dedup.add(
                DedupHit(
                    source="zotero",
                    doi=doi,
                    title=data.get("title", ""),
                    zotero_key=item.get("key"),
                )
            )
        for doi, note_path in notes_by_doi.items():
            dedup.add(
                DedupHit(
                    source="obsidian",
                    doi=doi,
                    title=_frontmatter_value(note_path, "title"),
                    zotero_key=_frontmatter_value(note_path, "zotero-key") or None,
                    obsidian_path=str(note_path),
                )
            )

    stale_paths: set[str] = set()
    stale_markers: set[str] = set()
    for hits in dedup.doi_to_hits.values():
        for hit in hits:
            obsidian_path = getattr(hit, "obsidian_path", None)
            if obsidian_path and not Path(obsidian_path).exists():
                stale_paths.add(obsidian_path)
                stale_markers.add(normalize_doi(getattr(hit, "doi", "")) or obsidian_path)
    for hits in dedup.title_to_hits.values():
        for hit in hits:
            obsidian_path = getattr(hit, "obsidian_path", None)
            if obsidian_path and not Path(obsidian_path).exists():
                stale_paths.add(obsidian_path)
                stale_markers.add(normalize_doi(getattr(hit, "doi", "")) or obsidian_path)
    for marker in sorted(stale_markers):
        report.stale_dedup.append(marker)
    for stale_path in sorted(stale_paths):
        if not dry_run:
            dedup.invalidate_obsidian_path(stale_path)
            manifest.append(
                new_entry(
                    cluster.slug,
                    action_query,
                    "repair_pruned_dedup",
                    obsidian_path=stale_path,
                )
            )

    live_dois = set(notes_by_doi) | set(zotero_by_doi)
    for doi in sorted(dedup.doi_to_hits.keys()):
        if doi and doi not in live_dois:
            if doi not in report.stale_dedup:
                report.stale_dedup.append(doi)
            if not dry_run:
                _prune_stale_doi(dedup, doi)
                manifest.append(
                    new_entry(
                        cluster.slug,
                        action_query,
                        "repair_pruned_dedup",
                        doi=doi,
                    )
                )

    duplicate_map: dict[str, set[str]] = {}
    for doi, hits in dedup.doi_to_hits.items():
        clusters = {
            Path(hit.obsidian_path).parent.name
            for hit in hits
            if getattr(hit, "obsidian_path", None)
        }
        if len(clusters) > 1:
            duplicate_map[doi] = clusters
    for doi, clusters in sorted(duplicate_map.items()):
        report.duplicate_dois.append({"doi": doi, "clusters": sorted(clusters)})

    if not dry_run:
        dedup.save(dedup_path)

    return report
