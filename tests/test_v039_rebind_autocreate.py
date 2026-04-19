"""v0.39 rebind auto-create-from-folder tests."""

from __future__ import annotations

from research_hub.clusters import ClusterRegistry
from research_hub.cluster_rebind import _propose_new_clusters_from_orphans, apply_rebind, emit_rebind_prompt
from tests._persona_factory import make_persona_vault


def _seed_orphans(cfg, folder, count, tag="research/topic-x"):
    subdir = cfg.raw / folder
    subdir.mkdir(exist_ok=True)
    for i in range(count):
        (subdir / f"orphan-{i}.md").write_text(
            f"---\ntitle: Orphan {i}\ntags: [{tag}]\n---\nbody",
            encoding="utf-8",
        )


def test_folder_with_6_orphans_proposes_new_cluster(tmp_path):
    cfg, _ = make_persona_vault(tmp_path, persona="A")
    _seed_orphans(cfg, "Behavioral-Theory", 6, tag="research/behavior")
    report = emit_rebind_prompt(cfg)
    assert "new_cluster_proposals" in report
    assert "behavioral-theory" in report.lower()


def test_folder_with_3_orphans_does_not_propose_new(tmp_path):
    cfg, _ = make_persona_vault(tmp_path, persona="A")
    _seed_orphans(cfg, "Tiny-Folder", 3)
    report = emit_rebind_prompt(cfg)
    assert "new_cluster_proposals" not in report
    assert "tiny-folder" not in report.lower()


def test_auto_create_slug_derives_from_folder_name(tmp_path):
    cfg, _ = make_persona_vault(tmp_path, persona="A")
    _seed_orphans(cfg, "Behavioral-Theory", 6)
    proposals = _propose_new_clusters_from_orphans(
        cfg,
        ClusterRegistry(cfg.clusters_file),
        {"Behavioral-Theory": list((cfg.raw / "Behavioral-Theory").glob("*.md"))},
    )
    assert len(proposals) == 1
    assert proposals[0].slug == "behavioral-theory"
    assert proposals[0].name == "Behavioral Theory"


def test_apply_without_auto_create_new_skips_new_clusters(tmp_path):
    cfg, _ = make_persona_vault(tmp_path, persona="A")
    _seed_orphans(cfg, "Behavioral-Theory", 6)
    report_path = tmp_path / "rebind.md"
    report_path.write_text(emit_rebind_prompt(cfg), encoding="utf-8")
    apply_rebind(cfg, report_path, dry_run=False, auto_create_new=False)
    assert (cfg.raw / "Behavioral-Theory" / "orphan-0.md").exists()
    assert "behavioral-theory" not in {cluster.slug for cluster in ClusterRegistry(cfg.clusters_file).list()}


def test_apply_with_auto_create_new_creates_cluster_and_moves(tmp_path):
    cfg, _ = make_persona_vault(tmp_path, persona="A")
    _seed_orphans(cfg, "Behavioral-Theory", 6)
    report_path = tmp_path / "rebind.md"
    report_path.write_text(emit_rebind_prompt(cfg), encoding="utf-8")
    result = apply_rebind(cfg, report_path, dry_run=False, auto_create_new=True)
    cluster_slugs = [cluster.slug for cluster in ClusterRegistry(cfg.clusters_file).list()]
    assert "behavioral-theory" in cluster_slugs
    moved_files = list((cfg.raw / "behavioral-theory").glob("*.md"))
    assert len(moved_files) == 6
    assert len(result.moved) == 6
