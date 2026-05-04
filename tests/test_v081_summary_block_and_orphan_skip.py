"""v0.81: summarize fills `## Summary` block + doctor skips raw/_deleted_*."""

from __future__ import annotations

from pathlib import Path

from research_hub import doctor
from research_hub.summarize import (
    PaperSummary,
    _replace_obsidian_block,
    _validate_entry,
)


# ---------- Part 1: summary block ----------

def _make_md_with_blocks() -> str:
    return (
        "---\n"
        "title: foo\n"
        "---\n\n"
        "## Summary\n\n"
        "> [!abstract]\n"
        "> [TODO] foo\n"
        "^summary\n\n"
        "## Key Findings\n\n"
        "> [!success]\n"
        "> - [abstract too thin to extract findings]\n"
        "^findings\n\n"
        "## Methodology\n\n"
        "> [!info]\n"
        "> [TODO]\n"
        "^methodology\n\n"
        "## Relevance\n\n"
        "> [!note]\n"
        "> [TODO]\n"
        "^relevance\n"
    )


def test_summary_block_filled_when_summary_present():
    summary = PaperSummary(
        paper_slug="x", summary="A 1-2 sentence TLDR.",
        key_findings=["finding A"], methodology="m", relevance="r",
    )
    out = _replace_obsidian_block(_make_md_with_blocks(), summary)
    assert "> A 1-2 sentence TLDR." in out
    assert "[TODO] foo" not in out


def test_summary_block_unchanged_when_summary_absent():
    summary = PaperSummary(
        paper_slug="x", summary="",
        key_findings=["finding A"], methodology="m", relevance="r",
    )
    out = _replace_obsidian_block(_make_md_with_blocks(), summary)
    # Summary block stays at [TODO] when LLM didn't return one (back-compat).
    assert "[TODO] foo" in out
    # But Findings/Methodology/Relevance still get filled.
    assert "> - finding A" in out


def test_validate_entry_accepts_summary_field():
    entry = {
        "paper_slug": "x", "summary": "TLDR sentence.",
        "key_findings": ["f1"], "methodology": "m", "relevance": "r",
    }
    sm, reason = _validate_entry(entry, valid_slugs={"x"})
    assert sm is not None and sm.summary == "TLDR sentence."


def test_validate_entry_omits_summary_field_back_compat():
    """Old LLM outputs without `summary` key still pass validation."""
    entry = {
        "paper_slug": "x",  # no `summary` key
        "key_findings": ["f1"], "methodology": "m", "relevance": "r",
    }
    sm, reason = _validate_entry(entry, valid_slugs={"x"})
    assert sm is not None and sm.summary == ""


# ---------- Part 2: doctor orphan_papers skips _deleted_* ----------


class _StubCfg:
    def __init__(self, raw_dir, clusters_file):
        self.raw = raw_dir
        self.clusters_file = clusters_file


def test_orphan_papers_skips_deleted_folders(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    raw.mkdir()
    # A real orphan folder (not bound, not deleted) → should WARN
    (raw / "true-orphan").mkdir()
    (raw / "true-orphan" / "p.md").write_text("title", encoding="utf-8")
    # A soft-deleted folder → should NOT count as orphan
    (raw / "_deleted_old-cluster").mkdir()
    (raw / "_deleted_old-cluster" / "p.md").write_text("title", encoding="utf-8")
    # Another deleted variant
    (raw / "_deleted_today_28_obsidian").mkdir()
    (raw / "_deleted_today_28_obsidian" / "p.md").write_text("title", encoding="utf-8")

    # Stub registry: no bound folders
    class _ClusterStub:
        slug = "x"
        obsidian_subfolder = "x"

    class _RegistryStub:
        def __init__(self, *a, **kw): pass
        def list(self): return []

    monkeypatch.setattr("research_hub.clusters.ClusterRegistry", _RegistryStub)
    cfg = _StubCfg(raw, tmp_path / "fake-clusters.yaml")

    result = doctor.check_cluster_orphan_papers(cfg)
    assert result.status == "WARN"
    assert "true-orphan" in (result.details or "")
    # _deleted_* folders should NOT appear in the orphan list
    assert "_deleted_old-cluster" not in (result.details or "")
    assert "_deleted_today_28_obsidian" not in (result.details or "")


def test_orphan_papers_ok_when_only_deleted_folders(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "_deleted_x").mkdir()
    (raw / "_deleted_x" / "p.md").write_text("t", encoding="utf-8")

    class _RegistryStub:
        def __init__(self, *a, **kw): pass
        def list(self): return []

    monkeypatch.setattr("research_hub.clusters.ClusterRegistry", _RegistryStub)
    cfg = _StubCfg(raw, tmp_path / "fake.yaml")

    result = doctor.check_cluster_orphan_papers(cfg)
    assert result.status == "OK"
