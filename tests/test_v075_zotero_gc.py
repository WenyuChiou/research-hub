from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from research_hub.clusters import ClusterRegistry
from research_hub.zotero.gc import GCCandidate, delete_candidates, scan_zotero_for_gc


def _collection(
    key: str,
    name: str,
    *,
    num_items: int = 0,
    num_collections: int = 0,
    date_added: str = "2025-01-01T00:00:00Z",
) -> dict:
    return {
        "key": key,
        "data": {"key": key, "name": name, "dateAdded": date_added},
        "meta": {"numItems": num_items, "numCollections": num_collections},
    }


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


class _ZotCollections:
    def __init__(self, collections: list[dict]) -> None:
        self._collections = collections
        self.deleted: list[str] = []

    def collections(self, *, limit=200, start=0):
        return self._collections[start : start + limit]

    def collection(self, key: str) -> dict:
        return {"key": key, "data": {"key": key}}

    def delete_collection(self, coll: dict) -> dict:
        self.deleted.append(coll["key"])
        return {}


def test_scan_zotero_for_gc_flags_old_empty_test_orphan_collection():
    zot = _ZotCollections([_collection("A1", "test-topic")])

    candidates = scan_zotero_for_gc(zot, set())

    assert len(candidates) == 1
    assert "orphan-from-vault" in candidates[0].reasons
    assert any(reason.startswith("empty>") for reason in candidates[0].reasons)
    assert any(reason.startswith("test-pattern(") for reason in candidates[0].reasons)


def test_scan_zotero_for_gc_skips_recent_empty_collection():
    zot = _ZotCollections([_collection("A1", "fresh-empty", date_added="2026-04-25T00:00:00Z")])

    candidates = scan_zotero_for_gc(zot, set(), age_days=30)

    assert candidates == [GCCandidate(key="A1", name="fresh-empty", num_items=0, num_collections=0, date_added="2026-04-25T00:00:00Z", reasons=["orphan-from-vault"])]


def test_scan_zotero_for_gc_marks_non_empty_orphan_distinctly():
    # PR-A: a non-empty orphan (4 real items) must NOT be the plain
    # `orphan-from-vault` reason (which --yes can auto-delete together with
    # empty+test) — it gets the distinct `orphan-with-items(N)` reason so it
    # is never auto-deleted and triggers a strong confirm.
    zot = _ZotCollections([_collection("A1", "survey", num_items=4)])

    candidates = scan_zotero_for_gc(zot, set())

    assert len(candidates) == 1
    assert candidates[0].reasons == ["orphan-with-items(4)"]
    assert "orphan-from-vault" not in candidates[0].reasons


def test_delete_candidates_returns_ok_and_error():
    class _DeleteZot(_ZotCollections):
        def delete_collection(self, coll: dict) -> dict:
            if coll["key"] == "ERR":
                raise RuntimeError("boom")
            return super().delete_collection(coll)

    zot = _DeleteZot([])

    results = delete_candidates(
        zot,
        [
            GCCandidate(key="OK1", name="ok", num_items=0, num_collections=0, date_added=""),
            GCCandidate(key="ERR", name="err", num_items=0, num_collections=0, date_added=""),
        ],
    )

    assert results["OK1"] == "ok"
    assert "boom" in results["ERR"]


def test_cli_zotero_gc_yes_only_deletes_triple_match(tmp_path, monkeypatch):
    from research_hub import cli

    cfg = _cfg(tmp_path)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create(query="live", name="Live", slug="live")
    registry.bind("live", zotero_collection_key="LIVE1", sync_zotero=False)
    zot = _ZotCollections(
        [
            _collection("DEL1", "test-topic"),
            _collection("KEEP1", "orphan-real", num_items=2),
        ]
    )
    monkeypatch.setattr(cli, "get_config", lambda: cfg)
    monkeypatch.setattr("research_hub.zotero.client.get_client", lambda: zot)

    rc = cli.main(["zotero", "gc", "--apply", "--yes"])

    assert rc == 0
    assert zot.deleted == ["DEL1"]
