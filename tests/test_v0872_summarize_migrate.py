from __future__ import annotations

from pathlib import Path

from research_hub.vault.summarize_migrate import migrate_existing_to_pending_status
from research_hub.zotero.fetch import make_raw_md


LONG_ABSTRACT = (
    "This abstract describes a study of human water interactions with enough detail "
    "to clear the summary queue threshold and support paper-level extraction from "
    "the abstract alone."
)


def _write_note(
    path: Path,
    *,
    abstract: str = LONG_ABSTRACT,
    sections: str = "",
    status: str = "",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    status_line = f"summarize_status: {status}\n" if status else ""
    body_sections = sections or """
## Key Findings

> [!success]
> - Substantive finding about flood adaptation.
^findings

## Methodology

> [!info]
> Survey analysis of households and relocation outcomes.
^methodology

## Relevance

> [!note]
> Connects household water decisions to the cluster.
^relevance
"""
    path.write_text(
        f"""---
title: "Paper"
topic_cluster: "{path.parent.name}"
{status_line}---

# Paper

## Abstract

{abstract}

{body_sections}
""",
        encoding="utf-8",
    )


STICKY_SECTIONS = """
## Key Findings

- [review and extract from Abstract section above]

## Methodology

[review abstract; refine after reading PDF]

## Relevance

[TODO: fill relevance to cluster]
"""


def test_migrate_existing_flips_sticky_placeholder_to_pending(tmp_path: Path) -> None:
    note = tmp_path / "raw" / "human-water-llm" / "paper.md"
    _write_note(note, sections=STICKY_SECTIONS)

    results = migrate_existing_to_pending_status(tmp_path, dry_run=False)

    assert results == [(note, "pending")]
    text = note.read_text(encoding="utf-8")
    assert "summarize_status: pending" in text
    assert "Summary pending" in text
    assert "[review abstract; refine after reading PDF]" not in text


def test_migrate_existing_recognizes_substantive_content_as_done(tmp_path: Path) -> None:
    note = tmp_path / "raw" / "llm-agents-social" / "paper.md"
    _write_note(note)

    results = migrate_existing_to_pending_status(tmp_path, dry_run=False)

    assert results == [(note, "done")]
    assert "summarize_status: done" in note.read_text(encoding="utf-8")


def test_migrate_existing_sets_failed_no_abstract_when_abstract_short(tmp_path: Path) -> None:
    note = tmp_path / "raw" / "human-water-llm" / "paper.md"
    _write_note(note, abstract="(no abstract)", sections=STICKY_SECTIONS)

    results = migrate_existing_to_pending_status(tmp_path, dry_run=False)

    assert results == [(note, "failed_no_abstract")]
    text = note.read_text(encoding="utf-8")
    assert "summarize_status: failed_no_abstract" in text
    assert "Summary pending" in text
    assert "[TODO: fill relevance to cluster]" not in text


def test_migrate_existing_already_set_is_idempotent(tmp_path: Path) -> None:
    note = tmp_path / "raw" / "cluster" / "paper.md"
    _write_note(note, status="pending", sections=STICKY_SECTIONS)
    original = note.read_text(encoding="utf-8")

    results = migrate_existing_to_pending_status(tmp_path, dry_run=False)

    assert results == [(note, "already_set")]
    assert note.read_text(encoding="utf-8") == original


def test_migrate_existing_dry_run_does_not_write(tmp_path: Path) -> None:
    note = tmp_path / "raw" / "cluster" / "paper.md"
    _write_note(note, sections=STICKY_SECTIONS)
    original = note.read_text(encoding="utf-8")

    results = migrate_existing_to_pending_status(tmp_path, dry_run=True)

    assert results == [(note, "pending")]
    assert note.read_text(encoding="utf-8") == original


def test_migrate_existing_respects_cluster_filter(tmp_path: Path) -> None:
    target = tmp_path / "raw" / "target" / "paper.md"
    other = tmp_path / "raw" / "other" / "paper.md"
    _write_note(target, sections=STICKY_SECTIONS)
    _write_note(other, sections=STICKY_SECTIONS)

    results = migrate_existing_to_pending_status(tmp_path, cluster_slug_filter="target", dry_run=True)

    assert results == [(target, "pending")]


def test_make_raw_md_emits_summarize_status_pending_for_real_abstract() -> None:
    md = make_raw_md(
        {
            "title": "Paper",
            "authors": ["Doe, Jane"],
            "year": "2026",
            "journal": "",
            "doi": "",
            "abstract": LONG_ABSTRACT,
            "tags": [],
            "key": "K1",
        },
        [],
        [],
    )

    assert "summarize_status: pending" in md
    assert "## Key Findings" in md
    assert "Summary pending" in md


def test_make_raw_md_emits_failed_no_abstract_for_placeholder() -> None:
    md = make_raw_md(
        {
            "title": "Paper",
            "authors": [],
            "year": "2026",
            "journal": "",
            "doi": "",
            "abstract": "(no abstract)",
            "tags": [],
            "key": "K1",
        },
        [],
        [],
    )

    assert "summarize_status: failed_no_abstract" in md
