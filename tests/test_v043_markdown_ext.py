"""v0.43 - Obsidian Flavored Markdown extensions tests."""
from __future__ import annotations

import pytest

from research_hub.markdown_conventions import embed, highlight, property_block, wikilink


def test_wikilink_plain():
    assert wikilink("paper-slug") == "[[paper-slug]]"


def test_wikilink_with_display():
    assert wikilink("paper-slug", display="Paper Title") == "[[paper-slug|Paper Title]]"


def test_wikilink_with_heading():
    assert wikilink("paper-slug", heading="Summary") == "[[paper-slug#Summary]]"


def test_wikilink_with_block_id():
    assert wikilink("paper-slug", block_id="findings") == "[[paper-slug^findings]]"


def test_wikilink_heading_plus_display():
    assert wikilink("p", heading="Methods", display="see methods") == "[[p#Methods|see methods]]"


def test_wikilink_rejects_heading_plus_block_id():
    with pytest.raises(ValueError):
        wikilink("p", heading="Methods", block_id="findings")


def test_wikilink_rejects_empty_target():
    with pytest.raises(ValueError):
        wikilink("")
    with pytest.raises(ValueError):
        wikilink("   ")


def test_embed_plain():
    assert embed("image.png") == "![[image.png]]"


def test_embed_with_size():
    assert embed("image.png", size=300) == "![[image.png|300]]"


def test_embed_pdf_page():
    assert embed("paper.pdf", page=3) == "![[paper.pdf#page=3]]"


def test_highlight_wraps():
    assert highlight("important") == "==important=="

def test_property_block_strings():
    out = property_block(status="reading", title="My Paper")
    assert 'status: "reading"' in out
    assert 'title: "My Paper"' in out


def test_property_block_lists():
    out = property_block(tags=["llm", "harness"])
    assert 'tags: ["llm", "harness"]' in out


def test_property_block_mixed_types():
    out = property_block(verified=True, year=2026, doi=None)
    assert "verified: true" in out
    assert "year: 2026" in out
    assert "doi: null" in out


def test_property_block_empty():
    assert property_block() == ""
