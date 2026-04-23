from __future__ import annotations

from types import SimpleNamespace


class FakeWeb:
    def __init__(self):
        self.created: list[list[dict]] = []

    def create_collections(self, payload):
        self.created.append(payload)
        return {"successful": {"0": {"key": "COLLNEW"}}}


def test_cluster_create_auto_creates_zotero_collection_when_missing(tmp_path, monkeypatch):
    # Import inside the test: an earlier test in the suite may have popped
    # research_hub.clusters from sys.modules (see conftest.py
    # _reset_research_hub_modules), and a top-level import here would still
    # reference the old module while monkeypatch.setattr targets the new one.
    from research_hub.clusters import ClusterRegistry

    path = tmp_path / ".research_hub" / "clusters.yaml"
    path.parent.mkdir()
    web = FakeWeb()
    cfg = SimpleNamespace(clusters_file=path, no_zotero=False, zotero_api_key="K", zotero_library_id="LID")
    monkeypatch.setattr("research_hub.clusters.get_config", lambda: cfg)
    monkeypatch.setattr(
        "research_hub.zotero.client.ZoteroDualClient",
        lambda: SimpleNamespace(web=web),
    )

    cluster = ClusterRegistry(path).create(query="llm agents", name="LLM Agents")

    assert cluster.zotero_collection_key == "COLLNEW"
    assert web.created == [[{"name": "LLM Agents"}]]
    assert ClusterRegistry(path).get(cluster.slug).zotero_collection_key == "COLLNEW"


def test_cluster_create_skips_when_no_zotero(tmp_path, monkeypatch):
    from research_hub.clusters import ClusterRegistry

    path = tmp_path / ".research_hub" / "clusters.yaml"
    path.parent.mkdir()
    web = FakeWeb()
    cfg = SimpleNamespace(clusters_file=path, no_zotero=True)
    monkeypatch.setattr("research_hub.clusters.get_config", lambda: cfg)
    monkeypatch.setattr(
        "research_hub.zotero.client.ZoteroDualClient",
        lambda: SimpleNamespace(web=web),
    )

    cluster = ClusterRegistry(path).create(query="llm agents", name="LLM Agents")

    assert cluster.zotero_collection_key is None
    assert web.created == []
