"""v1.3.5 astra 07d closeout regression tests (sections 2, 3, 4, 6)."""

from __future__ import annotations

import json
import socket
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import requests
import yaml
from pyzotero import zotero, zotero_errors

import research_hub.authenticity as auth
from research_hub import __version__ as pkg_version
from research_hub import pipeline
from research_hub.clusters import ClusterRegistry
from research_hub.dedup import (
    DedupHit,
    DedupIndex,
    _extract_zotero_item_identity,
    _is_404_error,
    build_from_zotero,
    is_zotero_not_found_error,
)
from research_hub.fit_check import FitCheckResult
from research_hub.paper import (
    _UniqueMappingSafeLoader,
    _rewrite_paper_frontmatter,
    set_labels,
)
from research_hub.workspace.core import Workspace
from research_hub.workspace.integrations import LocalIntegrationsManager
from research_hub.workspace.library_snapshot import read_vault_snapshot
from research_hub.workspace.obsidian_validation import ObsidianValidation
from research_hub.workspace.sync_hooks import (
    WorkspaceSyncHooks,
    _author_surnames,
    _fold_latin_diacritics,
)


def _cfg(tmp_path: Path) -> SimpleNamespace:
    root = tmp_path / "vault"
    cfg = SimpleNamespace(
        root=root,
        raw=root / "raw",
        hub=root / "hub",
        logs=root / "logs",
        research_hub_dir=root / ".research_hub",
        clusters_file=root / ".research_hub" / "clusters.yaml",
        zotero_library_id="",
        zotero_default_collection=None,
        zotero_collections={},
    )
    for path in (cfg.raw, cfg.hub, cfg.logs, cfg.research_hub_dir):
        path.mkdir(parents=True, exist_ok=True)
    return cfg


# ---------------------------------------------------------------------------
# Section 2: Title-only FitCheck ambiguity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("order", [(4, 5), (5, 4)], ids=["4-then-5", "5-then-4"])
def test_v135_fit_load_scores_duplicate_title_different_scores_both_orders(
    tmp_path: Path,
    order: tuple[int, int],
) -> None:
    cfg = _cfg(tmp_path)
    cluster_dir = cfg.hub / "agents"
    cluster_dir.mkdir(parents=True, exist_ok=True)
    first_score, second_score = order
    rows = [
        FitCheckResult(
            doi="",
            title="Shared Ambiguous Monograph",
            score=first_score,
            reason=f"score {first_score}",
            kept=True,
            index=None,
        ).to_dict(),
        FitCheckResult(
            doi="",
            title="Shared Ambiguous Monograph",
            score=second_score,
            reason=f"score {second_score}",
            kept=True,
            index=None,
        ).to_dict(),
    ]
    (cluster_dir / ".fit_check_accepted.json").write_text(
        json.dumps({"cluster_slug": "agents", "threshold": 3, "accepted": rows}),
        encoding="utf-8",
    )

    fit_scores = auth._load_fit_scores(cfg, "agents")
    candidate = {"title": "Shared Ambiguous Monograph", "doi": ""}
    assert auth._fit_status_for_paper(candidate, fit_scores, 3) == {
        "kept": False,
        "reason": "relevance_unjudged",
        "score": None,
    }


@pytest.mark.parametrize("years", [(1998, 2024), (2024, 1998)])
def test_v135_fit_load_scores_duplicate_title_different_years_marks_ambiguous(
    tmp_path: Path,
    years: tuple[int, int],
) -> None:
    cfg = _cfg(tmp_path)
    cluster_dir = cfg.hub / "agents"
    cluster_dir.mkdir(parents=True, exist_ok=True)
    y1, y2 = years
    rows = [
        {"doi": "", "title": "Annual Hydrological Review", "score": 4, "kept": True, "year": y1},
        {"doi": "", "title": "Annual Hydrological Review", "score": 4, "kept": True, "year": y2},
    ]
    (cluster_dir / ".fit_check_accepted.json").write_text(
        json.dumps({"cluster_slug": "agents", "threshold": 3, "accepted": rows}),
        encoding="utf-8",
    )

    fit_scores = auth._load_fit_scores(cfg, "agents")
    assert auth._fit_status_for_paper({"title": "Annual Hydrological Review", "doi": ""}, fit_scores, 3) == {
        "kept": False,
        "reason": "relevance_unjudged",
        "score": None,
    }


def test_v135_fit_load_scores_missing_year_row_does_not_hide_conflicting_years(
    tmp_path: Path,
) -> None:
    cfg = _cfg(tmp_path)
    cluster_dir = cfg.hub / "agents"
    cluster_dir.mkdir(parents=True, exist_ok=True)
    rows = [
        {"doi": "", "title": "Interleaved Hydrological Review", "score": 4, "kept": True, "year": 1998},
        {"doi": "", "title": "Interleaved Hydrological Review", "score": 4, "kept": True},
        {"doi": "", "title": "Interleaved Hydrological Review", "score": 4, "kept": True, "year": 2024},
    ]
    (cluster_dir / ".fit_check_accepted.json").write_text(
        json.dumps({"cluster_slug": "agents", "threshold": 3, "accepted": rows}),
        encoding="utf-8",
    )

    fit_scores = auth._load_fit_scores(cfg, "agents")
    assert auth._fit_status_for_paper(
        {"title": "Interleaved Hydrological Review", "doi": ""}, fit_scores, 3
    ) == {
        "kept": False,
        "reason": "relevance_unjudged",
        "score": None,
    }


def test_v135_fit_load_scores_identical_duplicate_rows_still_resolve(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cluster_dir = cfg.hub / "agents"
    cluster_dir.mkdir(parents=True, exist_ok=True)
    row = {"doi": "", "title": "Identical Monograph", "score": 4, "kept": True, "year": 2023}
    (cluster_dir / ".fit_check_accepted.json").write_text(
        json.dumps({"cluster_slug": "agents", "threshold": 3, "accepted": [row, dict(row)]}),
        encoding="utf-8",
    )

    fit_scores = auth._load_fit_scores(cfg, "agents")
    assert auth._fit_status_for_paper({"title": "Identical Monograph", "doi": ""}, fit_scores, 3) == {
        "kept": True,
        "reason": "",
        "score": 4,
    }


# ---------------------------------------------------------------------------
# Section 3: Zotero edition-only & year-only identity preservation
# ---------------------------------------------------------------------------


def test_v135_dedup_hit_legacy_load_unknown_keys_and_edition_year_uniqueness(tmp_path: Path) -> None:
    legacy_path = tmp_path / "legacy_dedup.json"
    legacy_path.write_text(
        json.dumps(
            {
                "doi_to_hits": {
                    "10.1234/book": [
                        {
                            "source": "zotero",
                            "doi": "10.1234/book",
                            "title": "Principles of Hydrology",
                            "zotero_key": "ZLEGACY1",
                            "obsidian_path": None,
                            "unexpected_future_field": "ignored",
                        }
                    ]
                },
                "title_to_hits": {
                    "principles of hydrology": [
                        {
                            "source": "zotero",
                            "doi": "10.1234/book",
                            "title": "Principles of Hydrology",
                            "zotero_key": "ZLEGACY1",
                            "extra": 42,
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    loaded = DedupIndex.load(legacy_path)
    hit = loaded.doi_to_hits["10.1234/book"][0]
    assert hit.zotero_key == "ZLEGACY1"
    assert hit.year is None
    assert hit.authors == []
    assert hit.volume == ""
    assert hit.edition == ""

    idx = DedupIndex()
    idx.add(
        DedupHit(
            source="zotero",
            doi="10.1234/shared",
            title="Principles of Economics",
            zotero_key="ZK1",
            year=1890,
            authors=["Marshall, Alfred"],
            edition="1st",
        )
    )
    idx.add(
        DedupHit(
            source="zotero",
            doi="10.1234/shared",
            title="Principles of Economics",
            zotero_key="ZK1",
            year=1920,
            authors=["Marshall, Alfred"],
            edition="8th",
        )
    )
    assert len(idx.doi_to_hits["10.1234/shared"]) == 2
    assert len(idx.title_to_hits["principles of economics"]) == 2

    saved_path = tmp_path / "new_dedup.json"
    idx.save(saved_path)
    reloaded = DedupIndex.load(saved_path)
    assert [h.edition for h in reloaded.doi_to_hits["10.1234/shared"]] == ["1st", "8th"]
    copied = reloaded.copy()
    assert [h.year for h in copied.doi_to_hits["10.1234/shared"]] == [1890, 1920]


def test_v135_extract_zotero_item_identity_and_build_from_zotero() -> None:
    ident_wrapped = _extract_zotero_item_identity(
        {
            "key": "ZITEM1",
            "data": {
                "itemType": "book",
                "DOI": "10.1234/handbook",
                "title": "Hydrology Handbook",
                "date": "9999 / revised 1998-05-12",
                "creators": [
                    {"creatorType": "author", "lastName": "Doe", "firstName": "Jane"},
                    {"creatorType": "author", "name": "Consortium"},
                ],
                "volume": "2",
                "edition": "3rd",
            },
        }
    )
    assert ident_wrapped == {
        "doi": "10.1234/handbook",
        "title": "Hydrology Handbook",
        "zotero_key": "ZITEM1",
        "year": 1998,
        "authors": ["Doe, Jane", "Consortium"],
        "volume": "2",
        "edition": "3rd",
    }

    ident_flat = _extract_zotero_item_identity(
        {
            "key": "ZITEM2",
            "title": "Flat Item",
            "doi": "10.1234/flat",
            "year": "2021",
            "authors": ["Smith, Alice"],
            "volume": "1",
            "edition": "2nd",
        }
    )
    assert ident_flat["year"] == 2021
    assert ident_flat["authors"] == ["Smith, Alice"]

    class _FakeZot:
        def items(self, **_kw):
            return [
                {
                    "key": "ZBOOK1",
                    "data": {
                        "itemType": "book",
                        "DOI": "10.1234/book",
                        "title": "Economic Treatise",
                        "date": "1950",
                        "creators": [{"lastName": "Keynes", "firstName": "John"}],
                        "volume": "1",
                        "edition": "1st",
                    },
                }
            ]

    built = build_from_zotero(_FakeZot(), "lib1")
    assert len(built) == 1
    assert built[0].year == 1950
    assert built[0].authors == ["Keynes, John"]
    assert built[0].volume == "1"
    assert built[0].edition == "1st"


def test_v135_zotero_hit_and_item_match_enforce_edition_year_and_cjk_surnames() -> None:
    hit_ed1 = DedupHit(
        source="zotero",
        doi="10.1234/treatise",
        title="Economic Treatise",
        zotero_key="ZK_ED1",
        year=2020,
        authors=["Smith, Alice"],
        edition="1st",
    )
    assert (
        pipeline._zotero_hit_matches_paper(
            hit_ed1,
            {
                "doi": "10.1234/treatise",
                "title": "Economic Treatise",
                "year": 2020,
                "authors": ["Smith, Alice"],
                "edition": "2nd",
            },
        )
        is False
    )
    assert (
        pipeline._zotero_hit_matches_paper(
            hit_ed1,
            {
                "doi": "10.1234/treatise",
                "title": "Economic Treatise",
                "year": 1995,
                "authors": ["Smith, Alice"],
            },
        )
        is False
    )
    assert (
        pipeline._zotero_hit_matches_paper(
            hit_ed1,
            {
                "doi": "10.1234/treatise",
                "title": "Economic Treatise",
                "year": 2020,
                "authors": ["Smith, Alice"],
                "edition": "1st",
            },
        )
        is True
    )

    assert (
        pipeline._zotero_item_matches_paper(
            {
                "key": "ZK_LIVE",
                "DOI": "10.1234/treatise",
                "title": "Economic Treatise",
                "date": "2010",
                "creators": [{"lastName": "王", "firstName": "小明"}],
                "edition": "1st",
            },
            {
                "doi": "10.1234/treatise",
                "title": "Economic Treatise",
                "year": 2024,
                "authors": ["陳, 大文"],
                "edition": "2nd",
            },
        )
        is False
    )

    assert pipeline._author_surname_set({"authors": ["王, 小明"]}) == {"王"}
    assert pipeline._author_surname_set({"authors": ["陳, 大文"]}) == {"陳"}
    assert pipeline._author_surname_set({"authors": ["Müller, Hans"]}) == {"muller"}
    assert pipeline._author_surname_set({"authors": ["王小明"]}) == set()
    assert (
        pipeline._zotero_item_matches_paper(
            {
                "key": "ZK_CJK_UNSEG",
                "DOI": "10.1234/cjk",
                "title": "水利系統分析",
                "date": "2024",
                "creators": [{"lastName": "王", "firstName": "小明"}],
            },
            {
                "doi": "10.1234/cjk",
                "title": "水利系統分析",
                "year": 2024,
                "authors": ["王小明"],
            },
        )
        is True
    )
    assert (
        pipeline._zotero_item_matches_paper(
            {
                "key": "ZK_COMPOUND",
                "DOI": "10.1234/waals",
                "title": "On the Continuity of Gaseous and Liquid States",
                "date": "1873",
                "creators": [{"lastName": "van der Waals", "firstName": "Johannes Diderik"}],
            },
            {
                "doi": "10.1234/waals",
                "title": "On the Continuity of Gaseous and Liquid States",
                "year": 1873,
                "authors": ["Johannes Diderik van der Waals"],
            },
        )
        is True
    )
    assert (
        pipeline._zotero_item_matches_paper(
            {
                "key": "ZK_COMPOUND_DIFF",
                "DOI": "10.1234/waals",
                "title": "On the Continuity of Gaseous and Liquid States",
                "date": "1873",
                "creators": [{"lastName": "van der Waals", "firstName": "Johannes Diderik"}],
            },
            {
                "doi": "10.1234/waals",
                "title": "On the Continuity of Gaseous and Liquid States",
                "year": 1873,
                "authors": ["Bob Waals"],
            },
        )
        is False
    )

    # Stale cached DedupHit (e.g. cached edition='1st') must check live zot.item()
    # when available, reusing the key if Zotero was corrected to '2nd'.
    stale_ed1_hit = DedupHit(
        source="zotero",
        doi="10.1234/waals",
        title="On the Continuity of Gaseous and Liquid States",
        zotero_key="ZK_CORRECTED",
        year=1873,
        edition="1st",
    )

    class _CorrectedLiveZot:
        def item(self, key: str) -> dict:
            return {
                "key": key,
                "data": {
                    "DOI": "10.1234/waals",
                    "title": "On the Continuity of Gaseous and Liquid States",
                    "date": "1873",
                    "edition": "2nd",
                },
            }

    assert (
        pipeline._zotero_index_hit_status(
            stale_ed1_hit,
            {
                "doi": "10.1234/waals",
                "title": "On the Continuity of Gaseous and Liquid States",
                "year": 1873,
                "edition": "2nd",
            },
            _CorrectedLiveZot(),
            False,
        )
        == "verified"
    )


def test_v135_zotero_index_hit_verified_fails_closed_and_skips_when_obsidian_matches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hit = DedupHit(
        source="zotero",
        doi="10.1234/legacy",
        title="Legacy Paper",
        zotero_key="ZK_GONE",
    )
    paper = {"doi": "10.1234/legacy", "title": "Legacy Paper", "year": 2024}

    class _Error404Zot:
        def item(self, _key: str) -> dict:
            raise RuntimeError("404 not found")

    class _TransientErrorZot:
        def __init__(self) -> None:
            self.created: list[dict] = []

        def item(self, _key: str) -> dict:
            raise TimeoutError("temporary network failure")

        def items(self, *args, **kwargs):
            return []

        def collection_items(self, *args, **kwargs):
            return []

        def item_template(self, item_type: str) -> dict:
            return {"itemType": item_type}

        def create_items(self, items: list[dict]) -> dict:
            self.created.extend(items)
            return {"successful": {str(i): {"key": f"ZDUP{i}"} for i in range(len(items))}}

    class _EmptyZot:
        def item(self, _key: str) -> dict:
            return {}

    assert pipeline._zotero_index_hit_status(hit, paper, _Error404Zot(), False) == "mismatch"
    assert pipeline._zotero_index_hit_status(hit, paper, _TransientErrorZot(), False) == "unknown"
    assert pipeline._zotero_index_hit_status(hit, paper, _EmptyZot(), False) == "unknown"
    assert pipeline._zotero_index_hit_verified(hit, paper, _Error404Zot(), False) is False
    assert pipeline._zotero_index_hit_verified(hit, paper, _TransientErrorZot(), False) is False
    assert pipeline._zotero_index_hit_verified(hit, paper, _EmptyZot(), False) is False

    # Transient zot.item failure must defer the paper rather than falling through
    # to check_duplicate / create_items and creating a duplicate Zotero item.
    cfg_defer = _cfg(tmp_path / "defer")
    ClusterRegistry(cfg_defer.clusters_file).create(
        query="defer", name="Defer", slug="defer", zotero_collection_key="COLL_DEFER"
    )
    (cfg_defer.root / "papers_input.json").write_text(
        json.dumps(
            {
                "papers": [
                    {
                        "title": "Deferred Verification Paper",
                        "slug": "smith2024-deferred-verification",
                        "doi": "10.1234/defer",
                        "authors": ["Smith, Alice"],
                        "year": 2024,
                        "abstract": "Abs",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    transient_zot = _TransientErrorZot()
    defer_dedup = DedupIndex()
    defer_dedup.add(
        DedupHit(
            source="zotero",
            doi="10.1234/defer",
            title="Deferred Verification Paper",
            zotero_key="ZK_OTHER_COLL",
        )
    )
    monkeypatch.delenv("RESEARCH_HUB_NO_ZOTERO", raising=False)
    monkeypatch.setattr(pipeline, "get_config", lambda: cfg_defer)
    monkeypatch.setattr(pipeline, "get_client", lambda: transient_zot)
    monkeypatch.setattr(pipeline, "_load_or_build_dedup", lambda *a, **k: defer_dedup)
    monkeypatch.setattr(pipeline.time, "sleep", lambda _s: None)
    monkeypatch.setattr(
        "research_hub.authenticity.verify_authenticity",
        lambda papers, *_a, **_kw: (papers, []),
    )
    assert pipeline.run_pipeline(cluster_slug="defer", query="defer", verify=False) == 0
    assert transient_zot.created == []
    assert not (cfg_defer.raw / "defer" / "smith2024-deferred-verification.md").exists()
    defer_out = json.loads((cfg_defer.logs / "pipeline_output.json").read_text(encoding="utf-8"))
    assert defer_out["zotero_results"][0]["status"] == "DEFERRED_VERIFICATION"

    cfg = _cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(
        query="obs", name="Obs", slug="obs", zotero_collection_key="COLL_OBS"
    )
    existing_note = cfg.raw / "obs" / "smith2024-existing.md"
    existing_note.parent.mkdir(parents=True, exist_ok=True)
    existing_note.write_text(
        '---\ntitle: "Existing Obsidian Paper"\ndoi: "10.1234/obs"\nyear: 2024\nzotero-key: "ZK_OBS"\ncluster_queries: ["old"]\ntopic_cluster: "obs"\ntags: ["obs"]\n---\nBody\n',
        encoding="utf-8",
    )
    (cfg.root / "papers_input.json").write_text(
        json.dumps(
            {
                "papers": [
                    {
                        "title": "Existing Obsidian Paper",
                        "slug": "smith2024-existing",
                        "doi": "10.1234/obs",
                        "authors": ["Smith, Alice"],
                        "year": 2024,
                        "abstract": "Abs",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    class _CountingZot:
        def __init__(self) -> None:
            self.item_calls: list[str] = []

        def item(self, key: str) -> dict:
            self.item_calls.append(key)
            return {"key": key, "data": {"title": "Existing Obsidian Paper", "DOI": "10.1234/obs", "date": "2024"}}

    counting_zot = _CountingZot()
    dedup = DedupIndex()
    dedup.add(
        DedupHit(
            source="obsidian",
            doi="10.1234/obs",
            title="Existing Obsidian Paper",
            zotero_key="ZK_OBS",
            obsidian_path=str(existing_note),
        )
    )
    dedup.add(
        DedupHit(
            source="zotero",
            doi="10.1234/obs",
            title="Existing Obsidian Paper",
            zotero_key="ZK_OBS",
        )
    )
    monkeypatch.delenv("RESEARCH_HUB_NO_ZOTERO", raising=False)
    monkeypatch.setattr(pipeline, "get_config", lambda: cfg)
    monkeypatch.setattr(pipeline, "get_client", lambda: counting_zot)
    monkeypatch.setattr(pipeline, "_load_or_build_dedup", lambda *a, **k: dedup)
    monkeypatch.setattr(pipeline.time, "sleep", lambda _s: None)
    monkeypatch.setattr(pipeline, "update_cluster_links", lambda *a, **k: None)
    monkeypatch.setattr(
        "research_hub.authenticity.verify_authenticity",
        lambda papers, *_a, **_kw: (papers, []),
    )

    assert pipeline.run_pipeline(cluster_slug="obs", query="obs", verify=False) == 0
    assert counting_zot.item_calls == []


def test_v135_run_pipeline_legacy_dedup_hit_verified_against_live_zot_item(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(
        query="editions",
        name="Editions",
        slug="editions",
        zotero_collection_key="COLL_ED",
    )
    (cfg.root / "papers_input.json").write_text(
        json.dumps(
            {
                "papers": [
                    {
                        "title": "Treatise on Water Resources",
                        "slug": "smith2024-treatise-water-resources",
                        "doi": "10.1234/treatise",
                        "authors": ["Smith, Alice"],
                        "year": 2024,
                        "edition": "2nd",
                        "abstract": "Updated 2nd edition.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    class _ZotLiveMismatch:
        def __init__(self) -> None:
            self.created: list[dict] = []
            self.item_calls: list[str] = []

        def items(self, *args, **kwargs):
            return [
                {
                    "key": "ZK_LEGACY_ED1",
                    "data": {
                        "itemType": "book",
                        "title": "Treatise on Water Resources",
                        "DOI": "10.1234/treatise",
                        "date": "2010",
                        "edition": "1st",
                        "creators": [{"lastName": "Smith", "firstName": "Alice"}],
                        "tags": [],
                        "collections": [],
                    },
                }
            ]

        def collection_items(self, *args, **kwargs):
            return self.items(*args, **kwargs)

        def item(self, key: str) -> dict:
            self.item_calls.append(key)
            assert key == "ZK_LEGACY_ED1"
            return self.items()[0]

        def item_template(self, item_type: str) -> dict:
            return {"itemType": item_type}

        def create_items(self, items: list[dict]) -> dict:
            self.created.extend(items)
            return {"successful": {str(i): {"key": f"ZNEW{i}"} for i in range(len(items))}}

    fake_zot = _ZotLiveMismatch()
    monkeypatch.delenv("RESEARCH_HUB_NO_ZOTERO", raising=False)
    monkeypatch.setattr(pipeline, "get_config", lambda: cfg)
    monkeypatch.setattr(pipeline, "get_client", lambda: fake_zot)
    monkeypatch.setattr(pipeline, "add_note", lambda *a, **k: True)
    monkeypatch.setattr(pipeline.time, "sleep", lambda _s: None)
    monkeypatch.setattr(pipeline, "_next_batch_label", lambda *a, **k: "2026-11-27")
    monkeypatch.setattr(pipeline, "_ensure_batch_subcollection", lambda *a, **k: "BATCH1")
    monkeypatch.setattr(
        "research_hub.authenticity.verify_authenticity",
        lambda papers, *_a, **_kw: (papers, []),
    )

    legacy_dedup = DedupIndex()
    # Legacy DedupHit lacks year/edition, so only zot.item(hit.zotero_key) reveals the mismatch.
    legacy_dedup.add(
        DedupHit(
            source="zotero",
            doi="10.1234/treatise",
            title="Treatise on Water Resources",
            zotero_key="ZK_LEGACY_ED1",
        )
    )
    monkeypatch.setattr(pipeline, "_load_or_build_dedup", lambda *a, **k: legacy_dedup)

    rc = pipeline.run_pipeline(cluster_slug="editions", query="editions", verify=False)
    assert rc == 0
    assert "ZK_LEGACY_ED1" in fake_zot.item_calls
    assert len(fake_zot.created) == 1
    assert (cfg.raw / "editions" / "smith2024-treatise-water-resources.md").is_file()


# ---------------------------------------------------------------------------
# Section 4: YAML merge-source duplicate keys & set_labels pre-read validation
# ---------------------------------------------------------------------------


def test_v135_yaml_merge_source_duplicate_keys_rejected_while_outer_override_allowed(
    tmp_path: Path,
) -> None:
    with pytest.raises(yaml.constructor.ConstructorError):
        yaml.load(
            "custom: {<<: {title: First, title: Second}}\n",
            Loader=_UniqueMappingSafeLoader,
        )

    with pytest.raises(yaml.constructor.ConstructorError):
        yaml.load(
            "custom: {<<: [{a: 1}, {b: 2, b: 3}]}\n",
            Loader=_UniqueMappingSafeLoader,
        )

    with pytest.raises(yaml.constructor.ConstructorError):
        yaml.load(
            "custom: {<<: {1: bad}}\n",
            Loader=_UniqueMappingSafeLoader,
        )

    with pytest.raises(yaml.constructor.ConstructorError):
        yaml.load(
            "custom: {<<: {nested: {x: 1, x: 2}}, nested: {y: 1}}\n",
            Loader=_UniqueMappingSafeLoader,
        )

    allowed = yaml.load(
        "custom: {<<: {title: First}, title: Second}\n",
        Loader=_UniqueMappingSafeLoader,
    )
    assert allowed == {"custom": {"title": "Second"}}

    reused_alias_yaml = "base: &b {<<: {a: 1}, a: 2}\nother: {<<: *b}\n"
    reused_alias = yaml.load(reused_alias_yaml, Loader=_UniqueMappingSafeLoader)
    assert reused_alias == yaml.load(reused_alias_yaml, Loader=yaml.SafeLoader)

    reused_seq_yaml = "- &b {<<: {a: 1}, a: 2}\n- {<<: *b}\n"
    reused_seq_alias = yaml.load(reused_seq_yaml, Loader=_UniqueMappingSafeLoader)
    assert reused_seq_alias == yaml.load(reused_seq_yaml, Loader=yaml.SafeLoader)

    cfg = _cfg(tmp_path)
    bad_note = cfg.raw / "alpha" / "merge_dup_source.md"
    bad_note.parent.mkdir(parents=True, exist_ok=True)
    raw_bad = b"---\ntitle: \"Merge Trap\"\ncustom: {<<: {title: First, title: Second}}\n---\nBody\n"
    bad_note.write_bytes(raw_bad)
    with pytest.raises(ValueError, match="valid YAML mapping"):
        _rewrite_paper_frontmatter(bad_note, {"labels": ["seed"]})
    assert bad_note.read_bytes() == raw_bad
    with pytest.raises(ValueError, match="valid YAML mapping"):
        set_labels(cfg, bad_note.stem, add=["seed"])
    assert bad_note.read_bytes() == raw_bad

    good_note = cfg.raw / "alpha" / "merge_outer_override.md"
    good_note.write_text(
        "---\ntitle: \"Outer Override\"\ncustom: {<<: {title: First}, title: Second}\n---\nBody\n",
        encoding="utf-8",
    )
    state = set_labels(cfg, good_note.stem, add=["seed"])
    assert state.labels == ["seed"]

    alias_note = cfg.raw / "alpha" / "merge_alias_reuse.md"
    alias_note.write_text(
        "---\ntitle: \"Alias Reuse\"\nbase: &b {<<: {a: 1}, a: 2}\nother: {<<: *b}\n---\nBody\n",
        encoding="utf-8",
    )
    alias_state = set_labels(cfg, alias_note.stem, add=["seed"])
    assert alias_state.labels == ["seed"]


def test_v135_set_labels_preread_rejects_legacy_fallback_traps_before_write(
    tmp_path: Path,
) -> None:
    cfg = _cfg(tmp_path)
    alpha = cfg.raw / "alpha"
    alpha.mkdir(parents=True, exist_ok=True)

    traps = [
        ("unquoted_colon.md", b"---\ntitle: Unquoted Title: With Colon\nlabels: [seed, core]\n---\nBody\n"),
        ("non_mapping.md", b"---\n- item1\n- item2\n---\nBody\n"),
        ("dup_labels.md", b"---\ntitle: \"Dup\"\nlabels: [seed]\nlabels: [core]\n---\nBody\n"),
        ("invalid_tag.md", b"---\ntitle: \"Tag\"\nyear: !!int nope\n---\nBody\n"),
    ]
    for name, raw_bytes in traps:
        note = alpha / name
        note.write_bytes(raw_bytes)
        with pytest.raises(ValueError, match="valid YAML mapping"):
            set_labels(cfg, note.stem, add=["benchmark"])
        assert note.read_bytes() == raw_bytes


# ---------------------------------------------------------------------------
# Section 6: Cross-vault Kana dakuten & CJK surname preservation
# ---------------------------------------------------------------------------


def test_v135_kana_dakuten_and_cjk_surname_preservation_in_cross_vault_import(
    tmp_path: Path,
) -> None:
    assert _fold_latin_diacritics("café") == "cafe"
    assert _fold_latin_diacritics("cafe\u0301") == "cafe"
    assert _fold_latin_diacritics("Tokyo カラス調査") != _fold_latin_diacritics("Tokyo ガラス調査")
    assert _fold_latin_diacritics("Tokyo ハ\u309aンダ") == "Tokyo パンダ"
    assert _author_surnames(["王, 小明"]) == {"王"}
    assert _author_surnames(["陳, 大文"]) == {"陳"}
    assert _author_surnames(["王, 小明"]) != _author_surnames(["陳, 大文"])
    assert _author_surnames([{"family": "山田"}]) == {"山田"}
    assert _author_surnames([{"lastName": "山田"}]) == {"山田"}
    assert _author_surnames(["王小明"]) == set()

    vault = tmp_path / "vault_jp_cjk"
    (vault / ".obsidian").mkdir(parents=True)
    (vault / ".research_hub").mkdir()
    (vault / ".research_hub" / "clusters.yaml").write_text(
        "schema_version: '1.0'\nclusters:\n  alpha:\n    name: Alpha\n    status: active\n    obsidian_subfolder: alpha\n",
        encoding="utf-8",
    )
    (vault / "raw" / "alpha").mkdir(parents=True)
    (vault / "raw" / "alpha" / "karasu.md").write_text(
        '---\ntitle: "Tokyo カラス調査"\nyear: "2024"\nauthors: ["Sato, Ken"]\n---\nBody\n',
        encoding="utf-8",
    )
    (vault / "raw" / "alpha" / "garasu.md").write_text(
        '---\ntitle: "Tokyo ガラス調査"\nyear: "2024"\nauthors: ["Sato, Ken"]\n---\nBody\n',
        encoding="utf-8",
    )
    (vault / "raw" / "alpha" / "wang.md").write_text(
        '---\ntitle: "水利系統分析"\nyear: "2024"\nauthors: ["王, 小明"]\n---\nBody\n',
        encoding="utf-8",
    )
    (vault / "raw" / "alpha" / "chen.md").write_text(
        '---\ntitle: "水利系統分析"\nyear: "2024"\nauthors: ["陳, 大文"]\n---\nBody\n',
        encoding="utf-8",
    )

    ws = Workspace(tmp_path / "ws_jp_cjk")
    ws.create_project(id="proj-jp-cjk", title="JP CJK Import", archetype="review")
    cfg_path = tmp_path / "cfg_jp_cjk.json"
    cfg_path.write_text("{}", encoding="utf-8")
    hooks = WorkspaceSyncHooks(
        ws, LocalIntegrationsManager(cfg_path), obsidian_validation=ObsidianValidation(vault)
    )
    res = hooks.import_obsidian_notes("proj-jp-cjk", {"dry_run": False})
    assert res["imported_count"] == 4
    assert res["skipped_existing"] == 0


def test_v135_version_bumping_in_sync() -> None:
    assert pkg_version == "1.3.9"


# ---------------------------------------------------------------------------
# v1.3.6 closeout regressions (07e blockers: section 3 Path A/B & section 6)
# ---------------------------------------------------------------------------


def test_v136_run_pipeline_empty_live_zotero_data_defers_instead_of_reusing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(
        query="editions",
        name="Editions",
        slug="editions",
        zotero_collection_key="COLL_ED",
    )
    (cfg.root / "papers_input.json").write_text(
        json.dumps(
            {
                "papers": [
                    {
                        "title": "Treatise on Water Resources",
                        "slug": "smith2024-treatise-ed2",
                        "doi": "10.1234/treatise",
                        "authors": ["Smith, Alice"],
                        "year": 2024,
                        "edition": "2nd",
                        "abstract": "2nd edition.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    class _EmptyDataZot:
        def __init__(self) -> None:
            self.created: list[dict] = []

        def item(self, key: str) -> dict:
            return {"key": key, "data": {}}

        def items(self, *args, **kwargs):
            return []

        def collection_items(self, *args, **kwargs):
            return []

        def item_template(self, item_type: str) -> dict:
            return {"itemType": item_type}

        def create_items(self, items: list[dict]) -> dict:
            self.created.extend(items)
            return {"successful": {str(i): {"key": f"ZNEW{i}"} for i in range(len(items))}}

    fake_zot = _EmptyDataZot()
    # Legacy DedupHit lacks edition (representing an existing 1st-ed Zotero item),
    # while incoming pp is 2nd ed; empty live zot.item data must defer rather than reuse.
    legacy_dedup_no_ed = DedupIndex()
    legacy_dedup_no_ed.add(
        DedupHit(
            source="zotero",
            doi="10.1234/treatise",
            title="Treatise on Water Resources",
            zotero_key="ZOLD",
        )
    )
    monkeypatch.delenv("RESEARCH_HUB_NO_ZOTERO", raising=False)
    monkeypatch.setattr(pipeline, "get_config", lambda: cfg)
    monkeypatch.setattr(pipeline, "get_client", lambda: fake_zot)
    monkeypatch.setattr(pipeline, "_load_or_build_dedup", lambda *a, **k: legacy_dedup_no_ed)
    monkeypatch.setattr(pipeline.time, "sleep", lambda _s: None)
    monkeypatch.setattr(pipeline, "_next_batch_label", lambda *a, **k: "2026-11-27")
    monkeypatch.setattr(pipeline, "_ensure_batch_subcollection", lambda *a, **k: "BATCH1")
    monkeypatch.setattr(
        "research_hub.authenticity.verify_authenticity",
        lambda papers, *_a, **_kw: (papers, []),
    )

    rc = pipeline.run_pipeline(cluster_slug="editions", query="editions", verify=False)
    assert rc == 0
    assert fake_zot.created == []
    assert list(cfg.raw.rglob("*.md")) == []
    output = json.loads((cfg.logs / "pipeline_output.json").read_text(encoding="utf-8"))
    statuses = [row["status"] for row in output["zotero_results"]]
    assert statuses == ["DEFERRED_VERIFICATION"]
    assert "REUSED" not in statuses
    assert "CREATED" not in statuses
    assert output["obsidian_results"] == []
    error_logs = list(cfg.logs.glob("pipeline_errors_*.jsonl"))
    assert error_logs and "could not be verified" in error_logs[0].read_text(encoding="utf-8")


@pytest.mark.parametrize("with_legacy_hit", [True, False], ids=["legacy-index", "query-only"])
def test_v136_run_pipeline_dns_gaierror_defers_without_creating_zotero_or_notes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    with_legacy_hit: bool,
) -> None:
    assert pipeline._is_zotero_item_404(socket.gaierror(11001, "Host not found")) is False
    assert pipeline._is_zotero_item_404(RuntimeError("404 not found")) is True
    assert pipeline._is_zotero_item_404(RuntimeError("Host not found")) is False

    cfg = _cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(
        query="net",
        name="Net",
        slug="net",
        zotero_collection_key="COLL_NET",
    )
    (cfg.root / "papers_input.json").write_text(
        json.dumps(
            {
                "papers": [
                    {
                        "title": "Resilient Network Paper",
                        "slug": "smith2024-resilient-network",
                        "doi": "10.1234/resilient",
                        "authors": ["Smith, Alice"],
                        "year": 2024,
                        "abstract": "Abstract.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    class _DnsFailZot:
        def __init__(self) -> None:
            self.created: list[dict] = []

        def item(self, _key: str) -> dict:
            raise socket.gaierror(11001, "Host not found")

        def items(self, *args, **kwargs):
            raise socket.gaierror(11001, "Host not found")

        def collection_items(self, *args, **kwargs):
            raise socket.gaierror(11001, "Host not found")

        def item_template(self, item_type: str) -> dict:
            return {"itemType": item_type}

        def create_items(self, items: list[dict]) -> dict:
            self.created.extend(items)
            return {"successful": {str(i): {"key": f"ZDUP{i}"} for i in range(len(items))}}

    fake_zot = _DnsFailZot()
    dedup = DedupIndex()
    if with_legacy_hit:
        dedup.add(
            DedupHit(
                source="zotero",
                doi="10.1234/resilient",
                title="Resilient Network Paper",
                zotero_key="ZOLD_NET",
            )
        )

    monkeypatch.delenv("RESEARCH_HUB_NO_ZOTERO", raising=False)
    monkeypatch.setattr(pipeline, "get_config", lambda: cfg)
    monkeypatch.setattr(pipeline, "get_client", lambda: fake_zot)
    monkeypatch.setattr(pipeline, "_load_or_build_dedup", lambda *a, **k: dedup)
    monkeypatch.setattr(pipeline.time, "sleep", lambda _s: None)
    monkeypatch.setattr(pipeline, "_next_batch_label", lambda *a, **k: "2026-11-27")
    monkeypatch.setattr(pipeline, "_ensure_batch_subcollection", lambda *a, **k: "BATCH1")
    monkeypatch.setattr(
        "research_hub.authenticity.verify_authenticity",
        lambda papers, *_a, **_kw: (papers, []),
    )

    rc = pipeline.run_pipeline(cluster_slug="net", query="net", verify=False)
    assert rc == 0
    assert fake_zot.created == []
    assert list(cfg.raw.rglob("*.md")) == []
    output = json.loads((cfg.logs / "pipeline_output.json").read_text(encoding="utf-8"))
    assert [row["status"] for row in output["zotero_results"]] == ["DEFERRED_VERIFICATION"]
    assert output["obsidian_results"] == []
    error_logs = list(cfg.logs.glob("pipeline_errors_*.jsonl"))
    assert error_logs and "deferred" in error_logs[0].read_text(encoding="utf-8")


def test_v136_structured_cjk_surnames_cross_vault_snapshot_and_import_e2e(
    tmp_path: Path,
) -> None:
    def _make_vault(name: str, author_yaml: str) -> Path:
        vault = tmp_path / name
        (vault / ".obsidian").mkdir(parents=True)
        (vault / ".research_hub").mkdir()
        (vault / ".research_hub" / "clusters.yaml").write_text(
            "schema_version: '1.0'\nclusters:\n  alpha:\n    name: Alpha\n    status: active\n    obsidian_subfolder: alpha\n",
            encoding="utf-8",
        )
        (vault / "raw" / "alpha").mkdir(parents=True)
        (vault / "raw" / "alpha" / "paper.md").write_text(
            f'---\ntitle: "都市河川水文解析"\nyear: "2024"\nauthors:\n  - {author_yaml}\n---\nBody\n',
            encoding="utf-8",
        )
        return vault

    vault_a = _make_vault("vault_a", "{family: 山田}")
    vault_b = _make_vault("vault_b", "{lastName: 佐藤}")

    snap_a = read_vault_snapshot(vault_a)
    snap_b = read_vault_snapshot(vault_b)
    assert snap_a["notes"][0]["data"]["authors"] == ["山田"]
    assert snap_a["notes"][0]["data"]["author_surnames"] == ["山田"]
    assert snap_b["notes"][0]["data"]["authors"] == ["佐藤"]
    assert snap_b["notes"][0]["data"]["author_surnames"] == ["佐藤"]

    ws = Workspace(tmp_path / "ws_cjk_struct")
    ws.create_project(id="proj-cjk-struct", title="CJK Structured", archetype="review")
    cfg_path = tmp_path / "cfg_cjk_struct.json"
    cfg_path.write_text("{}", encoding="utf-8")
    mgr = LocalIntegrationsManager(cfg_path)

    hooks_a = WorkspaceSyncHooks(ws, mgr, obsidian_validation=ObsidianValidation(vault_a))
    res_a = hooks_a.import_obsidian_notes("proj-cjk-struct", {"dry_run": False})
    assert res_a["imported_count"] == 1
    assert res_a["skipped_existing"] == 0

    hooks_b = WorkspaceSyncHooks(ws, mgr, obsidian_validation=ObsidianValidation(vault_b))
    preview_b = hooks_b.import_obsidian_notes("proj-cjk-struct", {"dry_run": True})
    assert preview_b["would_import"] == 1
    assert preview_b["skipped_existing"] == 0
    assert [item["action"] for item in preview_b["items"]] == ["import"]

    res_b = hooks_b.import_obsidian_notes("proj-cjk-struct", {"dry_run": False})
    assert res_b["imported_count"] == 1
    assert res_b["skipped_existing"] == 0

    _, rows, _, _ = hooks_b._load_curated_sources("proj-cjk-struct")
    assert len(rows) == 2

    replay_b = hooks_b.import_obsidian_notes("proj-cjk-struct", {"dry_run": False})
    assert replay_b["imported_count"] == 0
    assert replay_b["skipped_existing"] == 1


# ---------------------------------------------------------------------------
# v1.3.7 closeout regressions (07f §3 probes)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "live_item",
    [
        {"key": "ZOLD", "data": {"date": "1890"}},
        {
            "key": "ZOLD",
            "data": {
                "DOI": "10.1234/treatise",
                "title": "Treatise on Water Resources",
                "date": "1890",
                "creators": [{"lastName": "Smith", "firstName": "Alice"}],
            },
        },
    ],
    ids=["date-only-missing-title-and-doi", "doi-title-missing-edition-field"],
)
def test_v137_partial_live_zotero_payload_defers_instead_of_reusing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    live_item: dict,
) -> None:
    cfg = _cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(
        query="editions",
        name="Editions",
        slug="editions",
        zotero_collection_key="COLL_ED",
    )
    (cfg.root / "papers_input.json").write_text(
        json.dumps(
            {
                "papers": [
                    {
                        "title": "Treatise on Water Resources",
                        "slug": "smith2024-treatise-ed2",
                        "doi": "10.1234/treatise",
                        "authors": ["Smith, Alice"],
                        "year": 2024,
                        "edition": "2nd",
                        "abstract": "2nd edition.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    class _PartialDataZot:
        def __init__(self) -> None:
            self.created: list[dict] = []

        def item(self, _key: str) -> dict:
            return live_item

        def items(self, *args, **kwargs):
            return []

        def collection_items(self, *args, **kwargs):
            return []

        def item_template(self, item_type: str) -> dict:
            return {"itemType": item_type}

        def create_items(self, items: list[dict]) -> dict:
            self.created.extend(items)
            return {"successful": {str(i): {"key": f"ZNEW{i}"} for i in range(len(items))}}

    fake_zot = _PartialDataZot()
    legacy_dedup = DedupIndex()
    legacy_dedup.add(
        DedupHit(
            source="zotero",
            doi="10.1234/treatise",
            title="Treatise on Water Resources",
            zotero_key="ZOLD",
        )
    )
    monkeypatch.delenv("RESEARCH_HUB_NO_ZOTERO", raising=False)
    monkeypatch.setattr(pipeline, "get_config", lambda: cfg)
    monkeypatch.setattr(pipeline, "get_client", lambda: fake_zot)
    monkeypatch.setattr(pipeline, "_load_or_build_dedup", lambda *a, **k: legacy_dedup)
    monkeypatch.setattr(pipeline.time, "sleep", lambda _s: None)
    monkeypatch.setattr(pipeline, "_next_batch_label", lambda *a, **k: "2026-11-27")
    monkeypatch.setattr(pipeline, "_ensure_batch_subcollection", lambda *a, **k: "BATCH1")
    monkeypatch.setattr(
        "research_hub.authenticity.verify_authenticity",
        lambda papers, *_a, **_kw: (papers, []),
    )

    rc = pipeline.run_pipeline(cluster_slug="editions", query="editions", verify=False)
    assert rc == 0
    assert fake_zot.created == []
    assert list(cfg.raw.rglob("*.md")) == []
    output = json.loads((cfg.logs / "pipeline_output.json").read_text(encoding="utf-8"))
    statuses = [row["status"] for row in output["zotero_results"]]
    assert statuses == ["DEFERRED_VERIFICATION"]
    assert "REUSED" not in statuses
    assert "CREATED" not in statuses
    assert output["obsidian_results"] == []
    error_logs = list(cfg.logs.glob("pipeline_errors_*.jsonl"))
    assert error_logs and "could not be verified" in error_logs[0].read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("item_status", "expected_status", "expected_items", "expected_notes"),
    [
        (503, "DEFERRED_VERIFICATION", 0, 0),
        (404, "CREATED", 1, 1),
    ],
    ids=["http-503-groups-404-defers", "http-404-groups-404-creates"],
)
def test_v137_real_pyzotero_mock_transport_503_defers_and_404_creates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    item_status: int,
    expected_status: str,
    expected_items: int,
    expected_notes: int,
) -> None:
    cfg = _cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(
        query="net",
        name="Net",
        slug="net",
        zotero_collection_key="COLL_NET",
    )
    (cfg.root / "papers_input.json").write_text(
        json.dumps(
            {
                "papers": [
                    {
                        "title": "Resilient Network Paper",
                        "slug": "smith2024-resilient-network",
                        "doi": "10.1234/resilient",
                        "authors": ["Smith, Alice"],
                        "year": 2024,
                        "abstract": "Abstract.",
                        "summary": "Summary.",
                        "key_findings": ["Finding 1"],
                        "methodology": "Method.",
                        "relevance": "Relevant.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    created_items: list[dict] = []
    created_notes: list[dict] = []

    def _transport_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/groups/404/items/ABCDEFGH":
            if item_status == 503:
                return httpx.Response(503, text="Service Unavailable")
            return httpx.Response(404, text="Not found")
        if request.method == "GET" and request.url.path in (
            "/groups/404/collections/COLL_NET/items",
            "/groups/404/items",
        ):
            return httpx.Response(200, json=[])
        if request.method == "GET" and request.url.path == "/items/new":
            item_type = request.url.params.get("itemType", "journalArticle")
            return httpx.Response(
                200,
                json={"itemType": item_type, "tags": [], "collections": [], "creators": []},
            )
        if request.method == "POST" and request.url.path == "/groups/404/items":
            payload = json.loads(request.content.decode("utf-8"))
            for entry in payload:
                if entry.get("itemType") == "note":
                    created_notes.append(entry)
                else:
                    created_items.append(entry)
            return httpx.Response(
                200,
                json={
                    "successful": {str(i): {"key": f"ZNEW{i}"} for i in range(len(payload))},
                    "unchanged": {},
                    "failed": {},
                },
            )
        raise AssertionError(f"Unexpected pyzotero HTTP call: {request.method} {request.url}")

    real_zot = zotero.Zotero(library_id="404", library_type="group", api_key="test")
    real_zot.client = httpx.Client(transport=httpx.MockTransport(_transport_handler))
    monkeypatch.setattr(real_zot, "check_items", lambda items: items)

    dedup = DedupIndex()
    dedup.add(
        DedupHit(
            source="zotero",
            doi="10.1234/resilient",
            title="Resilient Network Paper",
            zotero_key="ABCDEFGH",
        )
    )

    monkeypatch.delenv("RESEARCH_HUB_NO_ZOTERO", raising=False)
    monkeypatch.setattr(pipeline, "get_config", lambda: cfg)
    monkeypatch.setattr(pipeline, "get_client", lambda: real_zot)
    monkeypatch.setattr(pipeline, "_load_or_build_dedup", lambda *a, **k: dedup)
    monkeypatch.setattr(pipeline.time, "sleep", lambda _s: None)
    monkeypatch.setattr(pipeline, "_next_batch_label", lambda *a, **k: "2026-11-27")
    monkeypatch.setattr(pipeline, "_ensure_batch_subcollection", lambda *a, **k: "BATCH1")
    monkeypatch.setattr(
        "research_hub.authenticity.verify_authenticity",
        lambda papers, *_a, **_kw: (papers, []),
    )

    rc = pipeline.run_pipeline(cluster_slug="net", query="net", verify=False)
    assert rc == 0
    assert len(created_items) == expected_items
    assert len(created_notes) == expected_notes
    output = json.loads((cfg.logs / "pipeline_output.json").read_text(encoding="utf-8"))
    assert [row["status"] for row in output["zotero_results"]] == [expected_status]
    if item_status == 503:
        assert list(cfg.raw.rglob("*.md")) == []
        error_logs = list(cfg.logs.glob("pipeline_errors_*.jsonl"))
        assert error_logs and "could not be verified" in error_logs[0].read_text(encoding="utf-8")
    else:
        assert len(list(cfg.raw.rglob("*.md"))) == 1


def test_v137_http_error_status_classification_requests_and_urllib() -> None:
    hit = DedupHit(
        source="zotero",
        doi="10.1234/resilient",
        title="Resilient Network Paper",
        zotero_key="ABCDEFGH",
    )
    paper = {"doi": "10.1234/resilient", "title": "Resilient Network Paper", "year": 2024}
    url_with_404_group = "https://api.zotero.org/groups/404/items/ABCDEFGH"

    def _requests_err(code: int, text: str) -> requests.HTTPError:
        resp = requests.Response()
        resp.status_code = code
        resp.url = url_with_404_group
        return requests.HTTPError(f"{code} {text} for url: {url_with_404_group}", response=resp)

    req_404 = _requests_err(404, "Not Found")
    req_503 = _requests_err(503, "Service Unavailable")
    url_404 = urllib.error.HTTPError(url_with_404_group, 404, "Not Found", {}, None)
    url_503 = urllib.error.HTTPError(url_with_404_group, 503, "Service Unavailable", {}, None)
    pyz_404 = zotero_errors.ResourceNotFoundError(
        f"\nCode: 404\nURL: {url_with_404_group}\nMethod: GET\nResponse: Not found"
    )
    pyz_503 = zotero_errors.HTTPError(
        f"\nCode: 503\nURL: {url_with_404_group}\nMethod: GET\nResponse: Service Unavailable"
    )

    class _RaisingZot:
        def __init__(self, exc: Exception) -> None:
            self._exc = exc

        def item(self, _key: str) -> dict:
            raise self._exc

    try:
        for exc in (req_404, url_404, pyz_404):
            assert is_zotero_not_found_error(exc) is True
            assert _is_404_error(exc) is True
            assert pipeline._is_zotero_item_404(exc) is True
            assert pipeline._zotero_index_hit_status(hit, paper, _RaisingZot(exc), False) == "mismatch"

        for exc in (req_503, url_503, pyz_503, socket.gaierror(11001, "Host not found"), TimeoutError("timed out")):
            assert is_zotero_not_found_error(exc) is False
            assert _is_404_error(exc) is False
            assert pipeline._is_zotero_item_404(exc) is False
            assert pipeline._zotero_index_hit_status(hit, paper, _RaisingZot(exc), False) == "unknown"
    finally:
        url_404.close()
        url_503.close()


@pytest.mark.parametrize(
    ("hit_kwargs", "live_data", "incoming_overrides"),
    [
        (
            {"edition": "1st", "year": 2024, "authors": ["Smith"]},
            {
                "DOI": "10.1234/treatise",
                "title": "Treatise on Water Resources",
                "date": "2024",
                "creators": [{"lastName": "Smith", "firstName": "Alice"}],
            },
            {"edition": "2nd"},
        ),
        (
            {"volume": "1", "year": 2024, "authors": ["Smith"]},
            {
                "DOI": "10.1234/treatise",
                "title": "Treatise on Water Resources",
                "date": "2024",
                "creators": [{"lastName": "Smith", "firstName": "Alice"}],
            },
            {"volume": "2"},
        ),
        (
            {"year": 1890, "authors": ["Smith"]},
            {
                "DOI": "10.1234/treatise",
                "title": "Treatise on Water Resources",
                "creators": [{"lastName": "Smith", "firstName": "Alice"}],
            },
            {"year": 2024},
        ),
        (
            {"year": 2024, "authors": ["Smith"]},
            {
                "DOI": "10.1234/treatise",
                "title": "Treatise on Water Resources",
                "date": "2024",
            },
            {"authors": ["Jones, Bob"]},
        ),
    ],
    ids=["cached-edition-waiver", "cached-volume-waiver", "cached-year-waiver", "cached-authors-waiver"],
)
def test_v137_cached_hit_waiver_still_compares_omitted_live_fields(
    hit_kwargs: dict,
    live_data: dict,
    incoming_overrides: dict,
) -> None:
    hit = DedupHit(
        source="zotero",
        doi="10.1234/treatise",
        title="Treatise on Water Resources",
        zotero_key="ZOLD",
        **hit_kwargs,
    )
    paper = {
        "doi": "10.1234/treatise",
        "title": "Treatise on Water Resources",
        "year": 2024,
        "authors": ["Smith, Alice"],
        **incoming_overrides,
    }

    class _StubZot:
        def item(self, _key: str) -> dict:
            return {"key": "ZOLD", "data": live_data}

    assert pipeline._zotero_index_hit_status(hit, paper, _StubZot(), False) == "mismatch"


# ---------------------------------------------------------------------------
# v1.3.8 closeout regressions (07g §3 probes)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("live_overrides", "incoming_authors", "expected_status", "expected_items", "expected_notes"),
    [
        ({"edition": ""}, ["Smith, Alice"], "CREATED", 1, 1),
        ({"edition": None}, ["Smith, Alice"], "CREATED", 1, 1),
        ({"date": "", "edition": "2nd", "volume": "2"}, ["Smith, Alice"], "CREATED", 1, 1),
        ({"creators": [], "date": "2024", "edition": "2nd", "volume": "2"}, ["Jones, Bob"], "CREATED", 1, 1),
        ({"volume": "", "date": "2024", "edition": "2nd"}, ["Smith, Alice"], "CREATED", 1, 1),
        (
            {"edition": "", "date": "", "creators": [], "volume": ""},
            ["Smith, Alice"],
            "CREATED",
            1,
            1,
        ),
        (
            {
                "edition": "2nd",
                "date": "2024",
                "creators": [{"lastName": "Smith", "firstName": "Alice"}],
                "volume": "2",
            },
            ["Smith, Alice"],
            "REUSED",
            0,
            1,
        ),
    ],
    ids=[
        "live-edition-empty-preserves-cached-1st",
        "live-edition-none-preserves-cached-1st",
        "live-date-empty-preserves-cached-1890",
        "live-creators-empty-preserves-cached-smith",
        "live-volume-empty-preserves-cached-vol1",
        "live-all-empty-preserves-cached-conflict",
        "live-explicit-2nd-overrides-cached-1st",
    ],
)
def test_v138_cached_zotero_conflict_preserved_when_live_fields_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    live_overrides: dict,
    incoming_authors: list[str],
    expected_status: str,
    expected_items: int,
    expected_notes: int,
) -> None:
    cfg = _cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(
        query="editions",
        name="Editions",
        slug="editions",
        zotero_collection_key="COLL_ED",
    )
    (cfg.root / "papers_input.json").write_text(
        json.dumps(
            {
                "papers": [
                    {
                        "title": "Treatise on Water Resources",
                        "slug": "smith2024-treatise-ed2",
                        "doi": "10.1234/treatise",
                        "authors": incoming_authors,
                        "year": 2024,
                        "volume": "2",
                        "edition": "2nd",
                        "abstract": "2nd edition.",
                        "summary": "Summary.",
                        "key_findings": ["Finding 1"],
                        "methodology": "Method.",
                        "relevance": "Relevant.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    live_data = {
        "key": "ZOLD",
        "version": 1,
        "itemType": "book",
        "DOI": "10.1234/treatise",
        "title": "Treatise on Water Resources",
        "date": "2024",
        "creators": [{"lastName": "Smith", "firstName": "Alice"}],
        "volume": "2",
        "edition": "2nd",
        "tags": [],
        "collections": [],
    }
    live_data.update(live_overrides)

    created_items: list[dict] = []
    created_notes: list[dict] = []

    def _transport_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/groups/404/items/ZOLD":
            return httpx.Response(200, json={"key": "ZOLD", "version": 1, "data": live_data})
        if request.method in ("POST", "PUT", "PATCH") and request.url.path == "/groups/404/items/ZOLD":
            return httpx.Response(204)
        if request.method == "GET" and request.url.path == "/groups/404/items/ZOLD/children":
            return httpx.Response(200, json=[])
        if request.method == "GET" and request.url.path in (
            "/groups/404/collections/COLL_ED/items",
            "/groups/404/items",
        ):
            return httpx.Response(200, json=[])
        if request.method == "GET" and request.url.path == "/items/new":
            item_type = request.url.params.get("itemType", "journalArticle")
            return httpx.Response(
                200,
                json={"itemType": item_type, "tags": [], "collections": [], "creators": []},
            )
        if request.method == "POST" and request.url.path == "/groups/404/items":
            payload = json.loads(request.content.decode("utf-8"))
            for entry in payload:
                if entry.get("itemType") == "note":
                    created_notes.append(entry)
                else:
                    created_items.append(entry)
            return httpx.Response(
                200,
                json={
                    "successful": {str(i): {"key": f"ZNEW{i}"} for i in range(len(payload))},
                    "unchanged": {},
                    "failed": {},
                },
            )
        raise AssertionError(f"Unexpected pyzotero HTTP call: {request.method} {request.url}")

    real_zot = zotero.Zotero(library_id="404", library_type="group", api_key="test")
    real_zot.client = httpx.Client(transport=httpx.MockTransport(_transport_handler))
    monkeypatch.setattr(real_zot, "check_items", lambda items: items)

    dedup = DedupIndex()
    dedup.add(
        DedupHit(
            source="zotero",
            doi="10.1234/treatise",
            title="Treatise on Water Resources",
            zotero_key="ZOLD",
            year=1890,
            authors=["Smith, Alice"],
            volume="1",
            edition="1st",
        )
    )

    monkeypatch.delenv("RESEARCH_HUB_NO_ZOTERO", raising=False)
    monkeypatch.setattr(pipeline, "get_config", lambda: cfg)
    monkeypatch.setattr(pipeline, "get_client", lambda: real_zot)
    monkeypatch.setattr(pipeline, "_load_or_build_dedup", lambda *a, **k: dedup)
    monkeypatch.setattr(pipeline.time, "sleep", lambda _s: None)
    monkeypatch.setattr(pipeline, "_next_batch_label", lambda *a, **k: "2026-11-28")
    monkeypatch.setattr(pipeline, "_ensure_batch_subcollection", lambda *a, **k: "BATCH1")
    monkeypatch.setattr(
        "research_hub.authenticity.verify_authenticity",
        lambda papers, *_a, **_kw: (papers, []),
    )

    rc = pipeline.run_pipeline(cluster_slug="editions", query="editions", verify=False)
    assert rc == 0
    assert len(created_items) == expected_items
    assert len(created_notes) == expected_notes
    output = json.loads((cfg.logs / "pipeline_output.json").read_text(encoding="utf-8"))
    assert [row["status"] for row in output["zotero_results"]] == [expected_status]
    assert list(cfg.logs.glob("pipeline_errors_*.jsonl")) == []
    assert len(list(cfg.raw.rglob("*.md"))) == 1


@pytest.mark.parametrize("scope", ["collection", "library"], ids=["collection-scope", "library-scope"])
def test_v138_real_pyzotero_truncated_search_row_conflicting_detail_creates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scope: str,
) -> None:
    cfg = _cfg(tmp_path)
    coll_key = "COLL_ED" if scope == "collection" else ""
    if scope == "library":
        cfg.zotero_default_collection = "COLL_DEFAULT"
    ClusterRegistry(cfg.clusters_file).create(
        query="editions",
        name="Editions",
        slug="editions",
        zotero_collection_key=coll_key,
    )
    (cfg.root / "papers_input.json").write_text(
        json.dumps(
            {
                "papers": [
                    {
                        "title": "Treatise on Water Resources",
                        "slug": "smith2024-treatise-ed2",
                        "doi": "10.1234/treatise",
                        "authors": ["Smith, Alice"],
                        "year": 2024,
                        "edition": "2nd",
                        "abstract": "2nd edition.",
                        "summary": "Summary.",
                        "key_findings": ["Finding 1"],
                        "methodology": "Method.",
                        "relevance": "Relevant.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    detail_calls: list[str] = []
    created_items: list[dict] = []
    created_notes: list[dict] = []
    expected_search_path = "/groups/404/collections/COLL_ED/items" if scope == "collection" else "/groups/404/items"

    def _transport_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == expected_search_path:
            return httpx.Response(
                200,
                json=[
                    {
                        "key": "ABCDEFGH",
                        "data": {
                            "DOI": "10.1234/treatise",
                            "title": "Treatise on Water Resources",
                        },
                    }
                ],
            )
        if request.method == "GET" and request.url.path == "/groups/404/items/ABCDEFGH":
            detail_calls.append(request.url.path)
            return httpx.Response(
                200,
                json={
                    "key": "ABCDEFGH",
                    "data": {
                        "DOI": "10.1234/treatise",
                        "title": "Treatise on Water Resources",
                        "date": "1890",
                        "creators": [{"lastName": "王", "firstName": "小明"}],
                        "edition": "1st",
                    },
                },
            )
        if request.method == "GET" and request.url.path == "/items/new":
            item_type = request.url.params.get("itemType", "journalArticle")
            return httpx.Response(
                200,
                json={"itemType": item_type, "tags": [], "collections": [], "creators": []},
            )
        if request.method == "POST" and request.url.path == "/groups/404/items":
            payload = json.loads(request.content.decode("utf-8"))
            for entry in payload:
                if entry.get("itemType") == "note":
                    created_notes.append(entry)
                else:
                    created_items.append(entry)
            return httpx.Response(
                200,
                json={
                    "successful": {str(i): {"key": f"ZNEW{i}"} for i in range(len(payload))},
                    "unchanged": {},
                    "failed": {},
                },
            )
        raise AssertionError(f"Unexpected pyzotero HTTP call: {request.method} {request.url}")

    real_zot = zotero.Zotero(library_id="404", library_type="group", api_key="test")
    real_zot.client = httpx.Client(transport=httpx.MockTransport(_transport_handler))
    monkeypatch.setattr(real_zot, "check_items", lambda items: items)

    monkeypatch.delenv("RESEARCH_HUB_NO_ZOTERO", raising=False)
    monkeypatch.setattr(pipeline, "get_config", lambda: cfg)
    monkeypatch.setattr(pipeline, "get_client", lambda: real_zot)
    monkeypatch.setattr(pipeline, "_load_or_build_dedup", lambda *a, **k: DedupIndex())
    monkeypatch.setattr(pipeline.time, "sleep", lambda _s: None)
    monkeypatch.setattr(pipeline, "_next_batch_label", lambda *a, **k: "2026-11-28")
    monkeypatch.setattr(pipeline, "_ensure_batch_subcollection", lambda *a, **k: "BATCH1")
    monkeypatch.setattr(
        "research_hub.authenticity.verify_authenticity",
        lambda papers, *_a, **_kw: (papers, []),
    )

    rc = pipeline.run_pipeline(cluster_slug="editions", query="editions", verify=False)
    assert rc == 0
    assert detail_calls == ["/groups/404/items/ABCDEFGH"]
    assert len(created_items) == 1
    assert len(created_notes) == 1
    output = json.loads((cfg.logs / "pipeline_output.json").read_text(encoding="utf-8"))
    assert [row["status"] for row in output["zotero_results"]] == ["CREATED"]
    assert list(cfg.logs.glob("pipeline_errors_*.jsonl")) == []
    assert len(list(cfg.raw.rglob("*.md"))) == 1


@pytest.mark.parametrize(
    ("detail_mode", "expected_status", "expected_errors"),
    [
        ("incomplete-detail", "DEFERRED_VERIFICATION", 1),
        ("http-503", "DEFERRED_VERIFICATION", 1),
        ("complete-matching-2nd", "SKIPPED_DUPLICATE", 0),
    ],
    ids=["incomplete-detail-defers", "http-503-detail-defers", "complete-2nd-skips-duplicate"],
)
def test_v138_real_pyzotero_truncated_search_row_defers_or_skips_duplicate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    detail_mode: str,
    expected_status: str,
    expected_errors: int,
) -> None:
    cfg = _cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(
        query="editions",
        name="Editions",
        slug="editions",
        zotero_collection_key="COLL_ED",
    )
    (cfg.root / "papers_input.json").write_text(
        json.dumps(
            {
                "papers": [
                    {
                        "title": "Treatise on Water Resources",
                        "slug": "smith2024-treatise-ed2",
                        "doi": "10.1234/treatise",
                        "authors": ["Smith, Alice"],
                        "year": 2024,
                        "edition": "2nd",
                        "abstract": "2nd edition.",
                        "summary": "Summary.",
                        "key_findings": ["Finding 1"],
                        "methodology": "Method.",
                        "relevance": "Relevant.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    detail_calls: list[str] = []
    created_items: list[dict] = []
    created_notes: list[dict] = []

    def _transport_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/groups/404/collections/COLL_ED/items":
            return httpx.Response(
                200,
                json=[
                    {
                        "key": "ABCDEFGH",
                        "data": {
                            "DOI": "10.1234/treatise",
                            "title": "Treatise on Water Resources",
                        },
                    }
                ],
            )
        if request.method == "GET" and request.url.path == "/groups/404/items/ABCDEFGH":
            detail_calls.append(request.url.path)
            if detail_mode == "http-503":
                return httpx.Response(503, text="Service Unavailable")
            data = {
                "DOI": "10.1234/treatise",
                "title": "Treatise on Water Resources",
                "date": "2024",
                "creators": [{"lastName": "Smith", "firstName": "Alice"}],
            }
            if detail_mode == "complete-matching-2nd":
                data["edition"] = "2nd"
            return httpx.Response(200, json={"key": "ABCDEFGH", "data": data})
        raise AssertionError(f"Unexpected pyzotero HTTP call: {request.method} {request.url}")

    real_zot = zotero.Zotero(library_id="404", library_type="group", api_key="test")
    real_zot.client = httpx.Client(transport=httpx.MockTransport(_transport_handler))
    monkeypatch.setattr(real_zot, "check_items", lambda items: items)

    monkeypatch.delenv("RESEARCH_HUB_NO_ZOTERO", raising=False)
    monkeypatch.setattr(pipeline, "get_config", lambda: cfg)
    monkeypatch.setattr(pipeline, "get_client", lambda: real_zot)
    monkeypatch.setattr(pipeline, "_load_or_build_dedup", lambda *a, **k: DedupIndex())
    monkeypatch.setattr(pipeline.time, "sleep", lambda _s: None)
    monkeypatch.setattr(pipeline, "_next_batch_label", lambda *a, **k: "2026-11-28")
    monkeypatch.setattr(pipeline, "_ensure_batch_subcollection", lambda *a, **k: "BATCH1")
    monkeypatch.setattr(
        "research_hub.authenticity.verify_authenticity",
        lambda papers, *_a, **_kw: (papers, []),
    )

    rc = pipeline.run_pipeline(cluster_slug="editions", query="editions", verify=False)
    assert rc == 0
    assert detail_calls == ["/groups/404/items/ABCDEFGH"]
    assert created_items == []
    assert created_notes == []
    assert list(cfg.raw.rglob("*.md")) == []
    output = json.loads((cfg.logs / "pipeline_output.json").read_text(encoding="utf-8"))
    assert [row["status"] for row in output["zotero_results"]] == [expected_status]
    error_logs = list(cfg.logs.glob("pipeline_errors_*.jsonl"))
    if expected_errors:
        assert len(error_logs) == 1
        lines = [ln for ln in error_logs[0].read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(lines) == expected_errors
    else:
        assert error_logs == []


@pytest.mark.parametrize(
    ("detail_payload", "expected_status", "expected_items", "expected_notes", "expected_errors"),
    [
        (
            {
                "key": "KEYONLY1",
                "data": {
                    "DOI": "10.1234/treatise",
                    "title": "Treatise on Water Resources",
                    "date": "2024",
                    "creators": [{"lastName": "Smith", "firstName": "Alice"}],
                    "edition": "2nd",
                },
            },
            "SKIPPED_DUPLICATE",
            0,
            0,
            0,
        ),
        (
            {
                "key": "KEYONLY1",
                "data": {
                    "DOI": "10.1234/treatise",
                    "title": "Treatise on Water Resources",
                    "date": "1890",
                    "creators": [{"lastName": "Smith", "firstName": "Alice"}],
                    "edition": "1st",
                },
            },
            "CREATED",
            1,
            1,
            0,
        ),
        (
            {"key": "KEYONLY1", "data": {}},
            "DEFERRED_VERIFICATION",
            0,
            0,
            1,
        ),
        (
            {"key": "KEYONLY1", "data": {"itemType": "note", "note": "<p>memo</p>"}},
            "CREATED",
            1,
            1,
            0,
        ),
        (
            {
                "key": "KEYONLY1",
                "data": {
                    "title": "Water Resources",
                    "date": "2024",
                    "creators": [{"lastName": "Smith", "firstName": "Alice"}],
                },
            },
            "CREATED",
            1,
            1,
            0,
        ),
    ],
    ids=[
        "key-only-match-skips",
        "key-only-conflict-creates",
        "key-only-empty-detail-defers",
        "key-only-note-creates",
        "key-only-distinct-subset-title-creates",
    ],
)
def test_v138_key_only_search_row_triggers_detail_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    detail_payload: dict,
    expected_status: str,
    expected_items: int,
    expected_notes: int,
    expected_errors: int,
) -> None:
    cfg = _cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(
        query="editions",
        name="Editions",
        slug="editions",
        zotero_collection_key="COLL_ED",
    )
    (cfg.root / "papers_input.json").write_text(
        json.dumps(
            {
                "papers": [
                    {
                        "title": "Treatise on Water Resources",
                        "slug": "smith2024-treatise-ed2",
                        "doi": "10.1234/treatise",
                        "authors": ["Smith, Alice"],
                        "year": 2024,
                        "edition": "2nd",
                        "abstract": "2nd edition.",
                        "summary": "Summary.",
                        "key_findings": ["Finding 1"],
                        "methodology": "Method.",
                        "relevance": "Relevant.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    detail_calls: list[str] = []
    created_items: list[dict] = []
    created_notes: list[dict] = []

    def _transport_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/groups/404/collections/COLL_ED/items":
            return httpx.Response(200, json=[{"key": "KEYONLY1", "data": {}}])
        if request.method == "GET" and request.url.path == "/groups/404/items/KEYONLY1":
            detail_calls.append(request.url.path)
            return httpx.Response(200, json=detail_payload)
        if request.method == "GET" and request.url.path == "/items/new":
            item_type = request.url.params.get("itemType", "journalArticle")
            return httpx.Response(
                200,
                json={"itemType": item_type, "tags": [], "collections": [], "creators": []},
            )
        if request.method == "POST" and request.url.path == "/groups/404/items":
            payload = json.loads(request.content.decode("utf-8"))
            for entry in payload:
                if entry.get("itemType") == "note":
                    created_notes.append(entry)
                else:
                    created_items.append(entry)
            return httpx.Response(
                200,
                json={
                    "successful": {str(i): {"key": f"ZNEW{i}"} for i in range(len(payload))},
                    "unchanged": {},
                    "failed": {},
                },
            )
        raise AssertionError(f"Unexpected pyzotero HTTP call: {request.method} {request.url}")

    real_zot = zotero.Zotero(library_id="404", library_type="group", api_key="test")
    real_zot.client = httpx.Client(transport=httpx.MockTransport(_transport_handler))
    monkeypatch.setattr(real_zot, "check_items", lambda items: items)

    monkeypatch.delenv("RESEARCH_HUB_NO_ZOTERO", raising=False)
    monkeypatch.setattr(pipeline, "get_config", lambda: cfg)
    monkeypatch.setattr(pipeline, "get_client", lambda: real_zot)
    monkeypatch.setattr(pipeline, "_load_or_build_dedup", lambda *a, **k: DedupIndex())
    monkeypatch.setattr(pipeline.time, "sleep", lambda _s: None)
    monkeypatch.setattr(pipeline, "_next_batch_label", lambda *a, **k: "2026-11-28")
    monkeypatch.setattr(pipeline, "_ensure_batch_subcollection", lambda *a, **k: "BATCH1")
    monkeypatch.setattr(
        "research_hub.authenticity.verify_authenticity",
        lambda papers, *_a, **_kw: (papers, []),
    )

    rc = pipeline.run_pipeline(cluster_slug="editions", query="editions", verify=False)
    assert rc == 0
    assert detail_calls == ["/groups/404/items/KEYONLY1"]
    assert len(created_items) == expected_items
    assert len(created_notes) == expected_notes
    output = json.loads((cfg.logs / "pipeline_output.json").read_text(encoding="utf-8"))
    assert [row["status"] for row in output["zotero_results"]] == [expected_status]
    error_logs = list(cfg.logs.glob("pipeline_errors_*.jsonl"))
    if expected_errors:
        assert len(error_logs) == 1
        lines = [ln for ln in error_logs[0].read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(lines) == expected_errors
    else:
        assert error_logs == []


def test_v138_missing_title_in_detail_with_part_marker_defers_instead_of_creating(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _cfg(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(
        query="hydro",
        name="Hydro",
        slug="hydro",
        zotero_collection_key="COLL_HY",
    )
    (cfg.root / "papers_input.json").write_text(
        json.dumps(
            {
                "papers": [
                    {
                        "title": "Hydrology, Part 2",
                        "slug": "smith2024-hydro-part2",
                        "doi": "10.1234/hydro-p2",
                        "authors": ["Smith, Alice"],
                        "year": 2024,
                        "abstract": "Part 2.",
                        "summary": "Summary.",
                        "key_findings": ["Finding 1"],
                        "methodology": "Method.",
                        "relevance": "Relevant.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    detail_calls: list[str] = []
    created_items: list[dict] = []

    def _transport_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/groups/404/collections/COLL_HY/items":
            return httpx.Response(
                200,
                json=[
                    {
                        "key": "HYDROROW1",
                        "data": {
                            "DOI": "10.1234/hydro-p2",
                            "title": "Hydrology, Part 2",
                        },
                    }
                ],
            )
        if request.method == "GET" and request.url.path == "/groups/404/items/HYDROROW1":
            detail_calls.append(request.url.path)
            return httpx.Response(
                200,
                json={
                    "key": "HYDROROW1",
                    "data": {
                        "DOI": "10.1234/hydro-p2",
                        "date": "2024",
                        "creators": [{"lastName": "Smith", "firstName": "Alice"}],
                    },
                },
            )
        if request.method == "POST":
            created_items.append(json.loads(request.content.decode("utf-8")))
            return httpx.Response(200, json={"successful": {}, "unchanged": {}, "failed": {}})
        raise AssertionError(f"Unexpected pyzotero HTTP call: {request.method} {request.url}")

    real_zot = zotero.Zotero(library_id="404", library_type="group", api_key="test")
    real_zot.client = httpx.Client(transport=httpx.MockTransport(_transport_handler))
    monkeypatch.setattr(real_zot, "check_items", lambda items: items)

    monkeypatch.delenv("RESEARCH_HUB_NO_ZOTERO", raising=False)
    monkeypatch.setattr(pipeline, "get_config", lambda: cfg)
    monkeypatch.setattr(pipeline, "get_client", lambda: real_zot)
    monkeypatch.setattr(pipeline, "_load_or_build_dedup", lambda *a, **k: DedupIndex())
    monkeypatch.setattr(pipeline.time, "sleep", lambda _s: None)
    monkeypatch.setattr(pipeline, "_next_batch_label", lambda *a, **k: "2026-11-28")
    monkeypatch.setattr(pipeline, "_ensure_batch_subcollection", lambda *a, **k: "BATCH1")
    monkeypatch.setattr(
        "research_hub.authenticity.verify_authenticity",
        lambda papers, *_a, **_kw: (papers, []),
    )

    rc = pipeline.run_pipeline(cluster_slug="hydro", query="hydro", verify=False)
    assert rc == 0
    assert detail_calls == ["/groups/404/items/HYDROROW1"]
    assert created_items == []
    assert list(cfg.raw.rglob("*.md")) == []
    output = json.loads((cfg.logs / "pipeline_output.json").read_text(encoding="utf-8"))
    assert [row["status"] for row in output["zotero_results"]] == ["DEFERRED_VERIFICATION"]
    error_logs = list(cfg.logs.glob("pipeline_errors_*.jsonl"))
    assert len(error_logs) == 1


# ---------------------------------------------------------------------------
# v1.3.9 closeout regressions (07h §3 probes)
# ---------------------------------------------------------------------------


def _run_v139_pipeline_with_transport(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    scope: str,
    paper: dict,
    dedup: DedupIndex,
    transport_handler,
) -> tuple[int, dict, list[Path]]:
    cfg = _cfg(tmp_path)
    coll_key = "COLL_ED" if scope == "collection" else ""
    if scope != "collection":
        cfg.zotero_default_collection = "COLL_DEFAULT"
    ClusterRegistry(cfg.clusters_file).create(
        query="editions",
        name="Editions",
        slug="editions",
        zotero_collection_key=coll_key,
    )
    (cfg.root / "papers_input.json").write_text(
        json.dumps({"papers": [paper]}),
        encoding="utf-8",
    )
    real_zot = zotero.Zotero(library_id="404", library_type="group", api_key="test")
    real_zot.client = httpx.Client(transport=httpx.MockTransport(transport_handler))
    monkeypatch.setattr(real_zot, "check_items", lambda items: items)

    monkeypatch.delenv("RESEARCH_HUB_NO_ZOTERO", raising=False)
    monkeypatch.setattr(pipeline, "get_config", lambda: cfg)
    monkeypatch.setattr(pipeline, "get_client", lambda: real_zot)
    monkeypatch.setattr(pipeline, "_load_or_build_dedup", lambda *a, **k: dedup)
    monkeypatch.setattr(pipeline.time, "sleep", lambda _s: None)
    monkeypatch.setattr(pipeline, "_next_batch_label", lambda *a, **k: "2026-11-28")
    monkeypatch.setattr(pipeline, "_ensure_batch_subcollection", lambda *a, **k: "BATCH1")
    monkeypatch.setattr(
        "research_hub.authenticity.verify_authenticity",
        lambda papers, *_a, **_kw: (papers, []),
    )

    rc = pipeline.run_pipeline(cluster_slug="editions", query="editions", verify=False)
    output = json.loads((cfg.logs / "pipeline_output.json").read_text(encoding="utf-8"))
    error_logs = list(cfg.logs.glob("pipeline_errors_*.jsonl"))
    return rc, output, error_logs


@pytest.mark.parametrize(
    ("live_overrides", "incoming_authors"),
    [
        ({"edition": ""}, ["Smith, Alice"]),
        ({"edition": None}, ["Smith, Alice"]),
        ({"date": "", "edition": "2nd", "volume": "2"}, ["Smith, Alice"]),
        ({"creators": [], "date": "2024", "edition": "2nd", "volume": "2"}, ["Jones, Bob"]),
        ({"volume": "", "date": "2024", "edition": "2nd"}, ["Smith, Alice"]),
    ],
    ids=[
        "edition-empty",
        "edition-none",
        "date-empty-vs-1890",
        "creators-empty-vs-smith",
        "volume-empty-vs-1",
    ],
)
@pytest.mark.parametrize(
    "scope",
    ["collection", "library", "library-title-fallback"],
    ids=["collection", "library", "library-title-fallback"],
)
def test_v139_cached_mismatch_key_survives_search_without_second_detail_fetch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    live_overrides: dict,
    incoming_authors: list[str],
    scope: str,
) -> None:
    paper = {
        "title": "Treatise on Water Resources",
        "slug": "smith2024-treatise-ed2",
        "doi": "10.1234/treatise",
        "authors": incoming_authors,
        "year": 2024,
        "volume": "2",
        "edition": "2nd",
        "abstract": "2nd edition.",
        "summary": "Summary.",
        "key_findings": ["Finding 1"],
        "methodology": "Method.",
        "relevance": "Relevant.",
    }
    live_data = {
        "key": "ZOLD",
        "version": 1,
        "itemType": "book",
        "DOI": "10.1234/treatise",
        "title": "Treatise on Water Resources",
        "date": "2024",
        "creators": [{"lastName": "Smith", "firstName": "Alice"}],
        "volume": "2",
        "edition": "2nd",
        "tags": [],
        "collections": [],
    }
    live_data.update(live_overrides)
    row_payload = {"key": "ZOLD", "data": dict(live_data)}

    zold_detail_calls: list[str] = []
    search_queries: list[str] = []
    created_items: list[dict] = []
    created_notes: list[dict] = []
    expected_search_path = (
        "/groups/404/collections/COLL_ED/items"
        if scope == "collection"
        else "/groups/404/items"
    )

    def _transport_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/groups/404/items/ZOLD":
            zold_detail_calls.append(request.url.path)
            return httpx.Response(200, json={"key": "ZOLD", "version": 1, "data": live_data})
        if request.method == "GET" and request.url.path == expected_search_path:
            q_val = request.url.params.get("q", "")
            search_queries.append(q_val)
            if scope == "library-title-fallback" and q_val == "10.1234/treatise":
                return httpx.Response(200, json=[])
            return httpx.Response(200, json=[row_payload])
        if request.method == "GET" and request.url.path == "/items/new":
            item_type = request.url.params.get("itemType", "journalArticle")
            return httpx.Response(
                200,
                json={"itemType": item_type, "tags": [], "collections": [], "creators": []},
            )
        if request.method == "POST" and request.url.path == "/groups/404/items":
            payload = json.loads(request.content.decode("utf-8"))
            for entry in payload:
                if entry.get("itemType") == "note":
                    created_notes.append(entry)
                else:
                    created_items.append(entry)
            return httpx.Response(
                200,
                json={
                    "successful": {str(i): {"key": f"ZNEW{i}"} for i in range(len(payload))},
                    "unchanged": {},
                    "failed": {},
                },
            )
        raise AssertionError(f"Unexpected pyzotero HTTP call: {request.method} {request.url}")

    dedup = DedupIndex()
    dedup.add(
        DedupHit(
            source="zotero",
            doi="10.1234/treatise",
            title="Treatise on Water Resources",
            zotero_key="ZOLD",
            year=1890,
            authors=["Smith, Alice"],
            volume="1",
            edition="1st",
        )
    )

    rc, output, error_logs = _run_v139_pipeline_with_transport(
        tmp_path,
        monkeypatch,
        scope=scope,
        paper=paper,
        dedup=dedup,
        transport_handler=_transport_handler,
    )
    assert rc == 0
    assert zold_detail_calls == ["/groups/404/items/ZOLD"]
    assert len(created_items) == 1
    assert len(created_notes) == 1
    assert [row["status"] for row in output["zotero_results"]] == ["CREATED"]
    assert error_logs == []
    assert len(list((tmp_path / "vault" / "raw").rglob("*.md"))) == 1
    if scope == "library-title-fallback":
        assert len(search_queries) == 2


@pytest.mark.parametrize(
    "scope",
    ["collection", "library", "library-title-fallback"],
    ids=["collection", "library", "library-title-fallback"],
)
def test_v139_cached_mismatch_key_skips_to_matching_sibling_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scope: str,
) -> None:
    paper = {
        "title": "Treatise on Water Resources",
        "slug": "smith2024-treatise-ed2",
        "doi": "10.1234/treatise",
        "authors": ["Smith, Alice"],
        "year": 2024,
        "volume": "2",
        "edition": "2nd",
        "abstract": "2nd edition.",
        "summary": "Summary.",
        "key_findings": ["Finding 1"],
        "methodology": "Method.",
        "relevance": "Relevant.",
    }
    zold_data = {
        "key": "ZOLD",
        "version": 1,
        "itemType": "book",
        "DOI": "10.1234/treatise",
        "title": "Treatise on Water Resources",
        "date": "2024",
        "creators": [{"lastName": "Smith", "firstName": "Alice"}],
        "volume": "2",
        "edition": "",
        "tags": [],
        "collections": [],
    }
    zmatch_data = {
        "key": "Z_MATCHING_ED2",
        "version": 1,
        "itemType": "book",
        "DOI": "10.1234/treatise",
        "title": "Treatise on Water Resources",
        "date": "2024",
        "creators": [{"lastName": "Smith", "firstName": "Alice"}],
        "volume": "2",
        "edition": "2nd",
    }

    zold_detail_calls: list[str] = []
    expected_search_path = (
        "/groups/404/collections/COLL_ED/items"
        if scope == "collection"
        else "/groups/404/items"
    )

    def _transport_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/groups/404/items/ZOLD":
            zold_detail_calls.append(request.url.path)
            return httpx.Response(200, json={"key": "ZOLD", "version": 1, "data": zold_data})
        if request.method == "GET" and request.url.path == expected_search_path:
            q_val = request.url.params.get("q", "")
            if scope == "library-title-fallback" and q_val == "10.1234/treatise":
                return httpx.Response(200, json=[])
            return httpx.Response(
                200,
                json=[
                    {"key": "ZOLD", "data": dict(zold_data)},
                    {"key": "Z_MATCHING_ED2", "data": dict(zmatch_data)},
                ],
            )
        raise AssertionError(f"Unexpected pyzotero HTTP call: {request.method} {request.url}")

    dedup = DedupIndex()
    dedup.add(
        DedupHit(
            source="zotero",
            doi="10.1234/treatise",
            title="Treatise on Water Resources",
            zotero_key="ZOLD",
            year=1890,
            authors=["Smith, Alice"],
            volume="1",
            edition="1st",
        )
    )

    rc, output, error_logs = _run_v139_pipeline_with_transport(
        tmp_path,
        monkeypatch,
        scope=scope,
        paper=paper,
        dedup=dedup,
        transport_handler=_transport_handler,
    )
    assert rc == 0
    assert zold_detail_calls == ["/groups/404/items/ZOLD"]
    assert [row["status"] for row in output["zotero_results"]] == ["SKIPPED_DUPLICATE"]
    assert error_logs == []
    assert list((tmp_path / "vault" / "raw").rglob("*.md")) == []


@pytest.mark.parametrize(
    ("search_doi_mode", "detail_doi", "expected_status", "expected_items", "expected_notes", "expected_errors"),
    [
        ("omitted", "10.1234/older-distinct-work", "CREATED", 1, 1, 0),
        ("empty", "10.1234/older-distinct-work", "CREATED", 1, 1, 0),
        ("omitted", "10.1234/audit", "SKIPPED_DUPLICATE", 0, 0, 0),
        ("empty", "10.1234/audit", "SKIPPED_DUPLICATE", 0, 0, 0),
        ("omitted", None, "DEFERRED_VERIFICATION", 0, 0, 1),
        ("empty", "", "DEFERRED_VERIFICATION", 0, 0, 1),
    ],
    ids=[
        "row-omits-doi-detail-conflict-creates",
        "row-empty-doi-detail-conflict-creates",
        "row-omits-doi-detail-match-skips",
        "row-empty-doi-detail-match-skips",
        "row-omits-doi-detail-omits-defers",
        "row-empty-doi-detail-empty-defers",
    ],
)
@pytest.mark.parametrize(
    "scope",
    ["collection", "library", "library-title-fallback"],
    ids=["collection", "library", "library-title-fallback"],
)
def test_v139_search_row_missing_or_empty_doi_requires_detail_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    search_doi_mode: str,
    detail_doi: str | None,
    expected_status: str,
    expected_items: int,
    expected_notes: int,
    expected_errors: int,
    scope: str,
) -> None:
    paper = {
        "title": "Audit of Water Governance",
        "slug": "smith2024-audit-water",
        "doi": "10.1234/audit",
        "authors": ["Smith, Alice"],
        "year": 2024,
        "abstract": "Audit paper.",
        "summary": "Summary.",
        "key_findings": ["Finding 1"],
        "methodology": "Method.",
        "relevance": "Relevant.",
    }
    row_data: dict[str, object] = {
        "title": "  Audit of Water Governance ",
        "date": "2024",
        "creators": [{"lastName": "Smith", "firstName": "Alice"}],
    }
    if search_doi_mode == "empty":
        row_data["DOI"] = ""

    detail_data: dict[str, object] = {
        "title": "Audit of Water Governance",
        "date": "2024",
        "creators": [{"lastName": "Smith", "firstName": "Alice"}],
    }
    if detail_doi is not None:
        detail_data["DOI"] = detail_doi

    detail_calls: list[str] = []
    search_queries: list[str] = []
    created_items: list[dict] = []
    created_notes: list[dict] = []
    expected_search_path = (
        "/groups/404/collections/COLL_ED/items"
        if scope == "collection"
        else "/groups/404/items"
    )

    def _transport_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == expected_search_path:
            q_val = request.url.params.get("q", "")
            search_queries.append(q_val)
            if scope == "library-title-fallback" and q_val == "10.1234/audit":
                return httpx.Response(200, json=[])
            return httpx.Response(200, json=[{"key": "ZAUDIT1", "data": row_data}])
        if request.method == "GET" and request.url.path == "/groups/404/items/ZAUDIT1":
            detail_calls.append(request.url.path)
            return httpx.Response(200, json={"key": "ZAUDIT1", "data": detail_data})
        if request.method == "GET" and request.url.path == "/items/new":
            item_type = request.url.params.get("itemType", "journalArticle")
            return httpx.Response(
                200,
                json={"itemType": item_type, "tags": [], "collections": [], "creators": []},
            )
        if request.method == "POST" and request.url.path == "/groups/404/items":
            payload = json.loads(request.content.decode("utf-8"))
            for entry in payload:
                if entry.get("itemType") == "note":
                    created_notes.append(entry)
                else:
                    created_items.append(entry)
            return httpx.Response(
                200,
                json={
                    "successful": {str(i): {"key": f"ZNEW{i}"} for i in range(len(payload))},
                    "unchanged": {},
                    "failed": {},
                },
            )
        raise AssertionError(f"Unexpected pyzotero HTTP call: {request.method} {request.url}")

    rc, output, error_logs = _run_v139_pipeline_with_transport(
        tmp_path,
        monkeypatch,
        scope=scope,
        paper=paper,
        dedup=DedupIndex(),
        transport_handler=_transport_handler,
    )
    assert rc == 0
    assert detail_calls == ["/groups/404/items/ZAUDIT1"]
    assert len(created_items) == expected_items
    assert len(created_notes) == expected_notes
    assert [row["status"] for row in output["zotero_results"]] == [expected_status]
    if expected_errors:
        assert len(error_logs) == 1
        lines = [ln for ln in error_logs[0].read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(lines) == expected_errors
    else:
        assert error_logs == []
    expected_md = 1 if expected_status == "CREATED" else 0
    assert len(list((tmp_path / "vault" / "raw").rglob("*.md"))) == expected_md
    if scope == "library-title-fallback":
        assert len(search_queries) == 2


def test_v139_check_duplicate_normalizes_whitespace_and_punctuation_with_matcher() -> None:
    from research_hub.zotero.client import check_duplicate

    class _Zot:
        def items(self, *, q: str, limit: int = 5) -> list[dict]:
            return [
                {
                    "key": "ZPUNCT1",
                    "data": {
                        "title": "Audit of Water: Governance!",
                        "date": "2024",
                        "creators": [{"lastName": "Smith", "firstName": "Alice"}],
                    },
                }
            ]

    pp = {
        "title": "  Audit of Water Governance  ",
        "doi": "",
        "year": 2024,
        "authors": ["Smith, Alice"],
    }
    assert check_duplicate(_Zot(), pp["title"], "") is False
    assert (
        check_duplicate(
            _Zot(),
            pp["title"],
            "",
            item_matches_fn=lambda data: pipeline._zotero_search_row_matches_paper(
                data, pp, _Zot()
            ),
        )
        is True
    )


def test_v139_cached_doi_conflict_preserved_when_live_search_row_omits_doi(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paper = {
        "title": "Audit of Water Governance",
        "slug": "smith2024-audit-new",
        "doi": "10.1234/audit-new",
        "authors": ["Smith, Alice"],
        "year": 2024,
        "abstract": "New paper.",
        "summary": "Summary.",
        "key_findings": ["Finding 1"],
        "methodology": "Method.",
        "relevance": "Relevant.",
    }
    created_items: list[dict] = []
    created_notes: list[dict] = []
    detail_calls: list[str] = []

    def _transport_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/groups/404/items/ZOLD_DOI":
            detail_calls.append(request.url.path)
            return httpx.Response(
                200,
                json={
                    "key": "ZOLD_DOI",
                    "data": {
                        "title": "Audit of Water Governance",
                        "date": "2024",
                        "creators": [{"lastName": "Smith", "firstName": "Alice"}],
                    },
                },
            )
        if request.method == "GET" and request.url.path == "/groups/404/collections/COLL_ED/items":
            return httpx.Response(
                200,
                json=[
                    {
                        "key": "ZOLD_DOI",
                        "data": {
                            "title": "Audit of Water Governance",
                            "date": "2024",
                            "creators": [{"lastName": "Smith", "firstName": "Alice"}],
                        },
                    }
                ],
            )
        if request.method == "GET" and request.url.path == "/items/new":
            item_type = request.url.params.get("itemType", "journalArticle")
            return httpx.Response(
                200,
                json={"itemType": item_type, "tags": [], "collections": [], "creators": []},
            )
        if request.method == "POST" and request.url.path == "/groups/404/items":
            payload = json.loads(request.content.decode("utf-8"))
            for entry in payload:
                if entry.get("itemType") == "note":
                    created_notes.append(entry)
                else:
                    created_items.append(entry)
            return httpx.Response(
                200,
                json={
                    "successful": {str(i): {"key": f"ZNEW{i}"} for i in range(len(payload))},
                    "unchanged": {},
                    "failed": {},
                },
            )
        raise AssertionError(f"Unexpected pyzotero HTTP call: {request.method} {request.url}")

    dedup = DedupIndex()
    dedup.add(
        DedupHit(
            source="zotero",
            doi="10.1234/audit-old",
            title="Audit of Water Governance",
            zotero_key="ZOLD_DOI",
            year=2024,
            authors=["Smith, Alice"],
        )
    )

    rc, output, error_logs = _run_v139_pipeline_with_transport(
        tmp_path,
        monkeypatch,
        scope="collection",
        paper=paper,
        dedup=dedup,
        transport_handler=_transport_handler,
    )
    assert rc == 0
    assert detail_calls == []
    assert len(created_items) == 1
    assert len(created_notes) == 1
    assert [row["status"] for row in output["zotero_results"]] == ["CREATED"]
    assert error_logs == []


def test_v139_check_duplicate_preserves_non_latin_titles() -> None:
    from research_hub.zotero.client import check_duplicate

    class _Zot:
        def __init__(self, row_title: str) -> None:
            self._row_title = row_title

        def items(self, *, q: str, limit: int = 5) -> list[dict]:
            return [
                {
                    "key": "ZCJK1",
                    "data": {
                        "title": self._row_title,
                        "date": "2024",
                        "creators": [{"lastName": "Smith", "firstName": "Alice"}],
                    },
                }
            ]

    for existing_title, incoming_title in (
        ("Deep Learning Survey for Water Governance: 醫療應用", "Deep Learning Survey for Water Governance: 金融應用"),
        ("AI 在水資源管理的應用", "AI 在醫療診斷的應用"),
    ):
        pp = {
            "title": incoming_title,
            "doi": "",
            "year": 2024,
            "authors": ["Smith, Alice"],
        }
        zot = _Zot(existing_title)
        assert (
            check_duplicate(
                zot,
                pp["title"],
                "",
                item_matches_fn=lambda data, _pp=pp, _zot=zot: pipeline._zotero_search_row_matches_paper(
                    data, _pp, _zot
                ),
            )
            is False
        )
        assert (
            pipeline._zotero_hit_matches_paper(
                DedupHit(
                    source="zotero",
                    title=existing_title,
                    zotero_key="ZCJK1",
                    year=2024,
                    authors=["Smith, Alice"],
                ),
                pp,
            )
            is False
        )

    same_pp = {
        "title": "  AI 在水資源管理的應用  ",
        "doi": "",
        "year": 2024,
        "authors": ["Smith, Alice"],
    }
    same_zot = _Zot("AI: 在水資源管理的應用！")
    assert (
        check_duplicate(
            same_zot,
            same_pp["title"],
            "",
            item_matches_fn=lambda data: pipeline._zotero_search_row_matches_paper(
                data, same_pp, same_zot
            ),
        )
        is True
    )


def test_v139_pipeline_does_not_skip_different_non_latin_subtitle_papers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paper = {
        "title": "Deep Learning Survey for Water Governance: 金融應用",
        "slug": "smith2024-dl-finance",
        "doi": "",
        "authors": ["Smith, Alice"],
        "year": 2024,
        "abstract": "Finance application.",
        "summary": "Summary.",
        "key_findings": ["Finding 1"],
        "methodology": "Method.",
        "relevance": "Relevant.",
    }
    created_items: list[dict] = []
    created_notes: list[dict] = []

    def _transport_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/groups/404/items":
            return httpx.Response(
                200,
                json=[
                    {
                        "key": "ZCJK_MED",
                        "data": {
                            "title": "Deep Learning Survey for Water Governance: 醫療應用",
                            "date": "2024",
                            "creators": [{"lastName": "Smith", "firstName": "Alice"}],
                        },
                    }
                ],
            )
        if request.method == "GET" and request.url.path == "/items/new":
            item_type = request.url.params.get("itemType", "journalArticle")
            return httpx.Response(
                200,
                json={"itemType": item_type, "tags": [], "collections": [], "creators": []},
            )
        if request.method == "POST" and request.url.path == "/groups/404/items":
            payload = json.loads(request.content.decode("utf-8"))
            for entry in payload:
                if entry.get("itemType") == "note":
                    created_notes.append(entry)
                else:
                    created_items.append(entry)
            return httpx.Response(
                200,
                json={
                    "successful": {str(i): {"key": f"ZNEW{i}"} for i in range(len(payload))},
                    "unchanged": {},
                    "failed": {},
                },
            )
        raise AssertionError(f"Unexpected pyzotero HTTP call: {request.method} {request.url}")

    rc, output, error_logs = _run_v139_pipeline_with_transport(
        tmp_path,
        monkeypatch,
        scope="library",
        paper=paper,
        dedup=DedupIndex(),
        transport_handler=_transport_handler,
    )
    assert rc == 0
    assert len(created_items) == 1
    assert len(created_notes) == 1
    assert [row["status"] for row in output["zotero_results"]] == ["CREATED"]
    assert error_logs == []
    assert len(list((tmp_path / "vault" / "raw").rglob("*.md"))) == 1
