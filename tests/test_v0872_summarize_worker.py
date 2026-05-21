from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from research_hub.paper import _parse_frontmatter
from research_hub.paper_summarize import (
    ParsedSummary,
    apply_parsed_summary_to_note,
    parse_summary_response,
    summarize_pending,
)


LONG_ABSTRACT = (
    "This abstract presents a mixed-methods study of flood adaptation, household "
    "water decisions, and institutional trust. It reports concrete findings "
    "from survey and interview data for a human-water systems cluster."
)


def _cfg(tmp_path: Path) -> SimpleNamespace:
    raw = tmp_path / "raw"
    raw.mkdir()
    return SimpleNamespace(raw=raw)


def _write_note(
    cfg: SimpleNamespace,
    cluster: str,
    slug: str,
    *,
    status: str = "pending",
    abstract: str = LONG_ABSTRACT,
) -> Path:
    path = Path(cfg.raw) / cluster / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""---
title: "{slug.title()}"
topic_cluster: "{cluster}"
summarize_status: {status}
---

# {slug.title()}

## Abstract

{abstract}

## Key Findings

> [!warning] Summary pending
> Run `research-hub paper summarize --pending` to fill this
> section from the abstract via paper-summarize.
^findings

## Methodology

> [!warning] Summary pending
> Run `research-hub paper summarize --pending` to fill this
> section from the abstract via paper-summarize.
^methodology

## Relevance

> [!warning] Summary pending
> Run `research-hub paper summarize --pending` to fill this
> section from the abstract via paper-summarize.
^relevance
""",
        encoding="utf-8",
    )
    return path


BACKEND_RESPONSE = """SUMMARY: The study links household water decisions to trust.

KEY_FINDINGS:
- Institutional trust predicts adaptation.
- Survey responses distinguish relocation and protection choices.
- Interview evidence explains the household decision process.

METHODOLOGY: Mixed-methods survey and interview study using household responses as the primary data.

RELEVANCE: It directly supports the human-water-llm cluster by grounding LLM agent behavior in human-water evidence.
"""


def test_summarize_pending_parses_response_into_four_sections(tmp_path: Path, monkeypatch) -> None:
    cfg = _cfg(tmp_path)
    note = _write_note(cfg, "human-water-llm", "paper-one")
    monkeypatch.setattr("research_hub.paper_summarize._invoke_backend", lambda backend, prompt: BACKEND_RESPONSE)

    results = summarize_pending(cfg, cluster_slug_filter="human-water-llm", backend="claude")

    assert [(r.path, r.action) for r in results] == [(note, "done")]
    text = note.read_text(encoding="utf-8")
    assert "## Summary" in text
    assert "Institutional trust predicts adaptation." in text
    assert "summarize_status: done" in text


def test_failed_no_abstract_path_does_not_call_backend(tmp_path: Path, monkeypatch) -> None:
    cfg = _cfg(tmp_path)
    note = _write_note(cfg, "cluster", "paper", abstract="(no abstract)")

    def fail_backend(backend: str, prompt: str) -> str:
        raise AssertionError("backend should not be called")

    monkeypatch.setattr("research_hub.paper_summarize._invoke_backend", fail_backend)

    results = summarize_pending(cfg, backend="claude")

    assert results[0].action == "failed_no_abstract"
    assert "summarize_status: failed_no_abstract" in note.read_text(encoding="utf-8")


def test_no_abstract_fallback_response_flips_status(tmp_path: Path, monkeypatch) -> None:
    cfg = _cfg(tmp_path)
    note = _write_note(cfg, "cluster", "paper")
    monkeypatch.setattr(
        "research_hub.paper_summarize._invoke_backend",
        lambda backend, prompt: "[no-abstract-fallback]",
    )

    results = summarize_pending(cfg, backend="claude")

    assert results[0].action == "failed_no_abstract"
    assert "summarize_status: failed_no_abstract" in note.read_text(encoding="utf-8")


def test_frontmatter_flipped_to_done_with_source_and_timestamp(tmp_path: Path, monkeypatch) -> None:
    cfg = _cfg(tmp_path)
    note = _write_note(cfg, "cluster", "paper")
    monkeypatch.setattr("research_hub.paper_summarize._invoke_backend", lambda backend, prompt: BACKEND_RESPONSE)

    summarize_pending(cfg, backend="codex")

    meta = _parse_frontmatter(note.read_text(encoding="utf-8"))
    assert meta["summarize_status"] == "done"
    assert meta["summarize_source"] == "codex"
    assert str(meta["summarized_at"]).endswith("Z")


def test_max_papers_is_honored(tmp_path: Path, monkeypatch) -> None:
    cfg = _cfg(tmp_path)
    _write_note(cfg, "cluster", "paper-one")
    _write_note(cfg, "cluster", "paper-two")
    monkeypatch.setattr("research_hub.paper_summarize._invoke_backend", lambda backend, prompt: BACKEND_RESPONSE)

    results = summarize_pending(cfg, backend="claude", max_papers=1)

    assert len(results) == 1
    statuses = [
        _parse_frontmatter(path.read_text(encoding="utf-8"))["summarize_status"]
        for path in sorted((Path(cfg.raw) / "cluster").glob("*.md"))
    ]
    assert statuses.count("done") == 1
    assert statuses.count("pending") == 1


@pytest.mark.parametrize("backend", ["claude", "codex", "gemini"])
def test_per_backend_dispatch(tmp_path: Path, monkeypatch, backend: str) -> None:
    cfg = _cfg(tmp_path)
    _write_note(cfg, "cluster", f"paper-{backend}")
    seen: list[str] = []

    def fake_backend(selected: str, prompt: str) -> str:
        seen.append(selected)
        return BACKEND_RESPONSE

    monkeypatch.setattr("research_hub.paper_summarize._invoke_backend", fake_backend)

    summarize_pending(cfg, backend=backend)

    assert seen == [backend]


def test_done_notes_are_skipped(tmp_path: Path, monkeypatch) -> None:
    cfg = _cfg(tmp_path)
    _write_note(cfg, "cluster", "paper", status="done")

    def fail_backend(backend: str, prompt: str) -> str:
        raise AssertionError("backend should not be called")

    monkeypatch.setattr("research_hub.paper_summarize._invoke_backend", fail_backend)

    assert summarize_pending(cfg, backend="claude") == []


def test_failed_no_abstract_is_retried_when_abstract_now_exists(tmp_path: Path, monkeypatch) -> None:
    cfg = _cfg(tmp_path)
    note = _write_note(cfg, "cluster", "paper", status="failed_no_abstract", abstract=LONG_ABSTRACT)
    monkeypatch.setattr("research_hub.paper_summarize._invoke_backend", lambda backend, prompt: BACKEND_RESPONSE)

    results = summarize_pending(cfg, backend="claude")

    assert results[0].action == "done"
    assert "summarize_status: done" in note.read_text(encoding="utf-8")


def test_dry_run_does_not_write_or_call_backend(tmp_path: Path, monkeypatch) -> None:
    cfg = _cfg(tmp_path)
    note = _write_note(cfg, "cluster", "paper")
    original = note.read_text(encoding="utf-8")

    def fail_backend(backend: str, prompt: str) -> str:
        raise AssertionError("backend should not be called")

    monkeypatch.setattr("research_hub.paper_summarize._invoke_backend", fail_backend)

    results = summarize_pending(cfg, backend="claude", dry_run=True)

    assert results[0].action == "would_summarize"
    assert note.read_text(encoding="utf-8") == original


def test_parse_summary_response_accepts_numbered_markdown() -> None:
    parsed = parse_summary_response(
        """1. SUMMARY: One sentence.
2. KEY_FINDINGS:
1. First claim.
2. Second claim.
3. METHODOLOGY: A survey study.
4. RELEVANCE: Connects to the cluster."""
    )

    assert parsed is not None
    assert parsed.summary == "One sentence."
    assert "- First claim." in parsed.key_findings
    assert parsed.methodology == "A survey study."


def test_apply_parsed_summary_adds_summary_before_abstract(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    note = _write_note(cfg, "cluster", "paper")
    text = note.read_text(encoding="utf-8")

    updated = apply_parsed_summary_to_note(
        text,
        ParsedSummary(
            summary="A concise summary.",
            key_findings="- Finding.",
            methodology="A method.",
            relevance="A relevance sentence.",
        ),
    )

    assert updated.index("## Summary") < updated.index("## Abstract")


# ---------------------------------------------------------------------------
# RELEVANCE prompt anti-generic guard (v1.1.0)
# ---------------------------------------------------------------------------

def test_prompt_template_relevance_anti_generic():
    """RELEVANCE instruction must forbid the generic 'This paper is relevant to...' form."""
    from research_hub.paper_summarize import PROMPT_TEMPLATE

    assert "Do NOT write" in PROMPT_TEMPLATE
    assert "SPECIFIC dimension" in PROMPT_TEMPLATE
