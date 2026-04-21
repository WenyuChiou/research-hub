from __future__ import annotations

import os
from pathlib import Path

import pytest

from research_hub.paper_schema import validate_paper_note


def _write_note(
    path: Path,
    *,
    doi: str = "10.1/example",
    summary: str = "A complete summary.",
    key_findings: str = "- Finding one.",
    methodology: str = "A complete methodology section.",
    relevance: str = "A complete relevance section.",
) -> Path:
    path.write_text(
        (
            "---\n"
            'title: "Example paper"\n'
            f'doi: "{doi}"\n'
            'authors: "Doe, Jane"\n'
            'year: "2025"\n'
            'topic_cluster: "my-cluster"\n'
            'status: "unread"\n'
            'ingested_at: "2026-04-14T00:00:00Z"\n'
            "---\n\n"
            "## Summary\n\n"
            f"{summary}\n\n"
            "## Key Findings\n\n"
            f"{key_findings}\n\n"
            "## Methodology\n\n"
            f"{methodology}\n\n"
            "## Relevance\n\n"
            f"{relevance}\n"
        ),
        encoding="utf-8",
    )
    return path


def test_validate_complete_note_returns_empty(tmp_path):
    path = _write_note(tmp_path / "paper.md")

    result = validate_paper_note(path)

    assert result.ok is True
    assert result.missing_frontmatter == []
    assert result.empty_sections == []
    assert result.todo_placeholders == []


def test_validate_missing_summary_flagged(tmp_path):
    path = _write_note(tmp_path / "paper.md", summary="")

    result = validate_paper_note(path)

    assert result.ok is False
    assert result.empty_sections == ["Summary"]


def test_validate_missing_required_frontmatter_field_flagged(tmp_path):
    path = _write_note(tmp_path / "paper.md", doi="")

    result = validate_paper_note(path)

    assert result.ok is False
    assert result.missing_frontmatter == ["doi"]
    assert result.severity == "fail"


def test_validate_todo_placeholders_flagged(tmp_path):
    path = _write_note(tmp_path / "paper.md", summary="[TODO: write summary]")

    result = validate_paper_note(path)

    assert result.ok is False
    assert result.todo_placeholders == ["Summary"]
    assert result.severity == "warn"


@pytest.mark.slow
def test_validate_live_cluster_notes():
    if os.environ.get("RESEARCH_HUB_RUN_LIVE_VAULT_TESTS") != "1":
        pytest.skip("set RESEARCH_HUB_RUN_LIVE_VAULT_TESTS=1 to validate live vault notes")
    vault = Path.home() / "knowledge-base" / "raw" / "llm-agents-software-engineering"
    if not vault.exists():
        pytest.skip("live vault not present")
    for note in sorted(vault.glob("*.md")):
        result = validate_paper_note(note)
        assert result.ok, (
            f"{note.name}: {result.missing_frontmatter=} "
            f"{result.empty_sections=} {result.todo_placeholders=}"
        )
