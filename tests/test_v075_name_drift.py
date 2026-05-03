from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from research_hub.clusters import ClusterRegistry


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


class _ZoteroStub:
    def __init__(self, name: str) -> None:
        self.name = name
        self.updated: list[dict] = []

    def collection(self, key: str) -> dict:
        return {"key": key, "version": 7, "data": {"name": self.name}}

    def update_collection(self, payload: dict) -> dict:
        self.updated.append(payload.copy())
        self.name = payload["name"]
        return payload


def test_check_cluster_name_drift_warns_on_mismatch(tmp_path, monkeypatch):
    from research_hub import doctor

    cfg = _cfg(tmp_path)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create(query="agents", name="Vault Name", slug="agents")
    registry.bind("agents", zotero_collection_key="COLL1", sync_zotero=False)
    monkeypatch.setattr("research_hub.zotero.client.get_client", lambda: _ZoteroStub("Zotero Name"))

    result = doctor.check_cluster_name_drift(cfg)

    assert result.status == "WARN"
    assert "agents" in result.details
    assert "Vault Name" in result.details
    assert "Zotero Name" in result.details


def test_check_cluster_name_drift_ok_when_aligned(tmp_path, monkeypatch):
    from research_hub import doctor

    cfg = _cfg(tmp_path)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create(query="agents", name="Shared Name", slug="agents")
    registry.bind("agents", zotero_collection_key="COLL1", sync_zotero=False)
    monkeypatch.setattr("research_hub.zotero.client.get_client", lambda: _ZoteroStub("Shared Name"))

    result = doctor.check_cluster_name_drift(cfg)

    assert result.status == "OK"


def test_bind_syncs_zotero_name_by_default(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create(query="agents", name="Vault Name", slug="agents")
    zot = _ZoteroStub("Old Name")
    monkeypatch.setattr(
        "research_hub.zotero.client.ZoteroDualClient",
        lambda: SimpleNamespace(web=zot),
    )

    registry.bind("agents", zotero_collection_key="COLL1")

    assert zot.updated == [{"key": "COLL1", "version": 7, "name": "Vault Name"}]


def test_bind_can_skip_zotero_name_sync(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create(query="agents", name="Vault Name", slug="agents")
    zot = _ZoteroStub("Old Name")
    monkeypatch.setattr(
        "research_hub.zotero.client.ZoteroDualClient",
        lambda: SimpleNamespace(web=zot),
    )

    registry.bind("agents", zotero_collection_key="COLL1", sync_zotero=False)

    assert zot.updated == []


def test_clusters_sync_names_can_apply_zotero_to_vault(tmp_path, monkeypatch):
    from research_hub import cli

    cfg = _cfg(tmp_path)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create(query="agents", name="Vault Name", slug="agents")
    registry.bind("agents", zotero_collection_key="COLL1", sync_zotero=False)
    monkeypatch.setattr(cli, "get_config", lambda: cfg)
    monkeypatch.setattr("research_hub.zotero.client.get_client", lambda: _ZoteroStub("Zotero Name"))

    rc = cli.main(
        [
            "clusters",
            "sync-names",
            "--cluster",
            "agents",
            "--direction",
            "zotero-to-vault",
            "--apply",
        ]
    )

    assert rc == 0
    assert ClusterRegistry(cfg.clusters_file).get("agents").name == "Zotero Name"
