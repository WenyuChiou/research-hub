"""PR-A: `zotero gc` must never auto-delete (or one-keypress-delete) a
non-empty orphan collection.

Root cause: gc flagged ANY collection whose key is not a current cluster
binding as `orphan-from-vault`, including stale non-empty date-prefixed
duplicate collections holding real items — making the output falsely
imply a data-loss risk (although `delete_candidates` already hard-skips
non-empty collections, so none could actually be deleted). Fix:
non-empty orphans get the distinct `orphan-with-items(N)` reason, are
listed under a separate review-only section, are excluded from `--yes`,
and are never offered in the interactive prompt at all. `mark-kept
--all-orphans` still captures them (both orphan reasons).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from research_hub import cli
from research_hub.clusters import ClusterRegistry
from research_hub.zotero.gc import scan_zotero_for_gc


def _collection(key, name, *, num_items=0, num_collections=0,
                 date_added="2025-01-01T00:00:00Z") -> dict:
    return {
        "key": key,
        "data": {"key": key, "name": name, "dateAdded": date_added},
        "meta": {"numItems": num_items, "numCollections": num_collections},
    }


class _Zot:
    def __init__(self, collections):
        self._c = collections
        self.deleted: list[str] = []

    def collections(self, *, limit=200, start=0):
        return self._c[start:start + limit]

    def collection(self, key):
        return {"key": key, "data": {"key": key}}

    def delete_collection(self, coll):
        self.deleted.append(coll["key"])
        return {}


def _cfg(tmp_path: Path) -> SimpleNamespace:
    root = tmp_path / "vault"
    rh = root / ".research_hub"
    (root / "raw").mkdir(parents=True)
    rh.mkdir(parents=True)
    return SimpleNamespace(
        root=root, raw=root / "raw", hub=root / "hub",
        research_hub_dir=rh, clusters_file=rh / "clusters.yaml",
    )


# ---- classification ----

def test_empty_orphan_still_orphan_from_vault():
    """Regression: safe junk path unchanged — empty orphan keeps the
    `orphan-from-vault` reason so --yes can still GC real junk."""
    zot = _Zot([_collection("E1", "old-empty")])
    c = scan_zotero_for_gc(zot, set())
    assert len(c) == 1
    assert "orphan-from-vault" in c[0].reasons


def test_non_empty_orphan_gets_distinct_reason():
    zot = _Zot([_collection("N1", "20260518-flood-forecas", num_items=37)])
    c = scan_zotero_for_gc(zot, set())
    assert c[0].reasons == ["orphan-with-items(37)"]
    assert "orphan-from-vault" not in c[0].reasons


def test_orphan_with_only_subcollections_is_non_empty():
    zot = _Zot([_collection("S1", "parent", num_items=0, num_collections=3)])
    c = scan_zotero_for_gc(zot, set())
    assert c[0].reasons == ["orphan-with-items(0)"]
    assert "orphan-from-vault" not in c[0].reasons


# ---- --yes never deletes a non-empty orphan ----

def test_yes_excludes_non_empty_orphan(tmp_path, monkeypatch, capsys):
    cfg = _cfg(tmp_path)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create(query="live", name="Live", slug="live")
    registry.bind("live", zotero_collection_key="LIVE1", sync_zotero=False)
    zot = _Zot([
        _collection("DEL1", "test-topic"),                        # empty+test+orphan
        _collection("BIG1", "20260518-flood", num_items=37),      # non-empty orphan
    ])
    monkeypatch.setattr(cli, "get_config", lambda: cfg)
    monkeypatch.setattr("research_hub.zotero.client.get_client", lambda: zot)

    rc = cli.main(["zotero", "gc", "--apply", "--yes"])

    assert rc == 0
    assert zot.deleted == ["DEL1"]            # BIG1 never auto-deleted
    out = capsys.readouterr().out
    assert "Skipped 1 non-empty orphan" in out


# ---- interactive: non-empty orphan is never offered for deletion ----

def test_interactive_non_empty_never_offered(tmp_path, monkeypatch, capsys):
    """A non-empty orphan is listed for review only — never prompted,
    never deleted, regardless of what the user types. (delete_candidates
    also hard-skips it, so even a forced selection is refused.)"""
    cfg = _cfg(tmp_path)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create(query="live", name="Live", slug="live")
    registry.bind("live", zotero_collection_key="LIVE1", sync_zotero=False)
    zot = _Zot([_collection("BIG1", "20260518-flood", num_items=37)])
    monkeypatch.setattr(cli, "get_config", lambda: cfg)
    monkeypatch.setattr("research_hub.zotero.client.get_client", lambda: zot)
    # Even "yes" to every prompt cannot delete it (it is never prompted).
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: "yes")

    assert cli.main(["zotero", "gc", "--apply"]) == 0
    assert zot.deleted == []
    assert "Skipped 1 non-empty orphan" in capsys.readouterr().out


def test_mark_kept_all_orphans_captures_non_empty(tmp_path, monkeypatch):
    """Regression for the cross-site contract break: splitting the orphan
    reason must NOT make `mark-kept --all-orphans` silently drop
    non-empty orphans (the real-data collections users most want kept)."""
    from research_hub.zotero.gc import load_kept_keys

    cfg = _cfg(tmp_path)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create(query="live", name="Live", slug="live")
    registry.bind("live", zotero_collection_key="LIVE1", sync_zotero=False)
    zot = _Zot([
        _collection("EMPTY1", "old-empty"),                    # empty orphan
        _collection("BIG1", "20260518-flood", num_items=37),   # non-empty orphan
    ])
    monkeypatch.setattr(cli, "get_config", lambda: cfg)
    monkeypatch.setattr("research_hub.zotero.client.get_client", lambda: zot)

    assert cli.main(["zotero", "mark-kept", "--all-orphans"]) == 0
    kept = load_kept_keys(cfg.research_hub_dir)
    assert "BIG1" in kept          # the whole point — was silently dropped
    assert "EMPTY1" in kept


def test_interactive_empty_still_simple_yes(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create(query="live", name="Live", slug="live")
    registry.bind("live", zotero_collection_key="LIVE1", sync_zotero=False)
    zot = _Zot([_collection("DEL1", "test-topic")])  # empty+test+orphan
    monkeypatch.setattr(cli, "get_config", lambda: cfg)
    monkeypatch.setattr("research_hub.zotero.client.get_client", lambda: zot)
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: "y")

    assert cli.main(["zotero", "gc", "--apply"]) == 0
    assert zot.deleted == ["DEL1"]            # empty junk still 1-key delete
