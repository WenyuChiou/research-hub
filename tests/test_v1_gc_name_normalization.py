"""Conservative name-normalization suppresses false orphan flags only."""

from __future__ import annotations

import pytest

from research_hub.clusters import slugify
from research_hub.zotero.gc import scan_zotero_for_gc


def _collection(
    key,
    name,
    *,
    num_items=0,
    num_collections=0,
    date_added="2025-01-01T00:00:00Z",
) -> dict:
    return {
        "key": key,
        "data": {"key": key, "name": name, "dateAdded": date_added},
        "meta": {"numItems": num_items, "numCollections": num_collections},
    }


class _Zot:
    def __init__(self, collections):
        self._c = collections

    def collections(self, *, limit=200, start=0):
        return self._c[start:start + limit]


def _vault_name_slugs() -> set[str]:
    return {
        slugify("Machine Learning Flood Forecasting"),
        "ml-flood-forecasting",
    }


def test_exact_reported_truncated_date_prefixed_collection_is_not_orphan():
    candidates = scan_zotero_for_gc(
        _Zot([
            _collection(
                "ZZZORPHAN1",
                "20260518-machine-learning-flood-forecas",
                num_items=7,
            )
        ]),
        vault_keys=set(),
        kept_keys=None,
        vault_name_slugs=_vault_name_slugs(),
    )

    assert not any(candidate.key == "ZZZORPHAN1" for candidate in candidates)


@pytest.mark.parametrize(
    "name",
    [
        "20260517-machine-learning-flood-forecasting",
        "20260518T093000-machine-learning-flood-forec",
    ],
)
def test_date_prefix_variants_are_name_recognised(name):
    candidates = scan_zotero_for_gc(
        _Zot([_collection("ZZZORPHAN2", name, num_items=7)]),
        vault_keys=set(),
        kept_keys=None,
        vault_name_slugs=_vault_name_slugs(),
    )

    assert not candidates


def test_unrelated_non_empty_orphan_still_flagged():
    candidates = scan_zotero_for_gc(
        _Zot([_collection("UNRELATED1", "scratch-xyz", num_items=3)]),
        vault_keys=set(),
        kept_keys=None,
        vault_name_slugs=_vault_name_slugs(),
    )

    assert len(candidates) == 1
    assert candidates[0].reasons == ["orphan-with-items(3)"]


def test_empty_recognised_collection_keeps_empty_junk_reason_only():
    candidates = scan_zotero_for_gc(
        _Zot([
            _collection(
                "EMPTYRECOG1",
                "20260518-machine-learning-flood-forecas",
                num_items=0,
                date_added="2020-01-01T00:00:00Z",
            )
        ]),
        vault_keys=set(),
        age_days=30,
        kept_keys=None,
        vault_name_slugs=_vault_name_slugs(),
    )

    assert len(candidates) == 1
    assert candidates[0].reasons == ["empty>30d"]
    assert "orphan-from-vault" not in candidates[0].reasons


def test_true_empty_unrecognised_orphan_still_has_yes_safety_reasons():
    candidates = scan_zotero_for_gc(
        _Zot([
            _collection(
                "EMPTYORPHAN1",
                "qqqq-deleteme",
                num_items=0,
                date_added="2020-01-01T00:00:00Z",
            )
        ]),
        vault_keys=set(),
        age_days=30,
        kept_keys=None,
        vault_name_slugs=_vault_name_slugs(),
    )

    assert len(candidates) == 1
    assert "empty>30d" in candidates[0].reasons
    assert "orphan-from-vault" in candidates[0].reasons


def test_non_date_long_digit_prefix_is_not_stripped_so_stays_orphan():
    """W1: a non-date long numeric prefix (e.g. a Unix timestamp) must NOT
    be stripped by _DATE_PREFIX_RE, so the name does not collapse onto a
    cluster slug and the collection stays flagged (safe over->under-flag
    direction)."""
    candidates = scan_zotero_for_gc(
        _Zot([
            _collection(
                "TS1",
                "1234567890-machine-learning-flood-forecasting",
                num_items=4,
            )
        ]),
        vault_keys=set(),
        kept_keys=None,
        vault_name_slugs=_vault_name_slugs(),
    )

    assert len(candidates) == 1
    assert candidates[0].reasons == ["orphan-with-items(4)"]


def test_short_name_collision_does_not_suppress_orphan_reason():
    candidates = scan_zotero_for_gc(
        _Zot([_collection("SHORT1", "abc", num_items=2)]),
        vault_keys=set(),
        kept_keys=None,
        vault_name_slugs={"abc"},
    )

    assert len(candidates) == 1
    assert candidates[0].reasons == ["orphan-with-items(2)"]


def test_none_vault_name_slugs_keeps_old_orphan_behaviour():
    candidates = scan_zotero_for_gc(
        _Zot([
            _collection(
                "OLDDEFAULT1",
                "20260518-machine-learning-flood-forecas",
                num_items=7,
            )
        ]),
        vault_keys=set(),
        kept_keys=None,
        vault_name_slugs=None,
    )

    assert len(candidates) == 1
    assert candidates[0].reasons == ["orphan-with-items(7)"]
