"""Tests for Cluster.bind() and the new v0.4.0 Cluster fields."""

from __future__ import annotations

from research_hub.clusters import Cluster, ClusterRegistry


def test_cluster_has_new_v0_4_0_fields():
    cluster = Cluster(slug="test", name="Test")
    assert hasattr(cluster, "notebooklm_notebook_url")
    assert hasattr(cluster, "notebooklm_notebook_id")
    assert cluster.notebooklm_notebook_url == ""
    assert cluster.notebooklm_notebook_id == ""


def test_cluster_registry_bind_sets_fields(tmp_path):
    clusters_file = tmp_path / "clusters.yaml"
    registry = ClusterRegistry(clusters_file)
    registry.create(query="test query", name="Test Cluster")
    updated = registry.bind(
        slug="test-query",
        zotero_collection_key="ABCD1234",
        obsidian_subfolder="test-query",
        notebooklm_notebook="Test Notebook",
    )
    assert updated.zotero_collection_key == "ABCD1234"
    assert updated.obsidian_subfolder == "test-query"
    assert updated.notebooklm_notebook == "Test Notebook"

    registry_reloaded = ClusterRegistry(clusters_file)
    reloaded = registry_reloaded.get("test-query")
    assert reloaded is not None
    assert reloaded.zotero_collection_key == "ABCD1234"


def test_cluster_registry_bind_raises_on_missing_cluster(tmp_path):
    registry = ClusterRegistry(tmp_path / "clusters.yaml")
    try:
        registry.bind(slug="does-not-exist", zotero_collection_key="X")
    except ValueError as exc:
        assert "does-not-exist" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_cluster_registry_bind_partial_update(tmp_path):
    """bind() with only some params updates only those fields."""
    clusters_file = tmp_path / "clusters.yaml"
    registry = ClusterRegistry(clusters_file)
    cluster = registry.create(query="x y z", name="XYZ")
    registry.bind(slug=cluster.slug, zotero_collection_key="KEY1")
    registry.bind(slug=cluster.slug, notebooklm_notebook="Notebook XYZ")
    updated = ClusterRegistry(clusters_file).get(cluster.slug)
    assert updated is not None
    assert updated.zotero_collection_key == "KEY1"
    assert updated.notebooklm_notebook == "Notebook XYZ"
