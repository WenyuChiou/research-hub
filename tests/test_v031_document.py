"""v0.31 Track A: Document base class tests."""

from __future__ import annotations

import pytest
import yaml

from research_hub.document import Document, Paper, parse_source_kind


def test_document_to_frontmatter_minimal():
    doc = Document(
        slug="my-pdf-2024",
        title="A Random PDF",
        source_kind="pdf",
        ingestion_source="import-folder",
    )

    frontmatter = doc.to_frontmatter()

    assert frontmatter["title"] == "A Random PDF"
    assert frontmatter["source_kind"] == "pdf"
    assert frontmatter["slug"] == "my-pdf-2024"
    assert "ingested_at" in frontmatter
    assert frontmatter["labels"] == []
    assert "doi" not in frontmatter


def test_document_rejects_invalid_source_kind():
    with pytest.raises(ValueError, match="source_kind"):
        Document(slug="x", title="x", source_kind="not_a_kind")


def test_paper_inherits_document():
    paper = Paper(
        slug="smith2024-foo",
        title="A Paper",
        source_kind="paper",
        doi="10.1234/foo",
        authors=[{"firstName": "John", "lastName": "Smith"}],
        year=2024,
    )

    assert isinstance(paper, Document)
    assert paper.source_kind == "paper"


def test_paper_frontmatter_includes_doi_and_authors():
    paper = Paper(
        slug="smith2024-foo",
        title="A Paper",
        source_kind="paper",
        doi="10.1234/foo",
        authors=[{"firstName": "John", "lastName": "Smith"}],
        year=2024,
        journal="Nature",
    )

    frontmatter = paper.to_frontmatter()

    assert frontmatter["doi"] == "10.1234/foo"
    assert "Smith, John" in frontmatter["authors"]
    assert frontmatter["year"] == 2024
    assert frontmatter["journal"] == "Nature"
    assert frontmatter["source_kind"] == "paper"


def test_parse_source_kind_defaults_to_paper_when_missing():
    legacy_frontmatter = {
        "title": "An Old Paper",
        "doi": "10.1/old",
        "authors": "Smith, John",
        "year": 2020,
    }
    assert parse_source_kind(legacy_frontmatter) == "paper"

    new_frontmatter = {"source_kind": "pdf", "title": "New PDF"}
    assert parse_source_kind(new_frontmatter) == "pdf"

    assert parse_source_kind({"source_kind": ""}) == "paper"
    assert parse_source_kind({"source_kind": None}) == "paper"


def test_document_markdown_roundtrip_preserves_frontmatter():
    doc = Document(
        slug="test-doc",
        title="Test Doc",
        source_kind="markdown",
        labels=["seed"],
        tags=["important"],
    )

    markdown = doc.to_markdown(body="# Hello\n\nSome content.")

    assert markdown.startswith("---\n")
    parts = markdown.split("---", 2)
    assert len(parts) == 3

    frontmatter = yaml.safe_load(parts[1])
    assert frontmatter["title"] == "Test Doc"
    assert frontmatter["source_kind"] == "markdown"
    assert frontmatter["labels"] == ["seed"]
    assert "Hello" in parts[2]
