"""Test the v0.46 garbage collector."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from types import SimpleNamespace

from research_hub.cleanup import collect_garbage


@pytest.fixture
def test_cfg(tmp_path: Path):
    """Config-like SimpleNamespace pointing to a temporary vault.

    The real Config class is private (`_Config` constructed via `get_config()`);
    cleanup helpers only need ``research_hub_dir`` so SimpleNamespace is enough.
    """
    research_hub_dir = tmp_path / ".research_hub"
    research_hub_dir.mkdir()
    return SimpleNamespace(
        root=tmp_path,
        raw=tmp_path / "raw",
        hub=tmp_path / "hub",
        research_hub_dir=research_hub_dir,
        clusters_file=research_hub_dir / "clusters.yaml",
    )


def _make_dummy_bundles(cfg, spec: dict[str, list[str]]):
    """Create bundle dirs based on a spec like:
    {"cluster1": ["20260101T000000Z", "20260102T000000Z"]}
    """
    bundles_root = cfg.research_hub_dir / "bundles"
    bundles_root.mkdir(exist_ok=True)
    for slug, timestamps in spec.items():
        for ts in timestamps:
            bundle_dir = bundles_root / f"{slug}-{ts}"
            bundle_dir.mkdir()
            (bundle_dir / "dummy.pdf").write_text("dummy")


def _make_dummy_debug_logs(cfg, timestamps: list[int]):
    """Create nlm-debug-*.jsonl files with given mtimes."""
    for ts in timestamps:
        path = cfg.research_hub_dir / f"nlm-debug-{ts}.jsonl"
        path.write_text("dummy")
        path.touch()
        # Manually set mtime
        import os
        os.utime(path, (ts, ts))


def _make_dummy_artifacts(cfg, spec: dict[str, list[str]]):
    """Create artifact files: {"cluster1": ["ask-1.md", "brief-1.txt"]}."""
    artifacts_root = cfg.research_hub_dir / "artifacts"
    artifacts_root.mkdir(exist_ok=True)
    for slug, filenames in spec.items():
        cluster_dir = artifacts_root / slug
        cluster_dir.mkdir(exist_ok=True)
        for filename in filenames:
            (cluster_dir / filename).write_text("dummy")


def test_gc_bundles_dry_run(test_cfg):
    _make_dummy_bundles(test_cfg, {
        "c1": ["20260101T000000Z", "20260102T000000Z", "20260103T000000Z"],
        "c2": ["20260201T000000Z", "20260202T000000Z"],
        "c3": ["20260301T000000Z"],
    })
    report = collect_garbage(test_cfg, do_bundles=True, apply=False)
    assert len(report.bundles) == 1
    assert report.bundles[0].cluster == "c1"
    assert report.bundles[0].path.name == "c1-20260101T000000Z"
    assert report.total_bytes > 0
    assert report.bytes_deleted == 0
    assert report.files_deleted == 0
    assert report.dirs_deleted == 0


def test_gc_bundles_apply(test_cfg):
    _make_dummy_bundles(test_cfg, {"c1": ["20260101T000000Z", "20260102T000000Z"]})
    stale_path = test_cfg.research_hub_dir / "bundles" / "c1-20260101T000000Z"
    report = collect_garbage(test_cfg, do_bundles=True, keep_bundles=1, apply=True)
    assert len(report.bundles) == 1
    assert report.bundles[0].path == stale_path
    assert report.bytes_deleted > 0
    assert report.files_deleted == 0
    assert report.dirs_deleted == 1
    assert not stale_path.exists()
    assert (test_cfg.research_hub_dir / "bundles" / "c1-20260102T000000Z").exists()


def test_gc_debug_logs_dry_run(test_cfg):
    now = int(time.time())
    stale_ts = now - 40 * 86400  # 40 days ago
    fresh_ts = now - 10 * 86400  # 10 days ago
    _make_dummy_debug_logs(test_cfg, [stale_ts, fresh_ts])
    report = collect_garbage(test_cfg, do_debug_logs=True, apply=False)
    assert len(report.debug_logs) == 1
    assert report.debug_logs[0].path.name == f"nlm-debug-{stale_ts}.jsonl"
    assert report.total_bytes > 0
    assert report.bytes_deleted == 0
    assert report.files_deleted == 0


def test_gc_debug_logs_apply(test_cfg):
    now = int(time.time())
    stale_ts = now - 40 * 86400
    stale_path = test_cfg.research_hub_dir / f"nlm-debug-{stale_ts}.jsonl"
    _make_dummy_debug_logs(test_cfg, [stale_ts])
    report = collect_garbage(test_cfg, do_debug_logs=True, apply=True)
    assert len(report.debug_logs) == 1
    assert report.bytes_deleted > 0
    assert report.files_deleted == 1
    assert not stale_path.exists()


def test_gc_artifacts_dry_run(test_cfg):
    """Sort by filename DESCENDING (lex, not numeric) — for ask-0..ask-11:
       lex desc: ask-9, ask-8, ..., ask-2, ask-11, ask-10, ask-1, ask-0.
       With keep=10, stale = slice[10:] = [ask-1.md, ask-0.md].
    """
    _make_dummy_artifacts(test_cfg, {
        "c1": [f"ask-{i}.md" for i in range(12)],
        "c2": [f"brief-{i}.txt" for i in range(5)],
    })
    report = collect_garbage(test_cfg, do_artifacts=True, keep_artifacts=10, apply=False)
    assert len(report.artifacts) == 2
    stale_names = sorted(c.path.name for c in report.artifacts)
    assert stale_names == ["ask-0.md", "ask-1.md"]
    assert report.artifacts[0].cluster == "c1"
    assert report.total_bytes > 0
    assert report.bytes_deleted == 0


def test_gc_artifacts_apply(test_cfg):
    _make_dummy_artifacts(test_cfg, {"c1": [f"ask-{i}.md" for i in range(11)]})
    report = collect_garbage(test_cfg, do_artifacts=True, keep_artifacts=10, apply=True)
    assert len(report.artifacts) == 1
    # With 11 files (ask-0 ... ask-10), lex-sort descending puts ask-9 first
    # and ask-0 last. Slice[10:] = [ask-0]. So ask-0.md is the stale one.
    assert report.artifacts[0].path.name == "ask-0.md"
    assert report.bytes_deleted > 0
    assert report.files_deleted == 1
    assert not (test_cfg.research_hub_dir / "artifacts" / "c1" / "ask-0.md").exists()


def test_gc_all_combined_dry_run(test_cfg):
    now = int(time.time())
    _make_dummy_bundles(test_cfg, {"c1": ["20260101T000000Z", "20260102T000000Z", "20260103T000000Z"]})
    _make_dummy_debug_logs(test_cfg, [now - 40 * 86400])
    _make_dummy_artifacts(test_cfg, {"c1": [f"ask-{i}.md" for i in range(11)]})

    report = collect_garbage(
        test_cfg,
        do_bundles=True,
        do_debug_logs=True,
        do_artifacts=True,
        keep_bundles=2,
        debug_older_than_days=30,
        keep_artifacts=10,
        apply=False,
    )
    assert len(report.bundles) == 1
    assert len(report.debug_logs) == 1
    assert len(report.artifacts) == 1
    assert report.total_bytes > 0
    assert report.bytes_deleted == 0
    assert report.files_deleted == 0
    assert report.dirs_deleted == 0
