from __future__ import annotations

import logging
import re
from pathlib import Path

from research_hub.dashboard.types import DriftAlert

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


def detect_drift(cfg, dedup) -> list[DriftAlert]:
    """Find inconsistencies between manual edits and pipeline state."""
    alerts: list[DriftAlert] = []
    try:
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
    except Exception:
        logger.exception("Failed to detect dashboard drift")
    return alerts
