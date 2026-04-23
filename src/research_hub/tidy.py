"""One-shot vault maintenance — v0.46.

Sequence:
  1. doctor --autofix (mechanical frontmatter backfills)
  2. dedup rebuild --obsidian-only
  3. bases emit --force per cluster (v0.43)
  4. cleanup --bundles --debug-logs --artifacts (preview by default)

Use ``apply_cleanup=True`` to actually flush the cleanup preview.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class TidyStep:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class TidyReport:
    steps: list[TidyStep] = field(default_factory=list)
    total_duration_sec: float = 0.0
    cleanup_preview_bytes: int = 0


def run_tidy(
    *,
    apply_cleanup: bool = False,
    print_progress: bool = True,
    cluster_slug: str | None = None,
) -> TidyReport:
    """Run the 4 maintenance sub-steps. Each step is non-fatal."""
    from research_hub.config import get_config

    cfg = get_config()
    started = time.time()
    report = TidyReport()

    # 1. doctor + autofix (mechanical frontmatter backfills)
    try:
        from research_hub.doctor import run_doctor
        from research_hub.vault_autofix import run_autofix

        autofix_summary = run_autofix(cfg)
        doctor_results = run_doctor()
        ok_count = sum(1 for r in doctor_results if getattr(r, "status", "") == "OK")
        info_count = sum(
            1 for r in doctor_results if getattr(r, "status", "") in ("INFO", "ii")
        )
        warn_count = sum(
            1 for r in doctor_results if getattr(r, "status", "") in ("WARN", "!!")
        )
        autofix_total = sum(int(v or 0) for k, v in autofix_summary.items() if k != "skipped_no_cluster")
        detail = "{0} checks ({1} OK, {2} INFO, {3} WARN); autofix backfilled {4} fields".format(
            len(doctor_results), ok_count, info_count, warn_count, autofix_total,
        )
        report.steps.append(TidyStep(name="doctor", ok=True, detail=detail))
    except Exception as exc:
        report.steps.append(TidyStep(name="doctor", ok=False, detail=str(exc)))

    # 2. dedup rebuild from Obsidian raw notes
    try:
        from research_hub.dedup import DedupIndex

        index_path = cfg.research_hub_dir / "dedup_index.json"
        index = DedupIndex.load(index_path)
        index.rebuild_from_obsidian(cfg.raw)
        index.save(index_path)
        detail = "{0} DOIs, {1} titles".format(
            len(index.doi_to_hits), len(index.title_to_hits)
        )
        report.steps.append(TidyStep(name="dedup", ok=True, detail=detail))
    except Exception as exc:
        report.steps.append(TidyStep(name="dedup", ok=False, detail=str(exc)))

    # 3. bases emit --force per cluster
    try:
        from research_hub.clusters import ClusterRegistry
        from research_hub.obsidian_bases import write_cluster_base

        registry = ClusterRegistry(cfg.clusters_file)
        if cluster_slug:
            cluster = registry.get(cluster_slug)
            if cluster is None:
                raise ValueError(f"Cluster not found: {cluster_slug}")
            cluster_list = [cluster]
        else:
            cluster_list = registry.list()
        refreshed = 0
        for cluster in cluster_list:
            try:
                write_cluster_base(
                    hub_root=Path(cfg.hub),
                    cluster_slug=cluster.slug,
                    cluster_name=cluster.name,
                    obsidian_subfolder=cluster.obsidian_subfolder,
                    force=True,
                )
                refreshed += 1
            except Exception as inner:
                logger.warning("bases emit failed for %s: %s", cluster.slug, inner)
        detail = "{0} clusters refreshed".format(refreshed)
        report.steps.append(TidyStep(name="bases", ok=True, detail=detail))
    except Exception as exc:
        report.steps.append(TidyStep(name="bases", ok=False, detail=str(exc)))

    # 4. cleanup preview (or apply)
    try:
        from research_hub.cleanup import collect_garbage, format_bytes

        gc_report = collect_garbage(
            cfg,
            do_bundles=True,
            do_debug_logs=True,
            do_artifacts=True,
            apply=apply_cleanup,
        )
        report.cleanup_preview_bytes = gc_report.total_bytes
        verb = "freed" if apply_cleanup else "would free"
        detail = "{0} {1} ({2} files + {3} dirs)".format(
            verb,
            format_bytes(gc_report.total_bytes),
            len(gc_report.debug_logs) + len(gc_report.artifacts),
            len(gc_report.bundles),
        )
        if not apply_cleanup and gc_report.total_bytes > 0:
            detail += "  -- run `research-hub cleanup --all --apply` to apply"
        report.steps.append(TidyStep(name="cleanup", ok=True, detail=detail))
    except Exception as exc:
        report.steps.append(TidyStep(name="cleanup", ok=False, detail=str(exc)))

    report.total_duration_sec = time.time() - started

    if print_progress:
        for step in report.steps:
            symbol = "OK" if step.ok else "FAIL"
            print(f"[{symbol}] {step.name:<8} {step.detail}")
        print("Done in {0:.1f}s.".format(report.total_duration_sec))

    return report
