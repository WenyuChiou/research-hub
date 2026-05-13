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


def test_first_paragraph_skips_archive_metadata_header() -> None:
    """v0.88.3 regression — TL;DR was grabbing `Source: <url>` /
    `Downloaded: <ts>` / `Sources: <n>` archive header instead of the
    synthesis intro, leaving readers staring at download receipts on
    mobile.
    """
    text = (
        "# Cluster Title\n\n"
        "Source: https://notebooklm.google.com/notebook/xyz\n"
        "Downloaded: 20260513T041410Z\n"
        "Sources: 12\n"
        "Saved briefings: Briefing Doc\n\n"
        "# Comparative Analysis of AI-Driven Frameworks\n\n"
        "### 1. Thematic Synthesis: Limitations of Conventional Models\n"
        "The current paradigm in flood risk management is bifurcated between "
        "hydrodynamic simulations and data-driven ML approaches.\n\n"
        "**Table 1: Comparative Analysis**\n"
    )
    para = _first_paragraph(text)
    assert "Source:" not in para
    assert "Downloaded:" not in para
    assert "Sources:" not in para
    assert "current paradigm" in para or "hydrodynamic" in para


def test_tldr_skips_table_separator_and_bold_label_lines() -> None:
    """Tables and bold-only label paragraphs shouldn't surface as TL;DR
    body — they read like noise on mobile."""
    text = (
        "# Brief\n\n"
        "| Col A | Col B |\n| :--- | :--- |\n| x | y |\n\n"
        "**Bold label only**\n\n"
        "This is the first real prose paragraph that should be selected.\n"
    )
    para = _first_paragraph(text)
    assert "first real prose paragraph" in para
    assert "| Col" not in para


def test_tldr_block_with_archive_header_uses_synthesis_prose() -> None:
    """End-to-end: when artifact text begins with the NLM archive header
    block, the TL;DR block should still surface synthesis content, not
    the download receipt."""
    art = _art(
        "# Cluster\n\n"
        "Source: https://example/notebook/xyz\n"
        "Downloaded: 20260513T041410Z\n"
        "Sources: 12\n"
        "Saved briefings: Briefing Doc\n\n"
        "# Synthesis Title\n\n"
        "The synthesis body actually discusses substantive findings here.\n"
    )
    block = _build_tldr_and_cluster_block(art, "demo")
    assert "Downloaded:" not in block
    assert "synthesis body" in block
