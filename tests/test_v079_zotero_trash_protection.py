from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from research_hub.clusters import ClusterRegistry


def _cfg(tmp_path: Path) -> SimpleNamespace:
    root = tmp_path / "vault"
    raw = root / "raw"
    hub = root / "hub"
    research_hub_dir = root / ".research_hub"
    raw.mkdir(parents=True)
    hub.mkdir(parents=True)
    research_hub_dir.mkdir(parents=True)
    return SimpleNamespace(
        root=root,
        raw=raw,
        hub=hub,
        research_hub_dir=research_hub_dir,
        clusters_file=research_hub_dir / "clusters.yaml",
    )


def test_doctor_zotero_trashed_check_finds_trashed(tmp_path, monkeypatch):
    from research_hub import doctor

    cfg = _cfg(tmp_path)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create(query="alpha", name="Alpha", slug="alpha")
    registry.bind("alpha", zotero_collection_key="TRASH1", sync_zotero=False)

    zot = MagicMock()
    zot.collection.side_effect = lambda key: {
        "data": {"deleted": 1 if key == "TRASH1" else 0, "name": f"name-{key}"}
    }
    monkeypatch.setattr("research_hub.zotero.client.get_client", lambda: zot)

    result = doctor.check_cluster_zotero_trashed(cfg)

    assert result.status == "WARN"
    assert "trashed" in result.message.lower()
    assert "alpha: TRASH1" in result.details


def test_doctor_zotero_trashed_check_ok(tmp_path, monkeypatch):
    from research_hub import doctor

    cfg = _cfg(tmp_path)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create(query="alpha", name="Alpha", slug="alpha")
    registry.bind("alpha", zotero_collection_key="LIVE1", sync_zotero=False)

    zot = MagicMock()
    zot.collection.return_value = {"data": {"deleted": 0, "name": "name-LIVE1"}}
    monkeypatch.setattr("research_hub.zotero.client.get_client", lambda: zot)

    result = doctor.check_cluster_zotero_trashed(cfg)

    assert result.status == "OK"


def test_cascade_delete_refuses_to_delete_shared_key(tmp_path, monkeypatch, capsys):
    from research_hub.clusters import cascade_delete_cluster

    cfg = _cfg(tmp_path)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create(query="alpha", name="Alpha", slug="alpha")
    registry.create(query="beta", name="Beta", slug="beta")
    registry.bind("alpha", zotero_collection_key="SHARED1", sync_zotero=False)
    registry.bind("beta", zotero_collection_key="SHARED1", sync_zotero=False, force_shared=True)

    zot = MagicMock()
    zot.collection_items.return_value = []
    dual = SimpleNamespace(web=zot, delete_collection=MagicMock())
    monkeypatch.setattr("research_hub.zotero.client.ZoteroDualClient", lambda: dual)

    cascade_delete_cluster(cfg, "alpha", apply=True, delete_zotero_collection=True)

    assert dual.delete_collection.call_count == 0
    assert (
        "refusing to delete Zotero coll SHARED1 because it is still bound by: beta"
        in capsys.readouterr().err
    )


def test_clusters_restore_zotero_coll_apply(tmp_path, monkeypatch):
    from research_hub import cli

    cfg = _cfg(tmp_path)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create(query="alpha", name="Alpha", slug="alpha")
    registry.bind("alpha", zotero_collection_key="TRASH1", sync_zotero=False)

    class _Zot:
        def __init__(self) -> None:
            self.updated: list[dict] = []

        def collection(self, key: str) -> dict:
            return {"key": key, "version": 9, "data": {"key": key, "name": "Alpha", "deleted": 1}}

        def update_collection(self, payload: dict) -> dict:
            self.updated.append(payload.copy())
            return payload

    zot = _Zot()
    monkeypatch.setattr(cli, "get_config", lambda: cfg)
    monkeypatch.setattr(
        "research_hub.zotero.client.ZoteroDualClient",
        lambda: SimpleNamespace(web=zot),
    )

    rc = cli.main(["clusters", "restore-zotero-coll", "--apply"])

    assert rc == 0
    assert zot.updated == [{"key": "TRASH1", "name": "Alpha", "deleted": 0, "version": 9}]


def test_resolve_collision_does_not_call_delete_or_trash(tmp_path, monkeypatch):
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
            self.updated_items: list[dict] = []
            self.delete_collection = MagicMock()
            self.update_collection = MagicMock()

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
            self.updated_items.append(data.copy())
            return {}

    zot = _Zot()
    monkeypatch.setattr(cli, "get_config", lambda: cfg)
    monkeypatch.setattr("research_hub.zotero.client.get_client", lambda: zot)

    rc = cli.main(["clusters", "resolve-collision", "beta", "--new", "--apply"])

    assert rc == 0
    assert ClusterRegistry(cfg.clusters_file).get("beta").zotero_collection_key == "NEWKEY1"
    assert zot.delete_collection.call_count == 0
    assert zot.update_collection.call_count == 0
