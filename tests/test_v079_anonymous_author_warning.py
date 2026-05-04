from __future__ import annotations

from research_hub.pipeline import _validate_paper_input


def _make_paper(authors, **overrides):
    base = {
        "title": "T",
        "doi": "10.1/x",
        "year": 2025,
        "authors": authors,
        "abstract": "a",
        "journal": "j",
        "summary": "s",
        "key_findings": ["k"],
        "methodology": "m",
        "relevance": "r",
    }
    base.update(overrides)
    return base


def test_warn_when_only_author_is_anonymous():
    pp = _make_paper([{"creatorType": "author", "name": "Anonymous"}])
    errors = _validate_paper_input(pp, 0)
    assert any("WARN -- all authors are anonymous" in error for error in errors)


def test_warn_when_all_authors_unknown():
    pp = _make_paper(
        [
            {"creatorType": "author", "lastName": "Unknown"},
            {"creatorType": "author", "name": "anonymous"},
        ]
    )
    errors = _validate_paper_input(pp, 0)
    assert any("WARN" in error for error in errors)


def test_no_warn_when_real_author():
    pp = _make_paper(
        [{"creatorType": "author", "firstName": "Ranjan", "lastName": "Sapkota"}]
    )
    errors = _validate_paper_input(pp, 0)
    assert not any("anonymous" in error.lower() for error in errors)


def test_warn_does_not_appear_with_mixed_authors():
    pp = _make_paper(
        [
            {"creatorType": "author", "name": "Anonymous"},
            {"creatorType": "author", "lastName": "Real Person"},
        ]
    )
    errors = _validate_paper_input(pp, 0)
    assert not any("anonymous" in error.lower() for error in errors)
