"""v1.3.5 astra 07d closeout regression tests (sections 2, 3, 4, 6)."""

from __future__ import annotations

import json
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

import research_hub.authenticity as auth
from research_hub import __version__ as pkg_version
from research_hub import pipeline
from research_hub.clusters import ClusterRegistry
from research_hub.dedup import (
    DedupHit,
    DedupIndex,
    _extract_zotero_item_identity,
    build_from_zotero,
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
    assert pkg_version == "1.3.6"


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
