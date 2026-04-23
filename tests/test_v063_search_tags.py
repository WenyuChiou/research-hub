from __future__ import annotations

from research_hub.discover import _to_papers_input
from research_hub.pipeline import _compose_hub_tags
from research_hub.search.arxiv_backend import ArxivBackend
from research_hub.search.base import SearchResult


def test_arxiv_backend_extracts_categories():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2604.12345v1</id>
    <published>2026-04-23T00:00:00Z</published>
    <title>Example</title>
    <summary>Abstract</summary>
    <author><name>Jane Doe</name></author>
    <category term="cs.AI" />
    <category term="cs.CL" />
  </entry>
</feed>
"""
    results = ArxivBackend(delay_seconds=0)._parse_feed(xml)
    assert results[0].categories == ["cs.AI", "cs.CL"]


def test_semantic_scholar_extracts_publication_types():
    result = SearchResult.from_s2_json(
        {
            "title": "Paper",
            "publicationTypes": ["Review", "JournalArticle"],
            "authors": [{"name": "Jane Doe"}],
            "externalIds": {},
        }
    )
    assert result.publication_types == ["Review", "JournalArticle"]


def test_to_papers_input_adds_category_tags():
    papers = _to_papers_input(
        [
            {
                "title": "Paper",
                "authors": ["Jane Doe"],
                "year": 2026,
                "categories": ["cs.AI"],
            }
        ],
        "alpha",
    )
    assert "category/cs.AI" in papers[0]["tags"]


def test_to_papers_input_adds_type_tags():
    papers = _to_papers_input(
        [
            {
                "title": "Paper",
                "authors": ["Jane Doe"],
                "year": 2026,
                "publication_types": ["Review"],
            }
        ],
        "alpha",
    )
    assert "type/Review" in papers[0]["tags"]


def test_compose_hub_tags_preserves_category_tags():
    tags = _compose_hub_tags({"tags": ["category/cs.AI"]}, "alpha")
    assert "category/cs.AI" in tags
