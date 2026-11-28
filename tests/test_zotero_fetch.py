"""Tests for research_hub.zotero.fetch helpers."""

import pytest

from research_hub.zotero.fetch import (
    extract_item_data,
    get_notes,
    make_paper_slug,
    make_raw_md,
    safe_filename,
    tags_to_wiki_links,
)


def test_safe_filename_basic():
    result = safe_filename("Smith, John", "2024", "A study of flood risk perception")

    assert result == "smith2024-study-flood-risk-perception.md"


def test_make_paper_slug_matches_safe_filename():
    """v0.84.0 regression test: the slug formula must be unified.

    Before v0.84.0, three call sites (pipeline.py:111, discover.py:813,
    operations.py:264) used divergent `slugify(title)[:60]` formulas that
    produced long slugs not matching `safe_filename()`'s 4-keyword short
    format. This caused 1,199 broken cross-ref wikilinks in user vaults
    (2026-05-11 graph hygiene audit). All paper-slug computation must
    now use `make_paper_slug`, which `safe_filename` also calls.
    """
    inputs = [
        ("Smith, John", "2024", "A study of flood risk perception"),
        ("Donkers, Anna", "2025", "Understanding Online Polarization"),
        ("Gupta, Rahul", "2025",
         "The role of social learning and collective norm formation in agents"),
    ]
    for author, year, title in inputs:
        slug = make_paper_slug(author, year, title)
        filename = safe_filename(author, year, title)
        # filename = slug + ".md", always
        assert filename == f"{slug}.md", (
            f"slug formula divergence: make_paper_slug={slug!r}, safe_filename={filename!r}"
        )
        # slug must not contain stopwords (the/of/and/in/...)
        assert "-the-" not in f"-{slug}-"
        assert "-of-" not in f"-{slug}-"
        assert "-and-" not in f"-{slug}-"
        # slug must not exceed ~60 chars (4 keywords typical)
        assert len(slug) <= 80, f"slug too long: {len(slug)} chars in {slug!r}"


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
        "volume": "",
        "issue": "",
        "pages": "",
        "edition": "",
        "doi": "10.1000/example",
        "url": "https://example.com/paper",
        "abstract": "Abstract text",
        "tags": ["PMT", "flood risk"],
    }


def test_tags_to_wiki_links_maps_known_terms():
    """v0.82.0: returns #tag syntax, not [[Wikilink]]. Old wikilink target
    files never existed → produced mega-hub stars in Obsidian graph view.
    """
    links = tags_to_wiki_links(["PMT", "flood risk"])

    assert "#protection-motivation-theory" in links
    assert "#flood-risk" in links


def test_tags_to_wiki_links_empty_for_unknown():
    assert tags_to_wiki_links(["unmapped topic"]) == []


def test_make_raw_md_includes_aliases_and_display_title():
    """v0.83.0: paper notes get aliases + display_title frontmatter so
    Obsidian graph view renders 'Donkers 2025 — ...' instead of dash slug.
    """
    item_data = {
        "key": "ABCD1234",
        "title": "Understanding Online Polarization",
        "authors": ["Donkers, Anna", "Smith, Bob", "Lee, Cara"],
        "year": "2025",
        "journal": "Some Journal",
        "doi": "10.1/example",
        "abstract": "",
        "tags": [],
    }
    md = make_raw_md(item_data, [], [], topic_cluster="test-cluster")

    assert 'aliases: ["Donkers 2025", "Donkers et al. 2025"]' in md
    assert 'display_title: "Donkers 2025 — Understanding Online Polarization"' in md


def test_make_raw_md_single_author_no_et_al():
    item_data = {
        "key": "ABCD",
        "title": "Solo Study",
        "authors": ["Donkers, Anna"],
        "year": "2025",
        "journal": "",
        "doi": "",
        "abstract": "",
        "tags": [],
    }
    md = make_raw_md(item_data, [], [], topic_cluster="x")

    assert 'aliases: ["Donkers 2025"]' in md
    assert "et al." not in md.split("---\n", 2)[1]  # not in frontmatter
    assert 'display_title: "Donkers 2025 — Solo Study"' in md


def test_make_raw_md_placeholder_author_falls_back_to_empty_aliases():
    """When Zotero ingestion has placeholder authors like '(See arXiv ...)',
    aliases is empty and display_title is also empty (avoid garbage display).
    """
    item_data = {
        "key": "ABCD",
        "title": "(See arXiv 2505.07087)",
        "authors": ["(See arXiv 2505.07087)"],
        "year": "2025",
        "journal": "",
        "doi": "",
        "abstract": "",
        "tags": [],
    }
    md = make_raw_md(item_data, [], [], topic_cluster="x")

    assert "aliases: []" in md
    assert 'display_title: ""' in md


def test_tags_to_wiki_links_never_emits_wikilink_brackets():
    """Regression test for the 7 GB graph-pollution bug (2026-05-11).

    Prior to v0.82.0, every paper with an 'llm' tag got `[[LLM-Agents]]`
    injected — an unresolved wikilink — creating a 115-edge mega-star hub
    in Obsidian's graph view. Ensure no value in TAG_WIKI_MAP regresses.
    """
    sample_tags = [
        "llm", "memory", "abm", "flood", "social capital", "metacognition",
        "multi-agent", "place attachment", "natural language",
    ]
    links = tags_to_wiki_links(sample_tags)
    assert links, "expected at least one concept tag"
    for link in links:
        assert "[[" not in link and "]]" not in link, (
            f"v0.82.0 regression: TAG_WIKI_MAP must emit #tag not [[Wikilink]]; got {link!r}"
        )
        assert link.startswith("#"), f"expected #tag prefix, got {link!r}"


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


def test_get_notes_does_not_swallow_keyboard_interrupt(monkeypatch):
    """Regression: get_notes used a bare `except:` that swallowed
    KeyboardInterrupt/SystemExit during the network call, making Ctrl-C
    impossible mid-fetch. After narrowing to `except Exception`, control-flow
    exceptions must propagate.
    """

    def raise_kbd(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr("research_hub.zotero.fetch.requests.get", raise_kbd)

    with pytest.raises(KeyboardInterrupt):
        get_notes("https://api.zotero.example", "ITEMKEY")


def test_get_notes_returns_empty_and_warns_on_network_error(monkeypatch, capsys):
    """A genuine network/JSON error is still best-effort (returns []) but is
    no longer fully silent — a warning is surfaced (matches get_all_items).
    """

    def raise_conn(*args, **kwargs):
        raise RuntimeError("connection reset")

    monkeypatch.setattr("research_hub.zotero.fetch.requests.get", raise_conn)

    result = get_notes("https://api.zotero.example", "ITEMKEY")

    assert result == []
    captured = capsys.readouterr()
    assert "Error fetching notes for ITEMKEY" in captured.out
