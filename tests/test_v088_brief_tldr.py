"""v0.88 #6 — brief mirror prepends TL;DR + cluster backlink."""

from __future__ import annotations

from types import SimpleNamespace

from research_hub.notebooklm.download import (
    _build_tldr_and_cluster_block,
    _find_executive_summary,
    _first_paragraph,
)


def _art(text: str) -> SimpleNamespace:
    return SimpleNamespace(text=text)


def test_extracts_executive_summary_when_present() -> None:
    text = """# Brief

## Executive Summary

Multi-agent LLM systems can outperform classical baselines on
flood risk assessment when given heterogeneous urban data.

## Detailed Analysis
..."""
    body = _find_executive_summary(text)
    assert "multi-agent" in body.lower() or "Multi-agent" in body


def test_extracts_alternate_headings_in_priority_order() -> None:
    for heading in ("Overview", "Key Themes", "Key Findings"):
        text = f"# Brief\n\n## {heading}\n\nThis is the {heading} body.\n\n## Other\nstuff"
        body = _find_executive_summary(text)
        assert heading in body or f"This is the {heading}" in body


def test_executive_summary_wins_over_other_headings() -> None:
    text = """# Brief

## Overview

Overview body content here.

## Executive Summary

Executive Summary content."""
    body = _find_executive_summary(text)
    # Executive Summary appears in the priority list FIRST
    assert "Executive Summary" in body or "Executive" in body


def test_first_paragraph_fallback_skips_headings() -> None:
    text = "# Brief\n\n## Section\n\nThe actual first paragraph of the body."
    assert _first_paragraph(text) == "The actual first paragraph of the body."


def test_tldr_block_includes_cluster_backlink() -> None:
    art = _art("## Executive Summary\n\nSome substantive content.\n\n## Next")
    block = _build_tldr_and_cluster_block(art, "demo-cluster")
    assert "## TL;DR" in block
    assert "Some substantive content" in block
    assert "**Cluster:** [[demo-cluster/00_overview|demo-cluster]]" in block


def test_tldr_block_truncates_long_summary() -> None:
    long_text = "A" * 2000
    art = _art(f"## Executive Summary\n\n{long_text}\n\n## Next")
    block = _build_tldr_and_cluster_block(art, "demo")
    # 500 char cap + "..." marker
    assert "..." in block
    # The TL;DR body itself should be at most ~500 chars
    tldr_start = block.find("## TL;DR")
    cluster_start = block.find("**Cluster:**")
    tldr_body = block[tldr_start:cluster_start]
    assert len(tldr_body) < 700  # 500 chars + "## TL;DR\n\n" + truncation marker


def test_tldr_block_handles_empty_brief() -> None:
    art = _art("")
    block = _build_tldr_and_cluster_block(art, "demo")
    # Always present a TL;DR header + cluster backlink, even on empty brief
    assert "## TL;DR" in block
    assert "**Cluster:** [[demo/00_overview|demo]]" in block


def test_tldr_block_handles_brief_with_no_recognised_heading() -> None:
    art = _art("# Brief\n\nJust some flat prose with no section headings.")
    block = _build_tldr_and_cluster_block(art, "demo")
    assert "## TL;DR" in block
    # Falls back to first paragraph
    assert "flat prose" in block
