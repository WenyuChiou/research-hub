"""v0.37 cluster integrity: doctor checks + rebind command."""

from __future__ import annotations

import json

from tests._persona_factory import make_persona_vault


def test_check_cluster_missing_dir_passes_for_clean_vault(tmp_path):
    from research_hub.doctor import check_cluster_missing_dir

    cfg, _ = make_persona_vault(tmp_path, persona="A")
    result = check_cluster_missing_dir(cfg)
    assert result.status == "OK"


def test_check_cluster_missing_dir_fails_when_dir_absent(tmp_path):
    from research_hub.clusters import ClusterRegistry
    from research_hub.doctor import check_cluster_missing_dir

    cfg, _ = make_persona_vault(tmp_path, persona="A")
    reg = ClusterRegistry(cfg.clusters_file)
    cluster = reg.list()[0]
    reg.bind(cluster.slug, obsidian_subfolder="nonexistent-dir-12345")
    result = check_cluster_missing_dir(cfg)
    assert result.status == "FAIL"
    assert "nonexistent-dir-12345" in (result.details or result.message)


def test_check_cluster_orphan_papers_detects_unbound_folder(tmp_path):
    from research_hub.doctor import check_cluster_orphan_papers

    cfg, _ = make_persona_vault(tmp_path, persona="A")
    orphan_dir = cfg.raw / "random-folder"
    orphan_dir.mkdir()
    (orphan_dir / "orphan-paper.md").write_text("---\ntitle: Orphan\n---\nbody", encoding="utf-8")
    result = check_cluster_orphan_papers(cfg)
    assert result.status == "WARN"
    assert "random-folder" in (result.details or result.message)


def test_check_cluster_empty_warns_for_zero_papers(tmp_path):
    from research_hub.clusters import ClusterRegistry
    from research_hub.doctor import check_cluster_empty

    cfg, _ = make_persona_vault(tmp_path, persona="A")
    reg = ClusterRegistry(cfg.clusters_file)
    reg.create(slug="empty-cluster", name="Empty Cluster", query="empty cluster", seed_keywords=["empty"])
    (cfg.raw / "empty-cluster").mkdir(exist_ok=True)
    result = check_cluster_empty(cfg)
    assert result.status == "WARN"
    assert "empty-cluster" in (result.details or result.message)


def test_check_cluster_cross_tagged_detects_mismatch(tmp_path):
    from research_hub.clusters import ClusterRegistry
    from research_hub.doctor import check_cluster_cross_tagged

    cfg, info = make_persona_vault(tmp_path, persona="A")
    reg = ClusterRegistry(cfg.clusters_file)
    current_slug = info["cluster_slug"]
    reg.create(slug="cluster-b-test", name="Cluster B", query="cluster b", seed_keywords=["b"])
    paper = cfg.raw / current_slug / "mistagged.md"
    paper.write_text("---\ntitle: x\ncluster: cluster-b-test\n---\nbody", encoding="utf-8")
    result = check_cluster_cross_tagged(cfg)
    assert result.status == "WARN"
    assert "mistagged" in (result.details or result.message)


def test_check_quote_orphan_detects_quote_on_unbound_paper(tmp_path):
    from research_hub.doctor import check_quote_orphan

    cfg, _ = make_persona_vault(tmp_path, persona="C")
    quote_dir = cfg.root / ".research_hub" / "quotes"
    quote_dir.mkdir(parents=True, exist_ok=True)
    (quote_dir / "ghost-paper.json").write_text(
        json.dumps({"paper_slug": "ghost-paper", "text": "..."}),
        encoding="utf-8",
    )
    result = check_quote_orphan(cfg)
    assert result.status == "WARN"
    assert "ghost-paper" in (result.details or result.message)


def test_emit_rebind_prompt_proposes_high_confidence_for_explicit_cluster(tmp_path):
    from research_hub.cluster_rebind import emit_rebind_prompt

    cfg, info = make_persona_vault(tmp_path, persona="A")
    target_slug = info["cluster_slug"]
    orphan_dir = cfg.raw / "stranded"
    orphan_dir.mkdir()
    (orphan_dir / "knows-its-home.md").write_text(
        f"---\ntitle: home\ncluster: {target_slug}\n---\nbody",
        encoding="utf-8",
    )
    report = emit_rebind_prompt(cfg)
    assert "knows-its-home.md" in report
    assert target_slug in report
    assert '"confidence": "high"' in report


def test_emit_rebind_prompt_skips_already_bound_folders(tmp_path):
    from research_hub.cluster_rebind import emit_rebind_prompt

    cfg, _ = make_persona_vault(tmp_path, persona="A")
    report = emit_rebind_prompt(cfg)
    assert "Proposed moves: 0" in report or "No moves proposed" in report


def test_apply_rebind_dry_run_does_not_move_files(tmp_path):
    from research_hub.cluster_rebind import apply_rebind, emit_rebind_prompt

    cfg, info = make_persona_vault(tmp_path, persona="A")
    orphan_dir = cfg.raw / "stranded"
    orphan_dir.mkdir()
    src = orphan_dir / "wandering.md"
    src.write_text(
        f"---\ntitle: x\ncluster: {info['cluster_slug']}\n---\nbody",
        encoding="utf-8",
    )

    report_path = tmp_path / "rebind.md"
    report_path.write_text(emit_rebind_prompt(cfg), encoding="utf-8")
    result = apply_rebind(cfg, report_path, dry_run=True)
    assert src.exists()
    assert len(result.moved) == 0
    assert result.log_path


def test_apply_rebind_actually_moves_with_no_dry_run(tmp_path):
    from research_hub.cluster_rebind import apply_rebind, emit_rebind_prompt

    cfg, info = make_persona_vault(tmp_path, persona="A")
    orphan_dir = cfg.raw / "stranded"
    orphan_dir.mkdir()
    src = orphan_dir / "moving.md"
    src.write_text(
        f"---\ntitle: x\ncluster: {info['cluster_slug']}\n---\nbody",
        encoding="utf-8",
    )

    report_path = tmp_path / "rebind.md"
    report_path.write_text(emit_rebind_prompt(cfg), encoding="utf-8")
    result = apply_rebind(cfg, report_path, dry_run=False)
    assert not src.exists()
    assert (cfg.raw / info["cluster_slug"] / "moving.md").exists()
    assert len(result.moved) == 1


def test_apply_rebind_skips_when_dst_exists(tmp_path):
    from research_hub.cluster_rebind import apply_rebind, emit_rebind_prompt

    cfg, info = make_persona_vault(tmp_path, persona="A")
    orphan_dir = cfg.raw / "stranded"
    orphan_dir.mkdir()
    src = orphan_dir / "duplicate.md"
    src.write_text(
        f"---\ntitle: x\ncluster: {info['cluster_slug']}\n---\nbody",
        encoding="utf-8",
    )
    (cfg.raw / info["cluster_slug"] / "duplicate.md").write_text("existing", encoding="utf-8")

    report_path = tmp_path / "rebind.md"
    report_path.write_text(emit_rebind_prompt(cfg), encoding="utf-8")
    result = apply_rebind(cfg, report_path, dry_run=False)
    assert src.exists()
    assert len(result.skipped) >= 1


def test_check_cluster_orphan_papers_ignores_pdfs_subdir(tmp_path):
    from research_hub.doctor import check_cluster_orphan_papers

    cfg, _ = make_persona_vault(tmp_path, persona="A")
    pdfs_dir = cfg.raw / "pdfs"
    pdfs_dir.mkdir(exist_ok=True)
    (pdfs_dir / "some.pdf").write_bytes(b"%PDF-1.0")
    result = check_cluster_orphan_papers(cfg)
    assert result.status == "OK"
