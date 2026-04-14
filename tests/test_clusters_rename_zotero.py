from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from research_hub.clusters import ClusterRegistry


def _cfg(tmp_path: Path) -> SimpleNamespace:
    root = tmp_path / "vault"
    research_hub_dir = root / ".research_hub"
    root.mkdir(parents=True)
    research_hub_dir.mkdir(parents=True)
    return SimpleNamespace(
        root=root,
        raw=root / "raw",
        hub=root / "hub",
        research_hub_dir=research_hub_dir,
        clusters_file=research_hub_dir / "clusters.yaml",
    )


class _ZoteroStub:
    def __init__(self, name: str = "Old Name", *, fail: bool = False) -> None:
        self.name = name
        self.fail = fail
        self.updated = []

    def collection(self, key: str) -> dict:
        if self.fail:
            raise RuntimeError("boom")
        return {"key": key, "data": {"name": self.name}}

    def update_collection(self, collection: dict) -> None:
        self.updated.append(collection["data"]["name"])


def test_clusters_rename_updates_zotero_collection_when_bound(tmp_path, monkeypatch, capsys):
    from research_hub import cli

    cfg = _cfg(tmp_path)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create(query="agents", name="Old Name", slug="agents", zotero_collection_key="WNV9SWVA")
    zot = _ZoteroStub()
    monkeypatch.setattr(cli, "get_config", lambda: cfg)
    monkeypatch.setattr("research_hub.zotero.client.get_client", lambda: zot)

    rc = cli.main(["clusters", "rename", "agents", "--name", "New Name"])

    assert rc == 0
    assert zot.updated == ["New Name"]
    assert ClusterRegistry(cfg.clusters_file).get("agents").name == "New Name"
    assert "renamed Zotero collection WNV9SWVA" in capsys.readouterr().out


def test_clusters_rename_skips_zotero_when_no_collection_key(tmp_path, monkeypatch):
    from research_hub import cli

    cfg = _cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Old Name", slug="agents")
    monkeypatch.setattr(cli, "get_config", lambda: cfg)

    rc = cli.main(["clusters", "rename", "agents", "--name", "New Name"])

    assert rc == 0
    assert ClusterRegistry(cfg.clusters_file).get("agents").name == "New Name"


def test_clusters_rename_zotero_failure_does_not_rollback_yaml(tmp_path, monkeypatch, capsys):
    from research_hub import cli

    cfg = _cfg(tmp_path)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create(query="agents", name="Old Name", slug="agents", zotero_collection_key="WNV9SWVA")
    monkeypatch.setattr(cli, "get_config", lambda: cfg)
    monkeypatch.setattr("research_hub.zotero.client.get_client", lambda: _ZoteroStub(fail=True))

    rc = cli.main(["clusters", "rename", "agents", "--name", "New Name"])

    captured = capsys.readouterr()
    assert rc == 0
    assert "WARNING: Zotero rename failed: boom" in captured.err
    assert ClusterRegistry(cfg.clusters_file).get("agents").name == "New Name"


def test_clusters_rename_idempotent_when_already_renamed(tmp_path, monkeypatch, capsys):
    from research_hub import cli

    cfg = _cfg(tmp_path)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create(query="agents", name="Old Name", slug="agents", zotero_collection_key="WNV9SWVA")
    zot = _ZoteroStub(name="New Name")
    monkeypatch.setattr(cli, "get_config", lambda: cfg)
    monkeypatch.setattr("research_hub.zotero.client.get_client", lambda: zot)

    rc = cli.main(["clusters", "rename", "agents", "--name", "New Name"])

    assert rc == 0
    assert zot.updated == []
    assert "already named 'New Name'" in capsys.readouterr().out
