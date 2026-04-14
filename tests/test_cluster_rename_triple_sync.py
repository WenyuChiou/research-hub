from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from research_hub.clusters import ClusterRegistry


def _cfg(tmp_path: Path) -> SimpleNamespace:
    root = tmp_path / "vault"
    root.mkdir(parents=True)
    research_hub_dir = root / ".research_hub"
    research_hub_dir.mkdir()
    return SimpleNamespace(
        root=root,
        raw=root / "raw",
        hub=root / "hub",
        research_hub_dir=research_hub_dir,
        clusters_file=research_hub_dir / "clusters.yaml",
    )


class _ZoteroStub:
    def __init__(self) -> None:
        self.updated: list[str] = []

    def collection(self, key: str) -> dict:
        return {"key": key, "data": {"name": "Old Name"}}

    def update_collection(self, collection: dict) -> None:
        self.updated.append(collection["data"]["name"])


def test_rename_updates_clusters_yaml(tmp_path, monkeypatch):
    from research_hub import cli

    cfg = _cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Old Name", slug="agents")
    monkeypatch.setattr(cli, "get_config", lambda: cfg)

    assert cli.main(["clusters", "rename", "agents", "--name", "New Name"]) == 0
    assert ClusterRegistry(cfg.clusters_file).get("agents").name == "New Name"


def test_rename_syncs_zotero_collection_name(tmp_path, monkeypatch):
    from research_hub import cli

    cfg = _cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(
        query="agents", name="Old Name", slug="agents", zotero_collection_key="COLL1"
    )
    zot = _ZoteroStub()
    monkeypatch.setattr(cli, "get_config", lambda: cfg)
    monkeypatch.setattr("research_hub.zotero.client.get_client", lambda: zot)

    assert cli.main(["clusters", "rename", "agents", "--name", "New Name"]) == 0
    assert zot.updated == ["New Name"]


def test_rename_does_not_move_obsidian_folder(tmp_path, monkeypatch):
    from research_hub import cli

    cfg = _cfg(tmp_path)
    note_dir = cfg.raw / "agents"
    note_dir.mkdir(parents=True)
    (note_dir / "paper.md").write_text("---\ntopic_cluster: \"agents\"\n---\n", encoding="utf-8")
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Old Name", slug="agents")
    monkeypatch.setattr(cli, "get_config", lambda: cfg)

    assert cli.main(["clusters", "rename", "agents", "--name", "New Name"]) == 0
    assert (cfg.raw / "agents" / "paper.md").exists()
    assert not (cfg.raw / "new-name").exists()


def test_rename_updates_notebooklm_cache_display_name(tmp_path, monkeypatch):
    from research_hub import cli

    cfg = _cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Old Name", slug="agents")
    (cfg.research_hub_dir / "nlm_cache.json").write_text(
        json.dumps({"agents": {"notebook_name": "Old Name", "notebook_url": "https://example.com"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "get_config", lambda: cfg)

    assert cli.main(["clusters", "rename", "agents", "--name", "New Name"]) == 0

    cache = json.loads((cfg.research_hub_dir / "nlm_cache.json").read_text(encoding="utf-8"))
    assert cache["agents"]["notebook_name"] == "New Name"
