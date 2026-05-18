from __future__ import annotations

from types import SimpleNamespace


class FakeWeb:
    def __init__(self, parent_key: str = "PARENTKEY"):
        self.created: list[list[dict]] = []
        self._parent_key = parent_key

    def collections(self, **kwargs):
        """Return a pre-existing "research-hub" parent so ensure_parent_collection
        resolves a deterministic key (PARENTKEY) without creating a new one."""
        return [
            {"data": {"key": self._parent_key, "name": "research-hub", "parentCollection": False}}
        ]

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
    # With zotero_parent_collection="research-hub" (default), the factory now
    # creates the cluster collection nested under the parent.  The assertion
    # below is intentionally loose on parentCollection type (truthy check only)
    # because the exact nesting invariant — cluster_payload["parentCollection"]
    # == "PARENTKEY" — is enforced by the stronger assertion in
    # tests/test_v0950_zotero_parent_collection.py::TestClusterCreationNesting.
    cluster_creates = [c for c in web.created if c and c[0].get("name") == "LLM Agents"]
    assert cluster_creates, f"cluster collection creation not found in {web.created}"
    # Assert the "LLM Agents" create call carries a truthy parentCollection
    # (the parent key resolved from FakeWeb.collections() → "PARENTKEY").
    cluster_payload = cluster_creates[0][0]
    assert cluster_payload.get("parentCollection") == "PARENTKEY", (
        f"LLM Agents collection must be nested; got: {cluster_payload}"
    )
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
