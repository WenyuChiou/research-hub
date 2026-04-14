from __future__ import annotations

import logging
import re
from pathlib import Path

from research_hub.clusters import ClusterRegistry
from research_hub.dashboard.types import DriftAlert
from research_hub.manifest import Manifest
from research_hub.utils.doi import normalize_doi

logger = logging.getLogger(__name__)


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


def _field(frontmatter: str, key: str) -> str:
    match = re.search(rf'^{re.escape(key)}:\s*[\'"]?([^\'"\n]*)[\'"]?', frontmatter, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _parse_frontmatter(frontmatter: str) -> dict[str, object]:
    if not frontmatter.strip():
        return {}
    try:
        import yaml

        parsed = yaml.safe_load(frontmatter) or {}
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _check_zotero_orphans(cfg, cluster, zot) -> list[DriftAlert]:
    alerts: list[DriftAlert] = []
    if not cluster.zotero_collection_key or zot is None:
        return alerts
    try:
        items = zot.collection_items(cluster.zotero_collection_key, limit=500)
    except Exception:
        return alerts

    cluster_raw_dir = Path(cfg.raw) / (cluster.obsidian_subfolder or cluster.slug)
    if not cluster_raw_dir.exists():
        return alerts

    note_dois: set[str] = set()
    for note in cluster_raw_dir.glob("*.md"):
        doi = _field(_read_frontmatter(note), "doi")
        if doi:
            note_dois.add(normalize_doi(doi))

    for item in items:
        data = item.get("data", {})
        item_doi = normalize_doi(str(data.get("DOI", "") or ""))
        if item_doi and item_doi not in note_dois:
            alerts.append(
                DriftAlert(
                    kind="zotero_orphan",
                    severity="WARN",
                    title="Zotero item has no matching note",
                    description=(
                        f"Zotero item '{str(data.get('title', '') or '')[:60]}' exists in the "
                        f"{cluster.slug} collection but no matching .md note was found."
                    ),
                    sample_paths=[],
                    fix_command=f"research-hub pipeline repair --cluster {cluster.slug} --execute",
                )
            )
    return alerts


def _check_subtopic_paper_mismatch(cfg, cluster) -> list[DriftAlert]:
    alerts: list[DriftAlert] = []
    topics_dir = Path(cfg.raw) / cluster.slug / "topics"
    if not topics_dir.exists():
        return alerts

    for sub_file in sorted(topics_dir.glob("*.md")):
        try:
            text = sub_file.read_text(encoding="utf-8")
        except OSError:
            continue
        frontmatter = ""
        if text.startswith("---"):
            end = text.find("\n---", 3)
            if end >= 0:
                frontmatter = text[3:end]
        parsed = _parse_frontmatter(frontmatter)
        try:
            declared = int(parsed.get("papers", 0) or 0)
        except (TypeError, ValueError):
            declared = 0
        papers_match = re.search(r"^## Papers\s*$(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
        actual = 0
        if papers_match:
            actual = len(re.findall(r"\[\[([^\|\]]+)", papers_match.group(1)))
        if declared != actual:
            alerts.append(
                DriftAlert(
                    kind="subtopic_paper_mismatch",
                    severity="WARN",
                    title="Subtopic paper count drift",
                    description=f"{sub_file.name}: frontmatter papers={declared}, actual links={actual}",
                    sample_paths=[str(sub_file)],
                    fix_command=f"research-hub topic build --cluster {cluster.slug}",
                )
            )
    return alerts


def _check_stale_manifest_clusters(cfg, registry: ClusterRegistry) -> list[DriftAlert]:
    manifest_path = cfg.research_hub_dir / "manifest.jsonl"
    if not manifest_path.exists():
        return []
    known = set(registry.clusters)
    stale = sorted(
        {
            entry.cluster
            for entry in Manifest(manifest_path).read_all()
            if entry.cluster and entry.cluster not in known
        }
    )
    if not stale:
        return []
    return [
        DriftAlert(
            kind="stale_manifest_cluster",
            severity="WARN",
            title="Manifest references unknown clusters",
            description="manifest.jsonl contains entries for cluster slugs missing from clusters.yaml.",
            sample_paths=stale[:10],
            fix_command="research-hub clusters list",
        )
    ]


def detect_drift(cfg, dedup, zot=None) -> list[DriftAlert]:
    """Find inconsistencies between manual edits and pipeline state."""
    alerts: list[DriftAlert] = []
    try:
        registry = ClusterRegistry(cfg.clusters_file)
        folder_mismatches: list[str] = []
        orphan_notes: list[str] = []
        for md_path in sorted(cfg.raw.rglob("*.md")):
            frontmatter = _read_frontmatter(md_path)
            cluster_value = _field(frontmatter, "topic_cluster")
            if not cluster_value:
                orphan_notes.append(str(md_path))
                continue
            parent_slug = md_path.parent.name
            if cluster_value != parent_slug:
                folder_mismatches.append(str(md_path))
        if folder_mismatches:
            slug = Path(folder_mismatches[0]).stem
            alerts.append(
                DriftAlert(
                    kind="folder_mismatch",
                    severity="WARN",
                    title="Folder and topic_cluster disagree",
                    description="Some notes are stored under a different folder than their YAML cluster binding.",
                    sample_paths=folder_mismatches[:10],
                    fix_command=f"research-hub move {slug} --to <topic_cluster_value>",
                )
            )
        if orphan_notes:
            slug = Path(orphan_notes[0]).stem
            alerts.append(
                DriftAlert(
                    kind="orphan_note",
                    severity="WARN",
                    title="Notes are missing topic_cluster",
                    description="Some notes are unassigned and will be skipped by cluster-based tooling.",
                    sample_paths=orphan_notes[:10],
                    fix_command=f"research-hub migrate-yaml --assign-cluster {slug}",
                )
            )
        duplicate_samples: list[str] = []
        duplicate_doi = ""
        for doi, hits in getattr(dedup, "doi_to_hits", {}).items():
            sources = {hit.source for hit in hits}
            if not {"zotero", "obsidian"} <= sources:
                continue
            clusters = {
                Path(hit.obsidian_path).parent.name
                for hit in hits
                if getattr(hit, "obsidian_path", None)
            }
            if len(clusters) > 1:
                duplicate_doi = doi
                duplicate_samples = sorted(
                    str(Path(hit.obsidian_path))
                    for hit in hits
                    if getattr(hit, "obsidian_path", None)
                )
                break
        if duplicate_samples:
            alerts.append(
                DriftAlert(
                    kind="duplicate_doi",
                    severity="WARN",
                    title="Duplicate DOI spans multiple cluster bindings",
                    description="The dedup index shows the same DOI across Zotero and Obsidian with conflicting cluster folders.",
                    sample_paths=duplicate_samples[:10],
                    fix_command=f"research-hub dedup invalidate --doi {duplicate_doi}",
                )
            )
        stale_paths = sorted(
            {
                str(Path(hit.obsidian_path))
                for hits in getattr(dedup, "doi_to_hits", {}).values()
                for hit in hits
                if getattr(hit, "obsidian_path", None) and not Path(hit.obsidian_path).exists()
            }
        )
        if stale_paths:
            alerts.append(
                DriftAlert(
                    kind="stale_dedup_path",
                    severity="WARN",
                    title="Dedup index points to missing notes",
                    description="Some obsidian-backed dedup hits reference note paths that no longer exist.",
                    sample_paths=stale_paths[:10],
                    fix_command="research-hub dedup rebuild --obsidian-only",
                )
            )
        if zot is None and any(cluster.zotero_collection_key for cluster in registry.list()):
            try:
                from research_hub.zotero.client import ZoteroDualClient

                dual = ZoteroDualClient()
                zot = getattr(dual, "web", dual)
            except Exception:
                zot = None
        for cluster in registry.list():
            alerts.extend(_check_zotero_orphans(cfg, cluster, zot))
            alerts.extend(_check_subtopic_paper_mismatch(cfg, cluster))
        alerts.extend(_check_stale_manifest_clusters(cfg, registry))
    except Exception:
        logger.exception("Failed to detect dashboard drift")
    return alerts
