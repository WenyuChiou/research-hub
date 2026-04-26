"""v0.68.4 regression — auto pipeline previously POSTed a new Zotero
collection on every run that lacked a recorded cluster.zotero_collection_key.

Real incident: 283 empty orphan collections accumulated in the maintainer's
real Zotero library over months (`test-topic` x 112, `persona-a-test` x 81,
`Flood Risk` x 5, etc.) because tests + retries + manual collection deletes
left clusters with no recorded key, and the next run blindly POSTed.

Fix: `_ensure_zotero_collection` now probes Zotero for an existing
collection with the same name before creating a new one.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from research_hub.auto import _ensure_zotero_collection, AutoReport


def _make_web_with_existing(name: str, key: str):
    """Mock pyzotero web client whose `collections()` returns one entry
    matching `name`. spec= prevents MagicMock auto-creating a `.web`
    attribute (the production code does `getattr(zot, 'web', None) or zot`
    to unwrap the dual-client wrapper; without spec, MagicMock auto-creates
    the inner `.web` and the unwrap picks that instead of the mock)."""
    web = MagicMock(spec=["collections", "create_collections"])
    web.collections.return_value = [{"data": {"key": key, "name": name}}]
    return web


def _make_web_with_no_match():
    web = MagicMock(spec=["collections", "create_collections"])
    web.collections.return_value = []
    web.create_collections.return_value = {
        "successful": {"0": {"key": "NEWKEY1", "data": {"key": "NEWKEY1"}}}
    }
    return web


def test_ensure_zotero_collection_reuses_existing_by_name(monkeypatch):
    web = _make_web_with_existing(name="My Cluster", key="EXISTING")
    monkeypatch.setattr("research_hub.zotero.client.get_client", lambda: web)

    cluster = SimpleNamespace(name="My Cluster", zotero_collection_key=None)
    registry = MagicMock()
    report = AutoReport(cluster_created=False, cluster_slug="my-cluster")

    _ensure_zotero_collection(registry, cluster, "my-cluster", report, print_progress=False)

    assert cluster.zotero_collection_key == "EXISTING"
    web.create_collections.assert_not_called()  # this is the regression we are
                                                # preventing — must NOT create
                                                # a duplicate when name matches
    registry.save.assert_called_once()
    assert report.steps[-1].name == "zotero.bind"
    assert report.steps[-1].ok is True
    assert "reused" in report.steps[-1].detail.lower()


def test_ensure_zotero_collection_creates_when_no_match(monkeypatch):
    web = _make_web_with_no_match()
    monkeypatch.setattr("research_hub.zotero.client.get_client", lambda: web)

    cluster = SimpleNamespace(name="Brand New Topic", zotero_collection_key=None)
    registry = MagicMock()
    report = AutoReport(cluster_created=False, cluster_slug="brand-new-topic")

    _ensure_zotero_collection(registry, cluster, "brand-new-topic", report, print_progress=False)

    assert cluster.zotero_collection_key == "NEWKEY1"
    web.create_collections.assert_called_once()
    args = web.create_collections.call_args[0][0]
    assert args == [{"name": "Brand New Topic"}]


def test_ensure_zotero_collection_does_not_create_on_pagination_match(monkeypatch):
    """Match must be found even if it's on a later page (collections > 100)."""
    web = MagicMock(spec=["collections", "create_collections"])
    page1 = [{"data": {"key": f"K{i}", "name": f"unrelated-{i}"}} for i in range(100)]
    page2 = [{"data": {"key": "MATCH", "name": "Target"}}]
    web.collections.side_effect = [page1, page2]
    monkeypatch.setattr("research_hub.zotero.client.get_client", lambda: web)

    cluster = SimpleNamespace(name="Target", zotero_collection_key=None)
    registry = MagicMock()
    report = AutoReport(cluster_created=False, cluster_slug="target")

    _ensure_zotero_collection(registry, cluster, "target", report, print_progress=False)

    assert cluster.zotero_collection_key == "MATCH"
    web.create_collections.assert_not_called()


def test_ensure_zotero_collection_skips_when_no_zotero_env(monkeypatch):
    monkeypatch.setenv("RESEARCH_HUB_NO_ZOTERO", "1")
    cluster = SimpleNamespace(name="X", zotero_collection_key=None)
    registry = MagicMock()
    report = AutoReport(cluster_created=False, cluster_slug="x")

    _ensure_zotero_collection(registry, cluster, "x", report, print_progress=False)

    assert cluster.zotero_collection_key is None
    registry.save.assert_not_called()
