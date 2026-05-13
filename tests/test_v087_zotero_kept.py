"""v0.87 — kept-by-user Zotero collection flow.

Covers `load_kept_keys`, `save_kept_keys`, and the `kept_keys` filter
inside `scan_zotero_for_gc`. The CLI subcommand wiring is covered by
end-to-end behavior in test_e2e_smoke.py if it lands later.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from research_hub.zotero.gc import (
    KEPT_FILE_NAME,
    kept_file_path,
    load_kept_keys,
    save_kept_keys,
    scan_zotero_for_gc,
)


def test_kept_file_path_is_under_research_hub_dir(tmp_path: Path) -> None:
    assert kept_file_path(tmp_path) == tmp_path / KEPT_FILE_NAME


def test_load_kept_keys_missing_file_returns_empty_set(tmp_path: Path) -> None:
    assert load_kept_keys(tmp_path) == set()


def test_load_kept_keys_malformed_json_returns_empty_set(tmp_path: Path) -> None:
    (tmp_path / KEPT_FILE_NAME).write_text("not valid json", encoding="utf-8")
    assert load_kept_keys(tmp_path) == set()


def test_save_then_load_kept_keys_roundtrips(tmp_path: Path) -> None:
    save_kept_keys(tmp_path, ["ABC123", "DEF456", "GHI789"], note="bulk-mark")
    assert load_kept_keys(tmp_path) == {"ABC123", "DEF456", "GHI789"}
    saved = json.loads((tmp_path / KEPT_FILE_NAME).read_text(encoding="utf-8"))
    assert saved["kept"] == ["ABC123", "DEF456", "GHI789"]  # sorted
    assert saved["note"] == "bulk-mark"
    assert "marked_at" in saved


def test_save_kept_keys_dedupes_and_strips_whitespace(tmp_path: Path) -> None:
    save_kept_keys(tmp_path, ["  K1  ", "K1", "K2", ""])
    assert load_kept_keys(tmp_path) == {"K1", "K2"}


def _stub_zot_one_orphan(keys: list[tuple[str, str, int, int]]):
    """Build a minimal pyzotero stub that yields N collections."""
    iso = "2024-01-01T00:00:00Z"
    collections_chunk = [
        {
            "key": k,
            "data": {"key": k, "name": name, "dateAdded": iso},
            "meta": {"numItems": items, "numCollections": subs},
        }
        for k, name, items, subs in keys
    ]
    calls = {"n": 0}

    def collections(limit=200, start=0):
        if calls["n"] > 0:
            return []
        calls["n"] += 1
        return collections_chunk

    return SimpleNamespace(collections=collections)


def test_scan_with_kept_keys_excludes_them_from_orphan_results() -> None:
    zot = _stub_zot_one_orphan([
        ("KEEPME", "Risk perception", 44, 0),
        ("DROPME", "scratch-collection", 0, 0),
    ])
    # Without kept_keys, both show up as orphan-from-vault
    candidates = scan_zotero_for_gc(zot, vault_keys=set())
    assert {c.key for c in candidates} == {"KEEPME", "DROPME"}

    # With kept_keys={KEEPME}, only DROPME remains
    zot = _stub_zot_one_orphan([
        ("KEEPME", "Risk perception", 44, 0),
        ("DROPME", "scratch-collection", 0, 0),
    ])
    candidates = scan_zotero_for_gc(zot, vault_keys=set(), kept_keys={"KEEPME"})
    assert {c.key for c in candidates} == {"DROPME"}


def test_kept_key_still_drops_if_test_pattern_matches() -> None:
    """User-marked-kept shouldn't override an explicit test-pattern name.

    A collection named `test-*` is presumably test cruft; if the user
    mark-kept it by accident via --all-orphans, the test-pattern reason
    still surfaces it as a candidate so the user can revisit.
    """
    zot = _stub_zot_one_orphan([
        ("OOPS", "test-zzz-scratch", 0, 0),
    ])
    candidates = scan_zotero_for_gc(zot, vault_keys=set(), kept_keys={"OOPS"})
    # orphan-from-vault is suppressed by kept_keys, but test-pattern is independent
    assert len(candidates) == 1
    assert any("test-pattern" in r for r in candidates[0].reasons)
    assert "orphan-from-vault" not in candidates[0].reasons
