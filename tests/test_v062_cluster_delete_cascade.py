from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from research_hub.dedup import DedupHit, DedupIndex


def _cfg(tmp_path: Path) -> SimpleNamespace:
    root = tmp_path / "vault"
    raw = root / "raw"
    hub = root / "hub"
    rh = root / ".research_hub"
    raw.mkdir(parents=True)
    hub.mkdir(parents=True)
    rh.mkdir(parents=True)
    clusters_file = rh / "clusters.yaml"
    clusters_file.write_text(
        json.dumps({"clusters": {"agents": {"name": "Agents", "zotero_collection_key": "C1"}}}),
        encoding="utf-8",
    )
    return SimpleNamespace(raw=raw, hub=hub, research_hub_dir=rh, clusters_file=clusters_file)


class FakeZotero:
    def __init__(self, items: list[dict]):
        self.items = items
        self.updated: list[dict] = []
        self.deleted = False

    def collection_items(self, collection_key, start=0, limit=100, itemType=""):
        return self.items[start : start + limit]

    def item(self, key):
        return {"data": {"key": key, "collections": ["C1", "OTHER"]}}

    def update_item(self, data):
        self.updated.append(data.copy())
        return {}

    def delete_item(self, item):
        self.deleted = True
        return {}


def _seed_cluster(cfg, *, papers: int = 2, crystals: int = 1, memory: int = 2):
    cluster_raw = cfg.raw / "agents"
    cluster_raw.mkdir(parents=True, exist_ok=True)
    for idx in range(papers):
        (cluster_raw / f"paper-{idx}.md").write_text("---\ntopic_cluster: agents\n---\n", encoding="utf-8")
    cluster_hub = cfg.hub / "agents"
    (cluster_hub / "crystals").mkdir(parents=True, exist_ok=True)
    for idx in range(crystals):
        (cluster_hub / "crystals" / f"c{idx}.md").write_text("# crystal\n", encoding="utf-8")
    (cluster_hub / "memory.json").write_text(
        json.dumps({"entities": [1] * memory, "claims": [], "methods": [], "cluster_slug": "agents"}),
        encoding="utf-8",
    )
    index = DedupIndex()
    index.add(DedupHit(source="obsidian", doi="10.1/a", title="Paper", obsidian_path=str(cluster_raw / "paper-0.md")))
    index.save(cfg.research_hub_dir / "dedup_index.json")


def test_cascade_report_counts_obsidian_papers(tmp_path, monkeypatch):
    from research_hub.clusters import compute_cluster_cascade_report

    cfg = _cfg(tmp_path)
    _seed_cluster(cfg, papers=3)
    monkeypatch.setattr("research_hub.zotero.client.ZoteroDualClient", lambda: SimpleNamespace(web=FakeZotero([])))
    report = compute_cluster_cascade_report(cfg, "agents")
    assert report.obsidian_papers == 3


def test_cascade_report_counts_zotero_items(tmp_path, monkeypatch):
    from research_hub.clusters import compute_cluster_cascade_report

    cfg = _cfg(tmp_path)
    _seed_cluster(cfg)
    items = [{"key": "Z1", "data": {"key": "Z1"}}, {"key": "Z2", "data": {"key": "Z2"}}]
    monkeypatch.setattr("research_hub.zotero.client.ZoteroDualClient", lambda: SimpleNamespace(web=FakeZotero(items)))
    report = compute_cluster_cascade_report(cfg, "agents")
    assert report.zotero_items_in_collection == 2


def test_cascade_delete_never_trashes_zotero_items(tmp_path, monkeypatch):
    from research_hub.clusters import cascade_delete_cluster

    cfg = _cfg(tmp_path)
    _seed_cluster(cfg)
    zot = FakeZotero([{"key": "Z1", "data": {"key": "Z1"}}])
    monkeypatch.setattr("research_hub.zotero.client.ZoteroDualClient", lambda: SimpleNamespace(web=zot))
    cascade_delete_cluster(cfg, "agents", apply=True)
    assert zot.updated and zot.updated[0]["collections"] == ["OTHER"]
    assert zot.deleted is False


def test_cascade_delete_moves_obsidian_to_deleted_folder(tmp_path, monkeypatch):
    from research_hub.clusters import cascade_delete_cluster

    cfg = _cfg(tmp_path)
    _seed_cluster(cfg)
    monkeypatch.setattr("research_hub.zotero.client.ZoteroDualClient", lambda: SimpleNamespace(web=FakeZotero([])))
    cascade_delete_cluster(cfg, "agents", apply=True)
    assert not (cfg.raw / "agents").exists()
    assert (cfg.raw / "_deleted_agents").exists()


def test_cascade_delete_dryrun_does_not_modify_state(tmp_path, monkeypatch):
    from research_hub.clusters import cascade_delete_cluster

    cfg = _cfg(tmp_path)
    _seed_cluster(cfg)
    monkeypatch.setattr("research_hub.zotero.client.ZoteroDualClient", lambda: SimpleNamespace(web=FakeZotero([])))
    cascade_delete_cluster(cfg, "agents", apply=False)
    assert (cfg.raw / "agents").exists()
    assert (cfg.hub / "agents").exists()
