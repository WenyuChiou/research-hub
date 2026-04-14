"""Run-once vault synchronization audit. Writes docs/audit_v0.26_vault_sync.md."""

from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace

from research_hub.clusters import ClusterRegistry
from research_hub.dedup import DedupIndex
from research_hub.dashboard.drift import detect_drift
from research_hub.manifest import Manifest


def _count_obsidian_notes(raw_dir: Path, slug: str) -> int:
    cluster_dir = raw_dir / slug
    if not cluster_dir.exists():
        return 0
    return len(list(cluster_dir.glob("*.md")))


def _count_dedup_hits(index: DedupIndex, slug: str) -> int:
    paths = {
        str(Path(hit.obsidian_path))
        for hits in index.doi_to_hits.values()
        for hit in hits
        if getattr(hit, "source", "") == "obsidian"
        and getattr(hit, "obsidian_path", None)
        and Path(hit.obsidian_path).parent.name == slug
    }
    return len(paths)


def _stale_dedup_paths(index: DedupIndex) -> list[str]:
    return sorted(
        {
            str(Path(hit.obsidian_path))
            for hits in index.doi_to_hits.values()
            for hit in hits
            if getattr(hit, "obsidian_path", None) and not Path(hit.obsidian_path).exists()
        }
    )


def _build_cfg(vault: Path) -> SimpleNamespace:
    research_hub_dir = vault / ".research_hub"
    return SimpleNamespace(
        root=vault,
        raw=vault / "raw",
        research_hub_dir=research_hub_dir,
        clusters_file=research_hub_dir / "clusters.yaml",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault", default=str(Path.home() / "knowledge-base"))
    args = parser.parse_args()

    vault = Path(args.vault).expanduser()
    cfg = _build_cfg(vault)
    registry = ClusterRegistry(cfg.clusters_file)
    dedup = DedupIndex.load(cfg.research_hub_dir / "dedup_index.json")
    manifest = Manifest(cfg.research_hub_dir / "manifest.jsonl")

    rows: list[str] = []
    orphan_clusters: list[str] = []
    recommended_fixes: set[str] = set()
    for cluster in registry.list():
        zotero_count = "n/a"
        obsidian_count = _count_obsidian_notes(cfg.raw, cluster.slug)
        dedup_count = _count_dedup_hits(dedup, cluster.slug)
        if obsidian_count == 0:
            orphan_clusters.append(cluster.slug)
        status = "OK" if obsidian_count == dedup_count else "DRIFT"
        rows.append(f"| {cluster.slug} | {zotero_count} | {obsidian_count} | {dedup_count} | {status} |")
        if status != "OK":
            recommended_fixes.add(f"research-hub pipeline repair --cluster {cluster.slug} --execute")

    known_slugs = {cluster.slug for cluster in registry.list()}
    unknown_folders = sorted(
        entry.name
        for entry in cfg.raw.iterdir()
        if entry.is_dir() and entry.name not in known_slugs and not entry.name.startswith("_")
    ) if cfg.raw.exists() else []
    stale_paths = _stale_dedup_paths(dedup)
    stale_manifest = sorted({entry.cluster for entry in manifest.read_all() if entry.cluster and entry.cluster not in known_slugs})
    drift_alerts = detect_drift(cfg, dedup, zot=None)
    for alert in drift_alerts:
        if alert.fix_command:
            recommended_fixes.add(alert.fix_command)

    report = "\n".join(
        [
            "# Vault Sync Audit - v0.26.0",
            "",
            "## Per-cluster counts",
            "",
            "| Cluster | Zotero | Obsidian | Dedup | Status |",
            "|---|---|---|---|---|",
            *(rows or ["| (none) | 0 | 0 | 0 | OK |"]),
            "",
            "## Orphan clusters (no notes on disk)",
            "",
            *(orphan_clusters or ["(none)"]),
            "",
            "## Unknown raw/ folders (not in registry)",
            "",
            *(unknown_folders or ["(none)"]),
            "",
            "## Stale dedup paths",
            "",
            *(stale_paths or ["(none)"]),
            "",
            "## Stale manifest cluster references",
            "",
            *(stale_manifest or ["(none)"]),
            "",
            "## Active drift alerts",
            "",
            "| Kind | Cluster | Detail | Fix |",
            "|---|---|---|---|",
            *(
                [
                    f"| {alert.kind} | {','.join(alert.sample_paths[:1]) or ''} | {alert.description} | {alert.fix_command} |"
                    for alert in drift_alerts
                ]
                or ["| (none) |  |  |  |"]
            ),
            "",
            "## Summary",
            "",
            f"- Total clusters: {len(known_slugs)}",
            f"- Clusters with drift: {sum(1 for row in rows if row.endswith('| DRIFT |'))}",
            f"- Total orphans: {len(orphan_clusters)}",
            "- Recommended fix commands: " + (", ".join(sorted(recommended_fixes)) if recommended_fixes else "(none)"),
        ]
    )

    output = Path("docs") / "audit_v0.26_vault_sync.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
