"""v1.3.5 astra 07d closeout regression tests (sections 2, 3, 4, 6)."""

from __future__ import annotations

import json
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
    assert pkg_version == "1.3.5"
