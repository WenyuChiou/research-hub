from __future__ import annotations

from research_hub import pipeline
from research_hub.zotero.client import check_duplicate


def test_validate_all_required_core_fields_reported():
    errors = pipeline._validate_paper_input({}, 0)

    assert any("missing required field 'title'" in err for err in errors)
    assert any("missing required field 'doi'" in err for err in errors)
    assert any("missing required field 'authors'" in err for err in errors)
    assert any("missing required field 'year'" in err for err in errors)


def test_validate_reports_missing_methodology_before_ingest():
    paper = {
        "title": "Paper",
        "doi": "10.1/x",
        "authors": ["Jane Doe"],
        "year": 2024,
        "abstract": "Abstract",
        "journal": "Journal",
        "summary": "Summary",
        "key_findings": ["One"],
        "relevance": "Relevant",
    }

    errors = pipeline._validate_paper_input(paper, 0)

    assert any("missing field 'methodology'" in err for err in errors)


def test_validate_reports_missing_key_findings_as_string_error():
    paper = {
        "title": "Paper",
        "doi": "10.1/x",
        "authors": ["Jane Doe"],
        "year": 2024,
        "abstract": "Abstract",
        "journal": "Journal",
        "summary": "Summary",
        "key_findings": "One",
        "methodology": "Survey",
        "relevance": "Relevant",
    }

    errors = pipeline._validate_paper_input(paper, 0)

    assert any("'key_findings' must be a list of strings" in err for err in errors)


def test_auto_generate_slug_from_first_author_year_title():
    paper = {
        "title": "A Study on LLM Agents",
        "authors": ["Jane Doe"],
        "year": 2024,
    }

    pipeline._auto_generate_missing_fields(paper, None)

    assert paper["slug"] == "doe2024-study-llm-agents"


def test_auto_generate_sub_category_uses_cluster_slug():
    paper = {"title": "Paper", "authors": ["Jane Doe"], "year": 2024}

    pipeline._auto_generate_missing_fields(paper, "llm-agents")

    assert paper["sub_category"] == "llm-agents"


def test_auto_generate_sub_category_uncategorized_when_no_cluster():
    paper = {"title": "Paper", "authors": ["Jane Doe"], "year": 2024}

    pipeline._auto_generate_missing_fields(paper, None)

    assert paper["sub_category"] == "uncategorized"


def test_auto_generate_does_not_clobber_existing_slug():
    paper = {"title": "Paper", "authors": ["Jane Doe"], "year": 2024, "slug": "keep-me"}

    pipeline._auto_generate_missing_fields(paper, None)

    assert paper["slug"] == "keep-me"


class _StubZot:
    def __init__(self):
        self.library_calls = []
        self.collection_calls = []

    def items(self, **kwargs):
        self.library_calls.append(kwargs)
        return [
            {"data": {"title": "Existing Elsewhere", "DOI": "10.1/elsewhere"}},
        ]

    def collection_items(self, collection_key, **kwargs):
        self.collection_calls.append((collection_key, kwargs))
        return []


def test_check_duplicate_collection_scoped_ignores_library_dupes():
    zot = _StubZot()

    is_dup = check_duplicate(
        zot,
        "Existing Elsewhere",
        "10.1/elsewhere",
        collection_key="COLL1",
    )

    assert is_dup is False
    assert zot.collection_calls == [("COLL1", {"q": "10.1/elsewhere", "limit": 5})]
    assert zot.library_calls == []


def test_check_duplicate_allow_library_duplicates_flag_returns_false():
    zot = _StubZot()

    is_dup = check_duplicate(
        zot,
        "Existing Elsewhere",
        "10.1/elsewhere",
        allow_library_duplicates=True,
    )

    assert is_dup is False
    assert zot.library_calls == []
    assert zot.collection_calls == []


def test_check_duplicate_library_wide_default_unchanged():
    zot = _StubZot()

    is_dup = check_duplicate(zot, "Existing Elsewhere", "10.1/elsewhere")

    assert is_dup is True
    assert zot.library_calls == [{"q": "10.1/elsewhere", "limit": 5}]
