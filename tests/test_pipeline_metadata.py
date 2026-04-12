"""Tests for pipeline metadata handling: authors dict format, volume/issue/pages."""

from __future__ import annotations

from research_hub.pipeline import _render_obsidian_note, _validate_paper_input


def test_render_obsidian_note_handles_dict_authors():
    pp = {
        "title": "Test Paper",
        "year": 2025,
        "journal": "Test Journal",
        "doi": "10.1234/test",
        "abstract": "An abstract.",
        "tags": ["test"],
        "authors": [
            {"creatorType": "author", "firstName": "Wen-Yu", "lastName": "Chang"},
            {"creatorType": "author", "firstName": "Ethan", "lastName": "Yang"},
        ],
        "summary": "summary",
        "key_findings": ["finding"],
        "methodology": "method",
        "relevance": "relevance",
        "slug": "test-paper",
        "sub_category": "test",
    }

    rendered = _render_obsidian_note(pp, "TEST_COL", "test-cluster", "query")

    assert "Chang, Wen-Yu" in rendered
    assert "Yang, Ethan" in rendered
    assert 'authors: "Chang, Wen-Yu; Yang, Ethan"' in rendered


def test_render_obsidian_note_handles_string_authors():
    pp = {
        "title": "Test",
        "year": 2024,
        "journal": "J",
        "doi": "10.1/x",
        "abstract": "",
        "tags": [],
        "authors": ["Wen-Yu Chang", "Ethan Yang"],
        "summary": "",
        "key_findings": [],
        "methodology": "",
        "relevance": "",
        "slug": "test",
        "sub_category": "test",
    }

    rendered = _render_obsidian_note(pp, "C", None, None)

    assert 'authors: "Wen-Yu Chang; Ethan Yang"' in rendered


def test_render_obsidian_note_emits_volume_issue_pages():
    pp = {
        "title": "T",
        "year": 2025,
        "journal": "J",
        "doi": "10.1/x",
        "abstract": "",
        "tags": [],
        "authors": [],
        "volume": "12",
        "issue": "3",
        "pages": "100-120",
        "summary": "",
        "key_findings": [],
        "methodology": "",
        "relevance": "",
        "slug": "t",
        "sub_category": "test",
    }

    rendered = _render_obsidian_note(pp, "C", "cluster", "q")

    assert 'volume: "12"' in rendered
    assert 'issue: "3"' in rendered
    assert 'pages: "100-120"' in rendered
    assert "**Citation:** J, 12(3), 100-120" in rendered


def test_validate_missing_creator_type():
    errors = _validate_paper_input(
        {
            "title": "T",
            "doi": "10.1/x",
            "year": 2025,
            "authors": [{"firstName": "Foo", "lastName": "Bar"}],
        },
        0,
    )

    assert any("creatorType" in error for error in errors)


def test_validate_missing_required_field():
    errors = _validate_paper_input({"title": "T", "doi": "10.1/x"}, 0)

    assert any("year" in error for error in errors)
    assert any("authors" in error for error in errors)


def test_validate_authors_must_be_list():
    errors = _validate_paper_input(
        {
            "title": "T",
            "doi": "10.1/x",
            "year": 2025,
            "authors": "Wen-Yu",
        },
        0,
    )

    assert any("must be a list" in error for error in errors)


def test_validate_passes_correct_input():
    errors = _validate_paper_input(
        {
            "title": "T",
            "doi": "10.1/x",
            "year": 2025,
            "authors": [{"creatorType": "author", "firstName": "F", "lastName": "L"}],
        },
        0,
    )

    assert errors == []
