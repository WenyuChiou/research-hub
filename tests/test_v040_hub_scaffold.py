"""v0.40 cluster hub scaffolding tests."""

from __future__ import annotations

import json
import shutil
import os
from pathlib import Path

from research_hub.cli import main

from tests._persona_factory import make_persona_vault


def _set_isolated_root(tmp_path: Path):
    os.environ["RESEARCH_HUB_ROOT"] = str(tmp_path)
    os.environ["RESEARCH_HUB_ALLOW_EXTERNAL_ROOT"] = "1"
    config_path = tmp_path / "_v040_config.json"
    config_path.write_text(
        json.dumps({"knowledge_base": {"root": str(tmp_path)}}),
        encoding="utf-8",
    )
    os.environ["RESEARCH_HUB_CONFIG"] = str(config_path)
    import research_hub.config as cfg_mod

    cfg_mod._config = None
    cfg_mod._config_path = None
    return cfg_mod


def test_scaffold_cluster_hub_creates_full_structure(tmp_path):
    """scaffold_cluster_hub creates overview + crystals/ + memory.json from scratch."""
    from research_hub.topic import scaffold_cluster_hub

    cfg, info = make_persona_vault(tmp_path, persona="A")
    slug = info["cluster_slug"]
    shutil.rmtree(cfg.hub / slug, ignore_errors=True)
    summary = scaffold_cluster_hub(cfg, slug)
    assert summary["overview"] == "created"
    assert summary["crystals_dir"] == "created"
    assert summary["memory_json"] == "created"
    assert (cfg.hub / slug / "00_overview.md").exists()
    assert (cfg.hub / slug / "crystals").is_dir()
    assert (cfg.hub / slug / "memory.json").exists()


def test_scaffold_cluster_hub_idempotent(tmp_path):
    """Calling scaffold twice doesn't break existing 00_overview.md."""
    from research_hub.topic import scaffold_cluster_hub

    cfg, info = make_persona_vault(tmp_path, persona="A")
    slug = info["cluster_slug"]
    scaffold_cluster_hub(cfg, slug)
    overview_path = cfg.hub / slug / "00_overview.md"
    original_text = overview_path.read_text(encoding="utf-8")
    overview_path.write_text(original_text + "\n\nUSER EDITS HERE", encoding="utf-8")

    summary = scaffold_cluster_hub(cfg, slug)
    assert summary["overview"] == "exists"
    assert "USER EDITS HERE" in overview_path.read_text(encoding="utf-8")


def test_create_cluster_auto_scaffolds_hub(tmp_path):
    """ClusterRegistry.create() auto-creates hub/<slug>/ for new cluster."""
    cfg_mod = _set_isolated_root(tmp_path)

    from research_hub.clusters import ClusterRegistry

    cfg = cfg_mod.HubConfig()
    cfg.clusters_file.parent.mkdir(parents=True, exist_ok=True)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create("My Brand New Topic", slug="brand-new")

    assert (cfg.hub / "brand-new" / "00_overview.md").exists()
    assert (cfg.hub / "brand-new" / "crystals").is_dir()
    assert (cfg.hub / "brand-new" / "memory.json").exists()


def test_scaffold_missing_backfills_orphan_clusters(tmp_path, monkeypatch, capsys):
    """clusters scaffold-missing CLI scaffolds clusters that have no hub dir."""
    cfg_mod = _set_isolated_root(tmp_path)

    from research_hub.clusters import ClusterRegistry

    cfg = cfg_mod.HubConfig()
    cfg.clusters_file.parent.mkdir(parents=True, exist_ok=True)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create("Orphan", slug="orphan-cluster")
    shutil.rmtree(cfg.hub / "orphan-cluster", ignore_errors=True)
    assert not (cfg.hub / "orphan-cluster").exists()

    monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)
    assert main(["clusters", "scaffold-missing"]) == 0

    out = capsys.readouterr().out
    assert "Scaffolded 1 of 1 clusters" in out
    assert (cfg.hub / "orphan-cluster" / "00_overview.md").exists()


def test_memory_json_has_correct_initial_shape(tmp_path):
    """memory.json starts with empty entities/claims/methods arrays."""
    from research_hub.topic import scaffold_cluster_hub

    cfg, info = make_persona_vault(tmp_path, persona="A")
    slug = info["cluster_slug"]
    scaffold_cluster_hub(cfg, slug)

    memory_path = cfg.hub / slug / "memory.json"
    data = json.loads(memory_path.read_text(encoding="utf-8"))
    assert data["entities"] == []
    assert data["claims"] == []
    assert data["methods"] == []
    assert data["cluster_slug"] == slug


def test_scaffold_works_for_all_4_personas(tmp_path):
    """All 4 personas get the same hub scaffold structure on cluster creation."""
    from research_hub.clusters import ClusterRegistry
    from research_hub.topic import scaffold_cluster_hub

    for persona in ("A", "B", "C", "H"):
        sub = tmp_path / persona
        sub.mkdir()
        cfg, _ = make_persona_vault(sub, persona=persona)
        clusters = ClusterRegistry(cfg.clusters_file).list()
        assert clusters, f"persona {persona} has no clusters"
        slug = clusters[0].slug
        scaffold_cluster_hub(cfg, slug)
        assert (cfg.hub / slug / "00_overview.md").exists(), f"persona {persona}: no overview"
        assert (cfg.hub / slug / "memory.json").exists(), f"persona {persona}: no memory"
