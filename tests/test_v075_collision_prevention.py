from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from research_hub.auto import AutoReport, _ensure_zotero_collection
from research_hub.clusters import ClusterRegistry, CollisionError


def _cfg(tmp_path: Path) -> SimpleNamespace:
    root = tmp_path / "vault"
    raw = root / "raw"
    rh = root / ".research_hub"
    raw.mkdir(parents=True)
    rh.mkdir(parents=True)
    return SimpleNamespace(
        root=root,
        raw=raw,
        hub=root / "hub",
        research_hub_dir=rh,
        clusters_file=rh / "clusters.yaml",
    )


def test_bind_raises_collision_error_on_duplicate_key(tmp_path):
    cfg = _cfg(tmp_path)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create(query="alpha", name="Alpha", slug="alpha")
    registry.create(query="beta", name="Beta", slug="beta")
    registry.bind("alpha", zotero_collection_key="SHARED1", sync_zotero=False)

    with pytest.raises(CollisionError):
        registry.bind("beta", zotero_collection_key="SHARED1", sync_zotero=False)


def test_bind_allows_duplicate_key_with_force_shared(tmp_path):
    cfg = _cfg(tmp_path)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create(query="alpha", name="Alpha", slug="alpha")
    registry.create(query="beta", name="Beta", slug="beta")
    registry.bind("alpha", zotero_collection_key="SHARED1", sync_zotero=False)

    cluster = registry.bind(
        "beta",
        zotero_collection_key="SHARED1",
        sync_zotero=False,
        force_shared=True,
    )

    assert cluster.zotero_collection_key == "SHARED1"


def test_auto_collection_reuse_skips_existing_key_already_bound_elsewhere(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create(query="alpha", name="Existing Topic", slug="alpha")
    registry.bind("alpha", zotero_collection_key="SHARED1", sync_zotero=False)
    registry.create(query="beta", name="Existing Topic", slug="beta")
    cluster = registry.get("beta")
    assert cluster is not None

    web = MagicMock(spec=["collections", "create_collections"])
    web.collections.return_value = [{"data": {"key": "SHARED1", "name": "Existing Topic"}}]
    web.create_collections.return_value = {
        "successful": {"0": {"key": "NEWKEY1", "data": {"key": "NEWKEY1"}}}
    }
    monkeypatch.setattr("research_hub.zotero.client.get_client", lambda: web)
    report = AutoReport(cluster_slug="beta", cluster_created=False)

    _ensure_zotero_collection(registry, cluster, "beta", report, print_progress=False)

    assert cluster.zotero_collection_key == "NEWKEY1"
    web.create_collections.assert_called_once()


def test_resolve_collision_new_creates_fresh_collection_and_retags_matching_items(tmp_path, monkeypatch):
    from research_hub import cli

    cfg = _cfg(tmp_path)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create(query="alpha", name="Alpha", slug="alpha")
    registry.create(query="beta", name="Beta", slug="beta")
    registry.bind("alpha", zotero_collection_key="SHARED1", sync_zotero=False, force_shared=True)
    registry.bind("beta", zotero_collection_key="SHARED1", sync_zotero=False, force_shared=True)
    note_dir = cfg.raw / "beta"
    note_dir.mkdir(parents=True)
    (note_dir / "paper.md").write_text(
        "---\n"
        'doi: "10.1000/one"\n'
        "topic_cluster: beta\n"
        "---\n",
        encoding="utf-8",
    )

    class _Zot:
        def __init__(self) -> None:
            self.updated: list[dict] = []

        def create_collections(self, payload):
            assert payload == [{"name": "Beta", "parentCollection": False}]
            return {"successful": {"0": {"key": "NEWKEY1"}}}

        def collection_items(self, collection_key, start=0, limit=100, itemType=""):
            assert collection_key == "SHARED1"
            return [{"key": "ITEM1", "data": {"DOI": "10.1000/one", "collections": ["SHARED1"]}}]

        def item(self, key):
            assert key == "ITEM1"
            return {"data": {"key": key, "DOI": "10.1000/one", "collections": ["SHARED1"]}}

        def update_item(self, data):
            self.updated.append(data.copy())
            return {}

    monkeypatch.setattr(cli, "get_config", lambda: cfg)
    monkeypatch.setattr("research_hub.zotero.client.get_client", lambda: _Zot())

    rc = cli.main(["clusters", "resolve-collision", "beta", "--new", "--apply"])

    assert rc == 0
    assert ClusterRegistry(cfg.clusters_file).get("beta").zotero_collection_key == "NEWKEY1"
