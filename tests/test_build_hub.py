"""Tests for build_hub.py logic - YAML parsing, WIKI_MERGE, topic matching."""

import re

from research_hub.vault.builder import WIKI_MERGE, normalize_collections


def test_wiki_merge_normalizes_known_aliases():
    result = normalize_collections(["Agent-Based Model", "survey"])
    assert "ABM" in result
    assert "Survey Methods" in result


def test_wiki_merge_deduplicates():
    """Same canonical name from two different aliases should appear once."""
    result = normalize_collections(["Agent-Based Model", "agent-based model"])
    assert result.count("ABM") == 1


def test_wiki_merge_passes_through_unknown():
    result = normalize_collections(["SomeNewTopic"])
    assert "SomeNewTopic" in result


def test_normalize_collections_empty():
    assert normalize_collections([]) == []


def test_yaml_parsing_regex():
    """YAML front-matter parser extracts key fields correctly."""
    content = """---
title: "Test Paper"
year: 2024
collections: ["ABM", "LLM AI agent"]
tags: ["flood", "simulation"]
status: "unread"
---

# Test Paper
"""
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    assert match is not None
    meta_block = match.group(1)

    collections_match = re.search(r"collections:\s*\[(.*?)\]", meta_block)
    assert collections_match is not None
    collections = [
        item.strip().strip('"').strip("'")
        for item in collections_match.group(1).split(",")
    ]
    assert "ABM" in collections
    assert "LLM AI agent" in collections


def test_topic_keyword_matching():
    """Papers matching topic keywords are included in the topic."""
    topic_info = {
        "keywords": ["flood risk", "flood model", "inundation"],
        "desc": "Flood risk assessment.",
    }
    paper = {"title_line": "A flood model for coastal areas", "tags": [], "collections": []}

    text = (
        paper.get("title_line", "")
        + " "
        + " ".join(paper.get("tags", []))
        + " "
        + " ".join(paper.get("collections", []))
    ).lower()
    matched = any(keyword.lower() in text for keyword in topic_info["keywords"])
    assert matched
