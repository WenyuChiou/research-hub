from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace


def _cfg(tmp_path: Path) -> SimpleNamespace:
    root = tmp_path / "vault"
    raw = root / "raw"
    hub = root / "hub"
    research_hub_dir = root / ".research_hub"
    raw.mkdir(parents=True)
    hub.mkdir(parents=True)
    research_hub_dir.mkdir(parents=True)
    return SimpleNamespace(
        root=root,
        raw=raw,
        hub=hub,
        research_hub_dir=research_hub_dir,
        clusters_file=research_hub_dir / "clusters.yaml",
    )


def _write_note(cfg, slug: str, doi: str) -> Path:
    note_dir = cfg.raw / "agents"
    note_dir.mkdir(parents=True, exist_ok=True)
    path = note_dir / f"{slug}.md"
    path.write_text(
        (
            "---\n"
            f'title: "{slug}"\n'
            f'doi: "{doi}"\n'
            'topic_cluster: "agents"\n'
            "---\n"
        ),
        encoding="utf-8",
    )
    return path


def test_label_from_fit_score_maps_5_to_core():
    from research_hub.paper import label_from_fit_score

    assert label_from_fit_score(5) == ["core"]


def test_label_from_fit_score_top_tier_adds_seed():
    from research_hub.paper import label_from_fit_score

    assert label_from_fit_score(5, is_top_tier=True) == ["seed", "core"]


def test_label_from_fit_score_4_returns_core():
    from research_hub.paper import label_from_fit_score

    assert label_from_fit_score(4) == ["core"]


def test_label_from_fit_score_3_returns_empty():
    from research_hub.paper import label_from_fit_score

    assert label_from_fit_score(3) == []


def test_label_from_fit_score_2_returns_tangential():
    from research_hub.paper import label_from_fit_score

    assert label_from_fit_score(2) == ["tangential"]


def test_label_from_fit_score_0_1_returns_deprecated():
    from research_hub.paper import label_from_fit_score

    assert label_from_fit_score(1) == ["deprecated"]
    assert label_from_fit_score(0) == ["deprecated"]


def test_apply_fit_check_to_labels_reads_both_sidecars(tmp_path):
    from research_hub.paper import apply_fit_check_to_labels, read_labels

    cfg = _cfg(tmp_path)
    _write_note(cfg, "accepted-paper", "10.1/accepted")
    _write_note(cfg, "rejected-paper", "10.1/rejected")
    cluster_dir = cfg.hub / "agents"
    cluster_dir.mkdir(parents=True, exist_ok=True)
    (cluster_dir / ".fit_check_accepted.json").write_text(
        json.dumps({"accepted": [{"doi": "10.1/accepted", "score": 4, "reason": "fit"}]}),
        encoding="utf-8",
    )
    (cluster_dir / ".fit_check_rejected.json").write_text(
        json.dumps({"rejected": [{"doi": "10.1/rejected", "score": 1, "reason": "off topic"}]}),
        encoding="utf-8",
    )

    result = apply_fit_check_to_labels(cfg, "agents")

    assert set(result["tagged"]) == {"accepted-paper", "rejected-paper"}
    assert "core" in read_labels(cfg, "accepted-paper").labels
    assert "deprecated" in read_labels(cfg, "rejected-paper").labels


def test_apply_fit_check_to_labels_assigns_seed_to_top_tier(tmp_path):
    from research_hub.paper import apply_fit_check_to_labels, read_labels

    cfg = _cfg(tmp_path)
    _write_note(cfg, "paper-one", "10.1/one")
    _write_note(cfg, "paper-two", "10.1/two")
    _write_note(cfg, "paper-three", "10.1/three")
    _write_note(cfg, "paper-four", "10.1/four")
    _write_note(cfg, "paper-five", "10.1/five")
    cluster_dir = cfg.hub / "agents"
    cluster_dir.mkdir(parents=True, exist_ok=True)
    (cluster_dir / ".fit_check_accepted.json").write_text(
        json.dumps(
            {
                "accepted": [
                    {"doi": "10.1/one", "score": 5, "reason": "best"},
                    {"doi": "10.1/two", "score": 5, "reason": "fit"},
                    {"doi": "10.1/three", "score": 5, "reason": "fit"},
                    {"doi": "10.1/four", "score": 5, "reason": "fit"},
                    {"doi": "10.1/five", "score": 5, "reason": "fit"},
                ]
            }
        ),
        encoding="utf-8",
    )

    apply_fit_check_to_labels(cfg, "agents")

    assert read_labels(cfg, "paper-one").labels == ["seed", "core"]
    assert read_labels(cfg, "paper-two").labels == ["core"]


def test_pick_top_tier_indices_uses_top_twenty_percent_of_score_fives():
    from research_hub.paper import _pick_top_tier_indices

    result = _pick_top_tier_indices(
        [
            {"score": 5},
            {"score": 5},
            {"score": 4},
            {"score": 5},
            {"score": 5},
            {"score": 5},
        ]
    )

    assert result == {0}


def test_pick_top_tier_indices_returns_empty_when_no_score_fives():
    from research_hub.paper import _pick_top_tier_indices

    assert _pick_top_tier_indices([{"score": 4}, {"score": 3}]) == set()


def test_apply_fit_check_to_labels_score_three_updates_fit_metadata_only(tmp_path):
    from research_hub.paper import apply_fit_check_to_labels, read_labels

    cfg = _cfg(tmp_path)
    _write_note(cfg, "paper-one", "10.1/one")
    cluster_dir = cfg.hub / "agents"
    cluster_dir.mkdir(parents=True, exist_ok=True)
    (cluster_dir / ".fit_check_accepted.json").write_text(
        json.dumps({"accepted": [{"doi": "10.1/one", "score": 3, "reason": "borderline"}]}),
        encoding="utf-8",
    )

    result = apply_fit_check_to_labels(cfg, "agents")
    state = read_labels(cfg, "paper-one")

    assert result["tagged"] == []
    assert state.labels == []
    assert state.fit_score == 3
    assert state.fit_reason == "borderline"


def test_apply_scores_writes_accepted_sidecar_json(tmp_path):
    from research_hub.fit_check import apply_scores

    cfg = _cfg(tmp_path)
    report = apply_scores(
        "agents",
        [{"title": "Paper", "doi": "10.1/a", "abstract": "A"}],
        [{"doi": "10.1/a", "score": 5, "reason": "fit"}],
        threshold=3,
        cfg=cfg,
    )

    payload = json.loads((cfg.hub / "agents" / ".fit_check_accepted.json").read_text(encoding="utf-8"))
    assert report.accepted[0].doi == "10.1/a"
    assert payload["accepted"][0]["reason"] == "fit"


def test_apply_fit_check_to_labels_reports_missing_from_accepted_sidecar(tmp_path):
    from research_hub.paper import apply_fit_check_to_labels

    cfg = _cfg(tmp_path)
    cluster_dir = cfg.hub / "agents"
    cluster_dir.mkdir(parents=True, exist_ok=True)
    (cluster_dir / ".fit_check_accepted.json").write_text(
        json.dumps({"accepted": [{"doi": "10.1/missing", "score": 5, "reason": "fit"}]}),
        encoding="utf-8",
    )

    result = apply_fit_check_to_labels(cfg, "agents")

    assert result["missing"] == ["10.1/missing"]


def test_pick_top_tier_indices_rounds_up_for_small_sets():
    from research_hub.paper import _pick_top_tier_indices

    assert _pick_top_tier_indices([{"score": 5}, {"score": 5}]) == {0}
