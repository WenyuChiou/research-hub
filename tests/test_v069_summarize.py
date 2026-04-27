"""v0.69.0 — paper-summarize feature.

Generates per-paper Key Findings + Methodology + Relevance via LLM CLI,
writes to BOTH Obsidian markdown AND Zotero child note.

Tests cover:
  - Prompt builder includes papers + abstracts in expected shape
  - Validator rejects unknown paper_slug, empty fields, wrong types
  - Apply path writes Obsidian markdown blocks + Zotero child note
  - Apply path rolls back markdown when Zotero write fails (sync invariant)
  - summarize_cluster gracefully saves prompt when no LLM CLI on PATH
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from research_hub.summarize import (
    PaperSummary,
    SummaryApplyResult,
    SummaryReport,
    _read_cluster_papers_with_abstracts,
    _validate_entry,
    apply_summaries,
    build_summarize_prompt,
    summarize_cluster,
)


# --- fixtures -----------------------------------------------------------


def _write_paper_md(path, slug, title, abstract, zotero_key="ZK1"):
    body = f"""---
title: "{title}"
year: 2024
doi: "10.1/{slug}"
zotero-key: {zotero_key}
---

# {title}

## Abstract

{abstract}

---

## Summary

> [!abstract]
> [TODO] {title}
^summary

## Key Findings

> [!success]
> - [TODO: fill from abstract]
^findings

## Methodology

> [!info]
> [TODO: fill from abstract]
^methodology

## Relevance

> [!note]
> [TODO: fill relevance to cluster]
^relevance
"""
    path.write_text(body, encoding="utf-8")


@pytest.fixture
def cfg(tmp_path):
    raw = tmp_path / "raw" / "test-cluster"
    raw.mkdir(parents=True)
    research_hub_dir = tmp_path / ".research_hub"
    research_hub_dir.mkdir()
    _write_paper_md(raw / "alice2024-paper-one.md", "alice2024-paper-one",
                    "Paper One", "Households relocate after major floods.", zotero_key="ZK1")
    _write_paper_md(raw / "bob2025-paper-two.md", "bob2025-paper-two",
                    "Paper Two", "Surveys show female-headed households relocate less.", zotero_key="ZK2")
    return SimpleNamespace(
        raw=raw.parent,
        research_hub_dir=research_hub_dir,
    )


# --- prompt building ----------------------------------------------------


def test_build_summarize_prompt_includes_all_papers_with_abstracts(cfg):
    prompt = build_summarize_prompt(cfg, "test-cluster")
    assert "Paper One" in prompt
    assert "Paper Two" in prompt
    assert "Households relocate after major floods." in prompt
    assert "alice2024-paper-one" in prompt
    assert "bob2025-paper-two" in prompt
    # Output schema is in the prompt as a JSON code block
    assert "summaries" in prompt
    assert "key_findings" in prompt
    assert "relevance" in prompt


def test_build_summarize_prompt_raises_on_unknown_cluster(cfg):
    with pytest.raises(ValueError, match="no papers found"):
        build_summarize_prompt(cfg, "does-not-exist")


def test_read_papers_skips_overview_and_index(cfg, tmp_path):
    (cfg.raw / "test-cluster" / "00_overview.md").write_text("---\ntype: overview\n---\nx", encoding="utf-8")
    (cfg.raw / "test-cluster" / "index.md").write_text("---\ntype: index\n---\nx", encoding="utf-8")
    papers = _read_cluster_papers_with_abstracts(cfg, "test-cluster")
    slugs = {p["slug"] for p in papers}
    assert "00_overview" not in slugs
    assert "index" not in slugs
    assert len(papers) == 2


# --- validation ---------------------------------------------------------


def test_validate_entry_rejects_unknown_paper_slug():
    valid_slugs = {"alice2024-paper-one"}
    summary, reason = _validate_entry(
        {"paper_slug": "unknown-slug", "key_findings": ["x"], "methodology": "m", "relevance": "r"},
        valid_slugs,
    )
    assert summary is None
    assert "unknown" in reason


def test_validate_entry_rejects_empty_findings():
    valid_slugs = {"alice2024-paper-one"}
    summary, reason = _validate_entry(
        {"paper_slug": "alice2024-paper-one", "key_findings": [], "methodology": "m", "relevance": "r"},
        valid_slugs,
    )
    assert summary is None
    assert "empty" in reason


def test_validate_entry_rejects_non_list_findings():
    valid_slugs = {"alice2024-paper-one"}
    summary, reason = _validate_entry(
        {"paper_slug": "alice2024-paper-one", "key_findings": "not a list",
         "methodology": "m", "relevance": "r"},
        valid_slugs,
    )
    assert summary is None
    assert "list" in reason


def test_validate_entry_accepts_well_formed_payload():
    valid_slugs = {"alice2024-paper-one"}
    summary, reason = _validate_entry(
        {"paper_slug": "alice2024-paper-one",
         "key_findings": ["Households relocate after floods.", "Tenure security predicts relocation."],
         "methodology": "Multivariate probit on 1200 households.",
         "relevance": "Empirical anchor for cluster's ABM papers."},
        valid_slugs,
    )
    assert reason is None
    assert isinstance(summary, PaperSummary)
    assert summary.paper_slug == "alice2024-paper-one"
    assert len(summary.key_findings) == 2
    assert summary.methodology.startswith("Multivariate")


# --- apply: writes ------------------------------------------------------


def _make_zot_with_existing_note():
    """MagicMock(spec=...) so the unwrap path in get_client doesn't trip."""
    zot = MagicMock(spec=["children", "update_item", "create_items", "item_template"])
    zot.children.return_value = [
        {"data": {"key": "NK1", "itemType": "note", "note": "old note", "parentItem": "ZK1"}}
    ]
    zot.update_item.return_value = {"successful": {"0": {"key": "NK1"}}}
    return zot


def test_apply_summaries_writes_obsidian_markdown_blocks(cfg):
    payload = {
        "summaries": [{
            "paper_slug": "alice2024-paper-one",
            "key_findings": ["Finding A.", "Finding B.", "Finding C."],
            "methodology": "Survey of 1200.",
            "relevance": "Anchor for cluster ABM models.",
        }]
    }
    zot = _make_zot_with_existing_note()
    result = apply_summaries(cfg, "test-cluster", payload, zot=zot)

    assert "alice2024-paper-one" in result.applied
    assert result.obsidian_writes == 1
    assert result.zotero_writes == 1

    md = (cfg.raw / "test-cluster" / "alice2024-paper-one.md").read_text(encoding="utf-8")
    assert "Finding A." in md
    assert "Finding B." in md
    assert "Finding C." in md
    assert "Survey of 1200." in md
    assert "Anchor for cluster ABM models." in md
    # TODO markers were replaced
    assert "[TODO: fill from abstract]" not in md
    assert "[TODO: fill relevance to cluster]" not in md


def test_apply_summaries_writes_zotero_child_note(cfg):
    payload = {"summaries": [{
        "paper_slug": "alice2024-paper-one",
        "key_findings": ["A finding."],
        "methodology": "ABM.",
        "relevance": "On-topic.",
    }]}
    zot = _make_zot_with_existing_note()
    result = apply_summaries(cfg, "test-cluster", payload, zot=zot)

    zot.update_item.assert_called_once()
    written = zot.update_item.call_args[0][0]
    assert "<h1>Summary</h1>" in written["note"]
    assert "<li>A finding.</li>" in written["note"]
    assert "ABM." in written["note"]
    assert "On-topic." in written["note"]
    assert result.zotero_writes == 1


def test_apply_summaries_creates_note_when_no_child_exists(cfg):
    """If a paper has no child note yet, create one."""
    payload = {"summaries": [{
        "paper_slug": "alice2024-paper-one",
        "key_findings": ["x"], "methodology": "y", "relevance": "z",
    }]}
    zot = MagicMock(spec=["children", "update_item", "create_items", "item_template"])
    zot.children.return_value = []  # no existing note
    zot.item_template.return_value = {"itemType": "note", "note": "", "parentItem": ""}
    zot.create_items.return_value = {"successful": {"0": {"key": "NEW_NOTE"}}}

    result = apply_summaries(cfg, "test-cluster", payload, zot=zot)
    assert result.zotero_writes == 1
    zot.create_items.assert_called_once()


# --- apply: rollback invariant ------------------------------------------


def test_apply_summaries_rolls_back_markdown_on_zotero_failure(cfg):
    """If Zotero write fails for a paper, that paper's markdown change must
    be reverted so Obsidian + Zotero stay in sync. Other papers still apply."""
    payload = {"summaries": [{
        "paper_slug": "alice2024-paper-one",
        "key_findings": ["should rollback"],
        "methodology": "x", "relevance": "y",
    }]}
    md_path = cfg.raw / "test-cluster" / "alice2024-paper-one.md"
    original = md_path.read_text(encoding="utf-8")

    zot = MagicMock(spec=["children", "update_item", "create_items", "item_template"])
    zot.children.return_value = [
        {"data": {"key": "NK1", "itemType": "note", "note": "old", "parentItem": "ZK1"}}
    ]
    zot.update_item.side_effect = RuntimeError("zotero exploded")

    result = apply_summaries(cfg, "test-cluster", payload, zot=zot)

    assert result.applied == []
    assert any("zotero write failed" in e for e in result.errors)
    # Markdown must be restored to its original state
    assert md_path.read_text(encoding="utf-8") == original


def test_apply_summaries_skips_paper_with_no_zotero_key_in_frontmatter(cfg, tmp_path):
    """A paper missing zotero-key in frontmatter has no Zotero anchor;
    rather than write Obsidian-only and silently desync, skip it."""
    bad_path = cfg.raw / "test-cluster" / "noid2024-no-key.md"
    bad_path.write_text("""---
title: "No key paper"
year: 2024
---

## Abstract

x

## Key Findings

> [!success]
> - [TODO: fill from abstract]
^findings

## Methodology

> [!info]
> [TODO: fill from abstract]
^methodology

## Relevance

> [!note]
> [TODO: fill relevance to cluster]
^relevance
""", encoding="utf-8")
    original = bad_path.read_text(encoding="utf-8")
    payload = {"summaries": [{
        "paper_slug": "noid2024-no-key",
        "key_findings": ["x"], "methodology": "y", "relevance": "z",
    }]}
    zot = _make_zot_with_existing_note()
    result = apply_summaries(cfg, "test-cluster", payload, zot=zot)

    assert any("no zotero-key" in e for e in result.errors)
    # Markdown reverted
    assert bad_path.read_text(encoding="utf-8") == original


# --- orchestration ------------------------------------------------------


def test_summarize_cluster_saves_prompt_when_no_llm_cli(cfg, monkeypatch):
    """When detect_llm_cli returns None, the prompt is saved to artifacts/
    and the report has prompt_path set (best-effort fallback, ok=True)."""
    monkeypatch.setattr("research_hub.auto.detect_llm_cli", lambda: None)
    report = summarize_cluster(cfg, "test-cluster")
    assert report.ok is True
    assert report.prompt_path is not None
    assert report.prompt_path.exists()
    assert report.cli_used == ""
    assert "summaries" in report.prompt_path.read_text(encoding="utf-8")


def test_summarize_cluster_uses_detected_cli_when_no_override(cfg, monkeypatch):
    monkeypatch.setattr("research_hub.auto.detect_llm_cli", lambda: "claude")
    monkeypatch.setattr(
        "research_hub.auto._invoke_llm_cli",
        lambda cli, prompt: '{"summaries": []}',
    )
    report = summarize_cluster(cfg, "test-cluster", apply=False)
    assert report.ok is True
    assert report.cli_used == "claude"
    # apply=False so no apply_result
    assert report.apply_result is None


def test_summarize_cluster_explicit_cli_override(cfg, monkeypatch):
    """Passing llm_cli should bypass detect_llm_cli."""
    monkeypatch.setattr("research_hub.auto.detect_llm_cli", lambda: None)  # would skip
    monkeypatch.setattr(
        "research_hub.auto._invoke_llm_cli",
        lambda cli, prompt: '{"summaries": []}',
    )
    report = summarize_cluster(cfg, "test-cluster", llm_cli="codex")
    assert report.cli_used == "codex"
    assert report.ok is True


def test_summarize_cluster_reports_error_on_unparseable_json(cfg, monkeypatch):
    monkeypatch.setattr("research_hub.auto.detect_llm_cli", lambda: "claude")
    monkeypatch.setattr(
        "research_hub.auto._invoke_llm_cli",
        lambda cli, prompt: "this is not JSON at all",
    )
    report = summarize_cluster(cfg, "test-cluster", apply=False)
    assert report.ok is False
    assert "JSON" in report.error


# --- to_dict ------------------------------------------------------------


def test_summary_report_to_dict_serializes_path():
    """SummaryReport.to_dict must convert Path to str so MCP-tool JSON
    serialization works."""
    from pathlib import Path
    report = SummaryReport(
        cluster_slug="x",
        prompt_path=Path("/tmp/p.md"),
        apply_result=SummaryApplyResult(cluster_slug="x", applied=["a"]),
    )
    d = report.to_dict()
    assert d["cluster_slug"] == "x"
    assert d["prompt_path"] == str(Path("/tmp/p.md"))
    assert d["apply_result"]["applied"] == ["a"]
