from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from research_hub.clusters import ClusterRegistry
from research_hub.doctor_field import (
    _infer_declared_field,
    field_inference_check,
    infer_field_from_notes,
)


@dataclass
class StubConfig:
    root: Path
    raw: Path
    research_hub_dir: Path
    clusters_file: Path


def make_config(tmp_path: Path) -> StubConfig:
    root = tmp_path / "vault"
    raw = root / "raw"
    research_hub_dir = root / ".research_hub"
    raw.mkdir(parents=True)
    research_hub_dir.mkdir(parents=True)
    return StubConfig(
        root=root,
        raw=raw,
        research_hub_dir=research_hub_dir,
        clusters_file=research_hub_dir / "clusters.yaml",
    )


def test_infer_field_from_notes_detects_cs_signals(tmp_path):
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()
    (notes_dir / "paper.md").write_text("arxiv swe llm software engineering", encoding="utf-8")

    inferred, scores = infer_field_from_notes(notes_dir)

    assert inferred == "cs"
    assert scores["cs"] >= 3


def test_infer_field_from_notes_detects_bio_signals(tmp_path):
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()
    (notes_dir / "paper.md").write_text("biorxiv protein genome molecular", encoding="utf-8")

    inferred, scores = infer_field_from_notes(notes_dir)

    assert inferred == "bio"
    assert scores["bio"] >= 3


def test_infer_field_from_notes_returns_general_when_empty(tmp_path):
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()

    inferred, scores = infer_field_from_notes(notes_dir)

    assert inferred == "general"
    assert scores == {}


def test_field_inference_check_warns_on_mismatch(tmp_path):
    cfg = make_config(tmp_path)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create(query="llm software engineering", name="SE", slug="se", seed_keywords=["llm", "software"])
    note_dir = cfg.raw / "se"
    note_dir.mkdir()
    (note_dir / "paper.md").write_text("biorxiv protein genome molecular", encoding="utf-8")

    reports = field_inference_check(cfg)

    assert reports[0]["cluster_slug"] == "se"
    assert reports[0]["status"] == "warn"
    assert reports[0]["declared_field"] == "cs"
    assert reports[0]["inferred_field"] == "bio"


def test_field_inference_check_ok_when_match(tmp_path):
    cfg = make_config(tmp_path)
    registry = ClusterRegistry(cfg.clusters_file)
    registry.create(query="llm software engineering", name="SE", slug="se", seed_keywords=["llm", "software"])
    note_dir = cfg.raw / "se"
    note_dir.mkdir()
    (note_dir / "paper.md").write_text("arxiv swe software llm", encoding="utf-8")

    reports = field_inference_check(cfg)

    assert reports[0]["status"] == "ok"
    assert reports[0]["inferred_field"] == "cs"


def test_infer_declared_field_from_seed_keywords():
    assert _infer_declared_field(["llm", "software", "benchmark"]) == "cs"
