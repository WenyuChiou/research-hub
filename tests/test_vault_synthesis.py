"""Tests for vault.synthesis cluster synthesis page generator."""

from __future__ import annotations

from pathlib import Path

from research_hub.vault.synthesis import (
    ClusterPaper,
    _author_short,
    _extract_bullets,
    _extract_section,
    _first_sentence,
    _llm_from_text,
    build_synthesis_markdown,
    parse_cluster_paper,
    synthesize_all_clusters,
    synthesize_cluster,
)


SAMPLE_NOTE = """---
title: "Flood Risk Perception in Rural Communities"
authors: "Smith, John; Doe, Jane"
year: 2024
journal: "Journal of Risk Research"
doi: "10.1000/example"
zotero-key: ABC123
tags: ["flood", "risk perception", "rural", "gpt-4"]
topic_cluster: "flood-risk-perception"
cluster_queries: ["flood risk perception"]
verified: false
status: deep-read
---

# Flood Risk Perception in Rural Communities

## Abstract

This paper studies flood risk perception among rural residents.

## Summary

Rural residents underestimate flood risk due to limited direct experience.

## Key Findings

- Risk perception is 30% lower than actual exposure
- Social networks mediate risk communication
- Protection motivation correlates with direct experience

## Methodology

Mixed-methods study with 500 household surveys followed by 30 interviews.

## Relevance

Open question: how do LLM-based agents simulate these perception biases?
"""


def _make_note(path: Path, content: str = SAMPLE_NOTE) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_extract_section_returns_section_body():
    body = "## Summary\n\nOne sentence.\n\n## Key Findings\n\n- a\n- b\n"
    assert _extract_section(body, "Summary").startswith("One sentence.")
    findings = _extract_section(body, "Key Findings")
    assert "- a" in findings
    assert "- b" in findings


def test_extract_section_empty_when_missing():
    assert _extract_section("no sections here", "Summary") == ""


def test_extract_bullets_filters_non_bullets():
    assert _extract_bullets("- first\ntext\n- second\n") == ["first", "second"]


def test_author_short_handles_one_two_many():
    assert _author_short("Smith, John") == "Smith"
    assert _author_short("Smith, John; Doe, Jane") == "Smith & Doe"
    assert _author_short("Smith, John; Doe, Jane; Wong, Li") == "Smith et al."
    assert _author_short("") == "Unknown"


def test_first_sentence_stops_at_period():
    assert _first_sentence("Hello world. More stuff.") == "Hello world."
    assert _first_sentence("") == ""
    assert _first_sentence("No punctuation here").startswith("No punctuation")


def test_llm_from_text_detects_tags_and_text():
    paper = ClusterPaper(slug="p", title="t", tags=["gemini"], summary="")
    assert _llm_from_text(paper) == "gemini"


def test_parse_cluster_paper_extracts_all_fields(tmp_path: Path):
    path = _make_note(tmp_path / "smith2024-flood-risk.md")
    paper = parse_cluster_paper(path)
    assert paper is not None
    assert paper.title == "Flood Risk Perception in Rural Communities"
    assert paper.year == "2024"
    assert paper.status == "deep-read"
    assert paper.summary.startswith("Rural residents")
    assert len(paper.key_findings) == 3
    assert "Protection motivation" in paper.key_findings[2]
    assert paper.methodology.startswith("Mixed-methods")


def test_parse_cluster_paper_returns_none_on_missing_frontmatter(tmp_path: Path):
    path = tmp_path / "broken.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Just a heading", encoding="utf-8")
    assert parse_cluster_paper(path) is None


def test_build_synthesis_markdown_contains_sections():
    paper = ClusterPaper(
        slug="smith2024",
        title="Sample Paper",
        authors="Smith, John",
        year="2024",
        status="unread",
        summary="A summary sentence.",
        key_findings=["Finding one", "Finding two"],
        methodology="Used surveys.",
        relevance="Applies to LLM simulation.",
    )
    output = build_synthesis_markdown(
        cluster_slug="test-cluster",
        cluster_name="Test Cluster",
        first_query="test query",
        papers=[paper],
    )
    assert "# Test Cluster - Synthesis" in output
    assert "**First query:** test query" in output
    assert "## Collated Summaries" in output
    assert "## Collated Key Findings" in output
    assert "## Methodology Comparison" in output
    assert "A summary sentence." in output
    assert "Finding one" in output
    assert "```dataview" in output


def test_build_synthesis_markdown_orders_newest_year_first():
    older = ClusterPaper(slug="old", title="Old", authors="A, A", year="2021")
    newer = ClusterPaper(slug="new", title="New", authors="B, B", year="2024")
    output = build_synthesis_markdown("cluster", "Cluster", "query", [older, newer])
    assert output.index("B (2024) - New") < output.index("A (2021) - Old")


def test_synthesize_cluster_writes_output(tmp_path: Path):
    raw = tmp_path / "raw"
    hub = tmp_path / "hub"
    _make_note(raw / "test-cluster" / "smith2024-flood-risk.md")
    output = synthesize_cluster(
        cluster_slug="test-cluster",
        cluster_name="Test Cluster",
        first_query="flood risk perception in rural communities",
        raw_dir=raw,
        hub_dir=hub,
    )
    assert output.exists()
    content = output.read_text(encoding="utf-8")
    assert "# Test Cluster - Synthesis" in content
    assert "Smith & Doe (2024) - Flood Risk Perception in Rural Communities" in content
    assert "Rural residents underestimate" in content


def test_synthesize_cluster_raises_for_missing_folder(tmp_path: Path):
    raw = tmp_path / "raw"
    hub = tmp_path / "hub"
    try:
        synthesize_cluster("missing", "Missing", "query", raw, hub)
    except FileNotFoundError as exc:
        assert "No papers found for cluster" in str(exc)
    else:
        raise AssertionError("Expected FileNotFoundError")


def test_synthesize_all_clusters_skips_missing_folders(tmp_path: Path):
    clusters_file = tmp_path / "clusters.yaml"
    clusters_file.write_text(
        "clusters:\n"
        "  alpha:\n"
        "    name: Alpha\n"
        "    first_query: alpha query\n"
        "  beta:\n"
        "    name: Beta\n"
        "    first_query: beta query\n",
        encoding="utf-8",
    )
    raw = tmp_path / "raw"
    hub = tmp_path / "hub"
    _make_note(raw / "alpha" / "paper.md")
    outputs = synthesize_all_clusters(raw, hub, clusters_file)
    assert len(outputs) == 1
    assert outputs[0].name == "alpha-synthesis.md"
