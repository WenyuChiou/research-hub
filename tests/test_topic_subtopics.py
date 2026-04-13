from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_hub.clusters import ClusterRegistry
from research_hub.topic import (
    SubtopicProposal,
    apply_assignments,
    build_subtopic_notes,
    emit_assign_prompt,
    emit_propose_prompt,
    list_subtopics,
)


class StubConfig:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.raw = root / "raw"
        self.hub = root / "hub"
        self.research_hub_dir = root / ".research_hub"
        self.clusters_file = self.research_hub_dir / "clusters.yaml"
        self.raw.mkdir(parents=True, exist_ok=True)
        self.hub.mkdir(parents=True, exist_ok=True)
        self.research_hub_dir.mkdir(parents=True, exist_ok=True)


def _cfg(tmp_path: Path) -> StubConfig:
    cfg = StubConfig(tmp_path / "vault")
    ClusterRegistry(cfg.clusters_file).create(query="my cluster", name="My Cluster", slug="my-cluster")
    return cfg


def _write_note(
    cfg: StubConfig,
    slug: str,
    *,
    title: str,
    authors: str = "Doe, Jane",
    year: str = "2024",
    doi: str | None = None,
    summary: str | None = None,
    abstract: str = "Default abstract.",
    extra_frontmatter: str = "",
) -> Path:
    note_dir = cfg.raw / "my-cluster"
    note_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "---",
        f'title: "{title}"',
        f'authors: "{authors}"',
        f'year: "{year}"',
        f'doi: "{doi or f"10.1/{slug}"}"',
    ]
    if summary is not None:
        lines.append(f'summary: "{summary}"')
    if extra_frontmatter:
        lines.append(extra_frontmatter.rstrip("\n"))
    lines.extend(
        [
            "---",
            "",
            "## Abstract",
            abstract,
            "",
            "## Summary",
            f"Summary for {title}.",
            "",
        ]
    )
    path = note_dir / f"{slug}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _proposal_json_block(prompt: str) -> dict:
    start = prompt.index("```json") + len("```json")
    end = prompt.index("```", start)
    return json.loads(prompt[start:end].strip())


def _assignment_prompt_json_block(prompt: str) -> dict:
    start = prompt.index("```json") + len("```json")
    end = prompt.index("```", start)
    return json.loads(prompt[start:end].strip())


def test_emit_propose_prompt_includes_digest(tmp_path):
    cfg = _cfg(tmp_path)
    _write_note(cfg, "paper1", title="Paper One")
    _write_note(cfg, "paper2", title="Paper Two")
    _write_note(cfg, "paper3", title="Paper Three")

    prompt = emit_propose_prompt(cfg, "my-cluster")

    assert "Paper One" in prompt
    assert "Paper Two" in prompt
    assert "Paper Three" in prompt


def test_emit_propose_prompt_respects_target_count(tmp_path):
    cfg = _cfg(tmp_path)

    default_prompt = emit_propose_prompt(cfg, "my-cluster")
    custom_prompt = emit_propose_prompt(cfg, "my-cluster", target_count=3)

    assert "Propose 5 natural sub-topics" in default_prompt
    assert "Propose 3 natural sub-topics" in custom_prompt


def test_emit_propose_prompt_empty_cluster_returns_message(tmp_path):
    cfg = _cfg(tmp_path)

    prompt = emit_propose_prompt(cfg, "my-cluster")

    assert "0 papers." in prompt
    assert _proposal_json_block(prompt)["subtopics"][0]["slug"] == "benchmarks"


def test_emit_assign_prompt_lists_all_subtopics(tmp_path):
    cfg = _cfg(tmp_path)
    subtopics = [
        SubtopicProposal(slug="benchmarks", title="Benchmarks", description="d1"),
        SubtopicProposal(slug="agent-interfaces", title="Agent Interfaces", description="d2"),
        SubtopicProposal(slug="evaluation-methods", title="Evaluation Methods", description="d3"),
    ]

    prompt = emit_assign_prompt(cfg, "my-cluster", subtopics)

    assert "benchmarks" in prompt
    assert "agent-interfaces" in prompt
    assert "evaluation-methods" in prompt


def test_emit_assign_prompt_lists_all_papers(tmp_path):
    cfg = _cfg(tmp_path)
    _write_note(cfg, "paper1", title="Paper One", abstract="Abstract one.")
    _write_note(cfg, "paper2", title="Paper Two", abstract="Abstract two.")
    _write_note(cfg, "paper3", title="Paper Three", abstract="Abstract three.")

    prompt = emit_assign_prompt(cfg, "my-cluster", [SubtopicProposal(slug="benchmarks", title="Benchmarks")])

    assert "Paper One" in prompt and "Abstract one." in prompt
    assert "Paper Two" in prompt and "Abstract two." in prompt
    assert "Paper Three" in prompt and "Abstract three." in prompt


def test_emit_assign_prompt_output_schema_is_valid_json(tmp_path):
    cfg = _cfg(tmp_path)

    prompt = emit_assign_prompt(cfg, "my-cluster", [SubtopicProposal(slug="benchmarks", title="Benchmarks")])

    parsed = _assignment_prompt_json_block(prompt)
    assert "assignments" in parsed


def test_apply_assignments_writes_subtopics_to_frontmatter(tmp_path):
    cfg = _cfg(tmp_path)
    path = _write_note(cfg, "paper1", title="Paper One")

    apply_assignments(cfg, "my-cluster", {"paper1": ["benchmarks"]})

    text = path.read_text(encoding="utf-8")
    assert "subtopics:" in text
    assert "  - benchmarks" in text


def test_apply_assignments_preserves_existing_frontmatter(tmp_path):
    cfg = _cfg(tmp_path)
    path = _write_note(cfg, "paper1", title="Paper One", doi="10.1/preserved")

    apply_assignments(cfg, "my-cluster", {"paper1": ["benchmarks"]})

    text = path.read_text(encoding="utf-8")
    assert 'title: "Paper One"' in text
    assert 'doi: "10.1/preserved"' in text


def test_apply_assignments_multi_subtopic_paper(tmp_path):
    cfg = _cfg(tmp_path)
    path = _write_note(cfg, "paper1", title="Paper One")

    apply_assignments(cfg, "my-cluster", {"paper1": ["benchmarks", "evaluation-methods"]})

    text = path.read_text(encoding="utf-8")
    assert "  - benchmarks" in text
    assert "  - evaluation-methods" in text


def test_apply_assignments_unknown_paper_slug_is_logged_and_skipped(tmp_path, caplog):
    cfg = _cfg(tmp_path)
    _write_note(cfg, "paper1", title="Paper One")

    with caplog.at_level("WARNING"):
        report = apply_assignments(cfg, "my-cluster", {"missing": ["benchmarks"], "paper1": ["benchmarks"]})

    assert "missing" not in report
    assert report["paper1"] == 1
    assert "missing" in caplog.text


def test_apply_assignments_replaces_existing_subtopics_field(tmp_path):
    cfg = _cfg(tmp_path)
    path = _write_note(
        cfg,
        "paper1",
        title="Paper One",
        extra_frontmatter="subtopics:\n  - old-topic",
    )

    apply_assignments(cfg, "my-cluster", {"paper1": ["benchmarks"]})

    text = path.read_text(encoding="utf-8")
    assert "old-topic" not in text
    assert text.count("subtopics:") == 1


def test_build_subtopic_notes_creates_one_file_per_subtopic(tmp_path):
    cfg = _cfg(tmp_path)
    _write_note(cfg, "paper1", title="Paper One")
    _write_note(cfg, "paper2", title="Paper Two")
    _write_note(cfg, "paper3", title="Paper Three")
    apply_assignments(
        cfg,
        "my-cluster",
        {
            "paper1": ["benchmarks"],
            "paper2": ["agent-interfaces"],
            "paper3": ["evaluation-methods"],
        },
    )

    written = build_subtopic_notes(cfg, "my-cluster")

    assert len(written) == 3
    assert len(list((cfg.raw / "my-cluster" / "topics").glob("*.md"))) == 3


def test_build_subtopic_notes_numbers_files_01_02_03(tmp_path):
    cfg = _cfg(tmp_path)
    _write_note(cfg, "paper1", title="Paper One")
    _write_note(cfg, "paper2", title="Paper Two")
    _write_note(cfg, "paper3", title="Paper Three")
    apply_assignments(
        cfg,
        "my-cluster",
        {
            "paper1": ["benchmarks"],
            "paper2": ["agent-interfaces"],
            "paper3": ["evaluation-methods"],
        },
    )

    written = build_subtopic_notes(cfg, "my-cluster")

    assert [path.name for path in written] == [
        "01_agent-interfaces.md",
        "02_benchmarks.md",
        "03_evaluation-methods.md",
    ]


def test_build_subtopic_notes_groups_papers_by_subtopic(tmp_path):
    cfg = _cfg(tmp_path)
    _write_note(cfg, "paper1", title="Paper One")
    _write_note(cfg, "paper2", title="Paper Two")
    apply_assignments(cfg, "my-cluster", {"paper1": ["benchmarks"], "paper2": ["agent-interfaces"]})

    build_subtopic_notes(cfg, "my-cluster")

    benchmarks = (cfg.raw / "my-cluster" / "topics" / "02_benchmarks.md").read_text(encoding="utf-8")
    interfaces = (cfg.raw / "my-cluster" / "topics" / "01_agent-interfaces.md").read_text(encoding="utf-8")
    assert "[[paper1|" in benchmarks
    assert "[[paper2|" not in benchmarks
    assert "[[paper2|" in interfaces


def test_build_subtopic_notes_multi_subtopic_paper_appears_in_both(tmp_path):
    cfg = _cfg(tmp_path)
    _write_note(cfg, "paper1", title="Paper One")
    apply_assignments(cfg, "my-cluster", {"paper1": ["benchmarks", "agent-interfaces"]})

    build_subtopic_notes(cfg, "my-cluster")

    topics_dir = cfg.raw / "my-cluster" / "topics"
    assert "[[paper1|" in (topics_dir / "01_agent-interfaces.md").read_text(encoding="utf-8")
    assert "[[paper1|" in (topics_dir / "02_benchmarks.md").read_text(encoding="utf-8")


def test_build_subtopic_notes_overwrites_papers_section_only(tmp_path):
    cfg = _cfg(tmp_path)
    _write_note(cfg, "paper1", title="Paper One")
    _write_note(cfg, "paper2", title="Paper Two")
    apply_assignments(cfg, "my-cluster", {"paper1": ["benchmarks"]})
    build_subtopic_notes(cfg, "my-cluster")
    path = cfg.raw / "my-cluster" / "topics" / "01_benchmarks.md"
    original = path.read_text(encoding="utf-8")
    edited = original.replace("## Scope\n", "## Scope\n\nCustom scope.\n").replace(
        "## Open questions\n",
        "## Open questions\n\n- custom question\n",
    )
    path.write_text(edited, encoding="utf-8")

    apply_assignments(cfg, "my-cluster", {"paper1": ["benchmarks"], "paper2": ["benchmarks"]})
    build_subtopic_notes(cfg, "my-cluster")

    rerun = path.read_text(encoding="utf-8")
    assert "Custom scope." in rerun
    assert "- custom question" in rerun
    assert "[[paper1|" in rerun
    assert "[[paper2|" in rerun


def test_build_subtopic_notes_rerun_preserves_frontmatter_yaml(tmp_path):
    """Regression test for v0.20.1: _update_subtopic_frontmatter dropped
    the trailing newline before the closing --- fence on rebuild, producing
    `status: draft---` jammed onto one line and breaking YAML parsing.
    `_extract_frontmatter_block` then failed and `_existing_subtopic_paper_count`
    returned 0 for every cluster, making `topic list` show 0 papers."""
    cfg = _cfg(tmp_path)
    _write_note(cfg, "paper1", title="Paper One")
    _write_note(cfg, "paper2", title="Paper Two")
    apply_assignments(cfg, "my-cluster", {"paper1": ["benchmarks"]})
    build_subtopic_notes(cfg, "my-cluster")
    path = cfg.raw / "my-cluster" / "topics" / "01_benchmarks.md"

    # Rebuild — this triggers _update_subtopic_frontmatter
    apply_assignments(cfg, "my-cluster", {"paper1": ["benchmarks"], "paper2": ["benchmarks"]})
    build_subtopic_notes(cfg, "my-cluster")

    rerun_text = path.read_text(encoding="utf-8")
    # The YAML fence must be on its own line, not glued to the last field
    assert "\nstatus: draft\n---\n" in rerun_text or "\nstatus: draft\r\n---" in rerun_text
    assert "status: draft---" not in rerun_text
    # And `topic list` must still see the correct count
    descriptors = list_subtopics(cfg, "my-cluster")
    benchmarks = next(d for d in descriptors if d.slug == "benchmarks")
    assert benchmarks.paper_count == 2


def test_build_subtopic_notes_stable_numbering_on_rerun(tmp_path):
    cfg = _cfg(tmp_path)
    _write_note(cfg, "paper1", title="Paper One")
    _write_note(cfg, "paper2", title="Paper Two")
    apply_assignments(cfg, "my-cluster", {"paper1": ["benchmarks"], "paper2": ["agent-interfaces"]})
    build_subtopic_notes(cfg, "my-cluster")

    apply_assignments(cfg, "my-cluster", {"paper1": ["benchmarks"], "paper2": []})
    build_subtopic_notes(cfg, "my-cluster")

    topics_dir = cfg.raw / "my-cluster" / "topics"
    assert (topics_dir / "01_agent-interfaces.md").exists()
    assert (topics_dir / "02_benchmarks.md").exists()


def test_list_subtopics_reads_topics_folder(tmp_path):
    cfg = _cfg(tmp_path)
    _write_note(cfg, "paper1", title="Paper One")
    _write_note(cfg, "paper2", title="Paper Two")
    _write_note(cfg, "paper3", title="Paper Three")
    apply_assignments(
        cfg,
        "my-cluster",
        {
            "paper1": ["benchmarks"],
            "paper2": ["agent-interfaces"],
            "paper3": ["evaluation-methods"],
        },
    )
    build_subtopic_notes(cfg, "my-cluster")

    descriptors = list_subtopics(cfg, "my-cluster")

    assert len(descriptors) == 3
    assert [item.slug for item in descriptors] == ["agent-interfaces", "benchmarks", "evaluation-methods"]


def test_list_subtopics_returns_empty_when_no_folder(tmp_path):
    cfg = _cfg(tmp_path)

    assert list_subtopics(cfg, "my-cluster") == []
