from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from research_hub.clusters import ClusterRegistry
from research_hub.doctor import CheckResult
from research_hub.manifest import Manifest, new_entry
from research_hub.vault.sync import ClusterSyncStatus
from tests.test_pipeline import _configure, _paper


def _make_cfg(tmp_path: Path):
    root = tmp_path / "vault"
    raw = root / "raw"
    research_hub_dir = root / ".research_hub"
    raw.mkdir(parents=True)
    research_hub_dir.mkdir(parents=True)
    return SimpleNamespace(
        root=root,
        raw=raw,
        research_hub_dir=research_hub_dir,
        clusters_file=research_hub_dir / "clusters.yaml",
    )


def test_doctor_zotero_drift_warns_on_drifted_cluster(tmp_path, monkeypatch):
    from research_hub import doctor
    from research_hub.vault import sync as vault_sync

    cfg = _make_cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    monkeypatch.setattr("research_hub.zotero.client.get_client", lambda: object())
    monkeypatch.setattr(
        vault_sync,
        "compute_sync_status",
        lambda cluster, zot, raw: ClusterSyncStatus(
            cluster_slug=cluster.slug,
            obsidian_count=50,
            zotero_count=5,
            in_both=4,
        ),
    )

    result = doctor.check_cluster_zotero_drift(cfg)[0]
    assert result.status == "WARN"
    assert "agents" in result.details


def test_doctor_zotero_drift_ok_within_threshold(tmp_path, monkeypatch):
    from research_hub import doctor
    from research_hub.vault import sync as vault_sync

    cfg = _make_cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    monkeypatch.setattr("research_hub.zotero.client.get_client", lambda: object())
    monkeypatch.setattr(
        vault_sync,
        "compute_sync_status",
        lambda cluster, zot, raw: ClusterSyncStatus(
            cluster_slug=cluster.slug,
            obsidian_count=100,
            zotero_count=100,
            in_both=99,
        ),
    )

    result = doctor.check_cluster_zotero_drift(cfg)[0]
    assert result.status == "OK"


def test_doctor_test_pattern_warns_on_matching_slugs(tmp_path):
    from research_hub import doctor

    cfg = _make_cfg(tmp_path)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create(query="foo-test", name="Foo", slug="foo-test")
    registry.create(query="bar-scratch", name="Bar", slug="bar-scratch")
    registry.create(query="fresh-user-x", name="Fresh", slug="fresh-user-x")
    registry.create(query="real-cluster", name="Real", slug="real-cluster")

    result = doctor.check_cluster_test_pattern(cfg)
    assert result.status == "WARN"
    assert "foo-test" in result.details
    assert "bar-scratch" in result.details
    assert "fresh-user-x" in result.details
    assert "real-cluster" not in result.details


def test_doctor_collection_collision_warns_on_shared_key(tmp_path):
    from research_hub import doctor

    cfg = _make_cfg(tmp_path)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create(query="alpha", name="Alpha", slug="alpha")
    registry.create(query="beta", name="Beta", slug="beta")
    registry.bind("alpha", zotero_collection_key="ABC123", sync_zotero=False)
    registry.bind(
        "beta",
        zotero_collection_key="ABC123",
        sync_zotero=False,
        force_shared=True,
    )

    result = doctor.check_cluster_collection_collision(cfg)
    assert result.status == "WARN"
    assert "alpha" in result.details
    assert "beta" in result.details


def test_doctor_collection_collision_ok_when_unique(tmp_path):
    from research_hub import doctor

    cfg = _make_cfg(tmp_path)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create(query="alpha", name="Alpha", slug="alpha")
    registry.create(query="beta", name="Beta", slug="beta")
    registry.bind("alpha", zotero_collection_key="ABC123", sync_zotero=False)
    registry.bind("beta", zotero_collection_key="XYZ999", sync_zotero=False)

    result = doctor.check_cluster_collection_collision(cfg)
    assert result.status == "OK"


def test_doctor_manifest_orphan_cluster_info(tmp_path):
    from research_hub import doctor

    cfg = _make_cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="live", name="Live", slug="live")
    manifest = Manifest(cfg.research_hub_dir / "manifest.jsonl")
    manifest.append(new_entry(cluster="gone-cluster", query="q", action="new", title="Gone"))

    result = doctor.check_manifest_orphan_cluster(cfg)
    assert result.status == "INFO"
    assert "gone-cluster" in result.details


def test_import_folder_warns_without_with_zotero(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    vault_root = tmp_path / "vault"
    source_dir = tmp_path / "docs"
    source_dir.mkdir()
    (source_dir / "note.md").write_text("# Imported\n\nBody", encoding="utf-8")
    vault_root.mkdir()
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "knowledge_base": {
                    "root": str(vault_root),
                    "raw": str(vault_root / "raw"),
                    "hub": str(vault_root / "hub"),
                    "projects": str(vault_root / "projects"),
                    "logs": str(vault_root / "logs"),
                    "obsidian_graph": str(vault_root / ".obsidian" / "graph.json"),
                }
            }
        ),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    env["RESEARCH_HUB_ROOT"] = str(vault_root)
    env["RESEARCH_HUB_ALLOW_EXTERNAL_ROOT"] = "1"
    env["RESEARCH_HUB_CONFIG"] = str(config_path)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "research_hub",
            "import-folder",
            str(source_dir),
            "--cluster",
            "agents",
            "--yes",
        ],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0
    assert "WARNING: import-folder writes Obsidian only" in proc.stderr


def test_pipeline_no_zotero_banner_appears(tmp_path, monkeypatch, capsys):
    from research_hub import config as hub_config
    from research_hub import pipeline

    cfg = _configure(monkeypatch, tmp_path, default_collection="ABCD1234")
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    (cfg.root / "papers_input.json").write_text(
        json.dumps([_paper("Paper One", "paper-one", "10.1000/one")]),
        encoding="utf-8",
    )
    monkeypatch.setenv("RESEARCH_HUB_NO_ZOTERO", "1")
    monkeypatch.setattr(pipeline, "update_cluster_links", lambda *args, **kwargs: None)
    monkeypatch.setattr(pipeline, "_refresh_cluster_base", lambda *args, **kwargs: None)
    monkeypatch.setattr(pipeline.time, "sleep", lambda seconds: None)

    try:
        assert pipeline.run_pipeline(dry_run=False, cluster_slug="agents", verify=False) == 0
        err = capsys.readouterr().err
        assert "WARNING: Zotero writes DISABLED" in err
        assert "[no-zotero] wrote 1 obsidian notes; 0 zotero items" in err
    finally:
        hub_config._config = None
        hub_config._config_path = None


def test_clusters_audit_exits_1_on_drift(tmp_path, monkeypatch):
    from research_hub import cli

    cfg = _make_cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="audit", name="Audit", slug="audit")
    monkeypatch.setattr(cli, "get_config", lambda: cfg, raising=False)
    monkeypatch.setattr(cli, "_load_zotero_if_configured", lambda: object())
    monkeypatch.setattr(
        "research_hub.doctor.check_cluster_test_pattern",
        lambda cfg: CheckResult("cluster/test_pattern", "OK", "No test-pattern clusters found"),
    )
    monkeypatch.setattr(
        "research_hub.doctor.check_cluster_collection_collision",
        lambda cfg: CheckResult("cluster/collection_collision", "OK", "All unique"),
    )
    monkeypatch.setattr(
        "research_hub.doctor.check_manifest_orphan_cluster",
        lambda cfg: CheckResult("manifest/orphan_cluster", "OK", "All manifest cluster references resolve"),
    )
    monkeypatch.setattr(
        "research_hub.vault.sync.compute_sync_status",
        lambda cluster, zot, raw: ClusterSyncStatus(
            cluster_slug=cluster.slug,
            obsidian_count=10,
            zotero_count=5,
            in_both=4,
        ),
    )
    monkeypatch.setattr(
        "research_hub.doctor.check_cluster_zotero_drift",
        lambda cfg: [
            CheckResult(
                "cluster/zotero_drift",
                "WARN",
                "1 cluster(s) have Zotero drift > 5% threshold",
                details="audit: 6 obsidian-only papers (obsidian=10, in_both=4)",
            )
        ],
    )
    assert cli.main(["clusters", "audit"]) == 1

    monkeypatch.setattr(
        "research_hub.vault.sync.compute_sync_status",
        lambda cluster, zot, raw: ClusterSyncStatus(
            cluster_slug=cluster.slug,
            obsidian_count=10,
            zotero_count=10,
            in_both=10,
        ),
    )
    monkeypatch.setattr(
        "research_hub.doctor.check_cluster_zotero_drift",
        lambda cfg: [CheckResult("cluster/zotero_drift", "OK", "All clusters have Obsidian/Zotero counts within 5% drift")],
    )
    assert cli.main(["clusters", "audit"]) == 0
