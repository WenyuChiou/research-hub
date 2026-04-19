"""Garbage collection for research-hub accumulated files (v0.46).

Targets:
  - .research_hub/bundles/<cluster>-<ts>/ ??PDF bundle dirs (each ~20 MB)       
  - .research_hub/nlm-debug-*.jsonl       ??per-run NLM debug logs
  - .research_hub/artifacts/<slug>/ask-*.md
  - .research_hub/artifacts/<slug>/brief-*.txt

Default mode is dry-run (lists what would delete + total bytes).
Pass apply=True to actually remove.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


# bundle dir name format: <cluster_slug>-<UTC ISO timestamp like 20260419T184107Z>
BUNDLE_NAME_RE = re.compile(r"^(?P<slug>.+?)-(?P<ts>\d{8}T\d{6}Z)$")


@dataclass
class GcCandidate:
    path: Path
    size_bytes: int = 0
    cluster: Optional[str] = None
    timestamp: Optional[str] = None  # for sorting
    reason: str = ""

    def is_dir(self) -> bool:
        return self.path.is_dir()


@dataclass
class GcReport:
    bundles: list[GcCandidate] = field(default_factory=list)
    debug_logs: list[GcCandidate] = field(default_factory=list)
    artifacts: list[GcCandidate] = field(default_factory=list)
    bytes_deleted: int = 0
    files_deleted: int = 0
    dirs_deleted: int = 0
    apply: bool = False

    @property
    def total_bytes(self) -> int:
        return sum(c.size_bytes for c in self.bundles + self.debug_logs + self.artifacts)


def _path_size_bytes(path: Path) -> int:
    """Recursive size for dirs, file size for files."""
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    if path.is_dir():
        total = 0
        for child in path.rglob("*"):
            if child.is_file():
                try:
                    total += child.stat().st_size
                except OSError:
                    pass
        return total
    return 0


def list_stale_bundles(cfg, *, keep_per_cluster: int = 2) -> list[GcCandidate]: 
    """Return bundle dirs older than the most-recent N per cluster.

    Newest 2 bundles per cluster are kept. Order: by timestamp (UTC string      
    in dirname). All older are returned as candidates.
    """
    bundles_root = cfg.research_hub_dir / "bundles"
    if not bundles_root.exists():
        return []

    by_cluster: dict[str, list[GcCandidate]] = {}
    for child in bundles_root.iterdir():
        if not child.is_dir():
            continue
        match = BUNDLE_NAME_RE.match(child.name)
        if not match:
            continue
        slug = match.group("slug")
        ts = match.group("ts")
        candidate = GcCandidate(
            path=child,
            size_bytes=_path_size_bytes(child),
            cluster=slug,
            timestamp=ts,
            reason="bundle (older than keep window)",
        )
        by_cluster.setdefault(slug, []).append(candidate)

    stale: list[GcCandidate] = []
    for slug, bundles in by_cluster.items():
        # Sort by timestamp DESCENDING (newest first); slice to keep newest N   
        bundles.sort(key=lambda c: c.timestamp or "", reverse=True)
        stale.extend(bundles[keep_per_cluster:])
    return stale


def list_stale_debug_logs(cfg, *, older_than_days: int = 30) -> list[GcCandidate]:
    """Return nlm-debug-*.jsonl files older than the given threshold."""        
    debug_root = cfg.research_hub_dir
    if not debug_root.exists():
        return []
    cutoff = time.time() - older_than_days * 86400
    out: list[GcCandidate] = []
    for path in sorted(debug_root.glob("nlm-debug-*.jsonl")):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime < cutoff:
            out.append(
                GcCandidate(
                    path=path,
                    size_bytes=path.stat().st_size,
                    timestamp=datetime.fromtimestamp(mtime, tz=timezone.utc).strftime(
                        "%Y%m%dT%H%M%SZ"
                    ),
                    reason="debug log older than {0}d".format(older_than_days), 
                )
            )
    return out


def list_stale_artifacts(cfg, *, keep_per_cluster: int = 10) -> list[GcCandidate]:
    """Return ask-*.md / brief-*.txt artifacts beyond the keep window.

    Per cluster, keeps newest ``keep_per_cluster`` of EACH kind
    (ask vs brief). All older are returned as candidates.
    """
    artifacts_root = cfg.research_hub_dir / "artifacts"
    if not artifacts_root.exists():
        return []
    out: list[GcCandidate] = []
    for cluster_dir in sorted(artifacts_root.iterdir()):
        if not cluster_dir.is_dir():
            continue
        for pattern in ("ask-*.md", "brief-*.txt"):
            files = sorted(cluster_dir.glob(pattern), key=lambda p: p.name, reverse=True)
            for path in files[keep_per_cluster:]:
                out.append(
                    GcCandidate(
                        path=path,
                        size_bytes=path.stat().st_size,
                        cluster=cluster_dir.name,
                        timestamp=path.name,
                        reason="artifact (older than keep window)",
                    )
                )
    return out


def collect_garbage(
    cfg,
    *,
    do_bundles: bool = False,
    do_debug_logs: bool = False,
    do_artifacts: bool = False,
    keep_bundles: int = 2,
    debug_older_than_days: int = 30,
    keep_artifacts: int = 10,
    apply: bool = False,
) -> GcReport:
    """Collect (and optionally delete) stale files.

    Pass at least one of do_bundles / do_debug_logs / do_artifacts.
    """
    report = GcReport(apply=apply)

    if do_bundles:
        report.bundles = list_stale_bundles(cfg, keep_per_cluster=keep_bundles) 
    if do_debug_logs:
        report.debug_logs = list_stale_debug_logs(cfg, older_than_days=debug_older_than_days)
    if do_artifacts:
        report.artifacts = list_stale_artifacts(cfg, keep_per_cluster=keep_artifacts)

    if not apply:
        return report

    # Apply: delete + tally
    import shutil

    for candidate in report.bundles:
        try:
            if candidate.path.is_dir():
                shutil.rmtree(candidate.path)
                report.dirs_deleted += 1
            else:
                candidate.path.unlink()
                report.files_deleted += 1
            report.bytes_deleted += candidate.size_bytes
        except OSError:
            continue
    for candidate in report.debug_logs + report.artifacts:
        try:
            candidate.path.unlink()
            report.files_deleted += 1
            report.bytes_deleted += candidate.size_bytes
        except OSError:
            continue

    return report


def format_bytes(n: int) -> str:
    """Pretty-print byte counts."""
    if n < 1024:
        return "{0} B".format(n)
    if n < 1024 * 1024:
        return "{0:.1f} KB".format(n / 1024)
    if n < 1024 * 1024 * 1024:
        return "{0:.1f} MB".format(n / 1024 / 1024)
    return "{0:.1f} GB".format(n / 1024 / 1024 / 1024)
