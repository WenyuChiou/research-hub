"""Tests for research_hub.zotero.fetch helpers."""

from research_hub.zotero.fetch import (
    extract_item_data,
    make_raw_md,
    safe_filename,
    tags_to_wiki_links,
)


def test_safe_filename_basic():
    result = safe_filename("Smith, John", "2024", "A study of flood risk perception")

    assert result == "smith2024-study-flood-risk-perception.md"


def test_safe_filename_handles_missing_year_and_author():
    result = safe_filename("", "", "Untitled draft")

    assert result == "unknownnd-untitled-draft.md"


def test_safe_filename_strips_stopwords():
    result = safe_filename("Doe, Jane", "2024", "The Role of the Agent in a Model")

    assert result == "doe2024-role-agent-model.md"


def test_extract_item_data_skips_attachments():
    assert extract_item_data({"data": {"itemType": "attachment"}}) is None


def test_extract_item_data_basic_fields():
    item = {
        "key": "ABCD1234",
        "data": {
            "itemType": "journalArticle",
            "title": "Flood Risk and Protection Motivation",
            "creators": [
                {"creatorType": "author", "firstName": "Jane", "lastName": "Doe"},
                {"creatorType": "author", "name": "Research Group"},
            ],
            "date": "2024-01-15",
            "publicationTitle": "Risk Journal",
            "DOI": "10.1000/example",
            "url": "https://example.com/paper",
            "abstractNote": "Abstract text",
            "tags": [{"tag": "PMT"}, {"tag": "flood risk"}],
        },
    }

    result = extract_item_data(item)

    assert result == {
        "key": "ABCD1234",
        "item_type": "journalArticle",
        "title": "Flood Risk and Protection Motivation",
        "authors": ["Doe, Jane", "Research Group"],
        "year": "2024",
        "journal": "Risk Journal",
        "doi": "10.1000/example",
        "url": "https://example.com/paper",
        "abstract": "Abstract text",
        "tags": ["PMT", "flood risk"],
    }


def test_tags_to_wiki_links_maps_known_terms():
    links = tags_to_wiki_links(["PMT", "flood risk"])

    assert "[[Protection-Motivation-Theory]]" in links
    assert "[[Flood-Risk]]" in links


def test_tags_to_wiki_links_empty_for_unknown():
    assert tags_to_wiki_links(["unmapped topic"]) == []


def test_make_raw_md_contains_yaml_frontmatter():
    item_data = {
        "key": "ABCD1234",
        "title": "Flood Risk and Protection Motivation",
        "authors": ["Doe, Jane"],
        "year": "2024",
        "journal": "Risk Journal",
        "doi": "10.1000/example",
        "abstract": "Abstract text",
        "tags": ["PMT", "flood risk"],
    }

    markdown = make_raw_md(item_data, ["Survey Papers"], ["Important note"])

    assert markdown.startswith('---\ntitle: "Flood Risk and Protection Motivation"')
    assert "zotero-key: ABCD1234" in markdown
    assert "\n## Abstract\n\nAbstract text\n" in markdown
