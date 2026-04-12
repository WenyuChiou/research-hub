"""Canonical DOI helper tests."""

from __future__ import annotations

from research_hub.utils.doi import extract_arxiv_id, is_arxiv_doi, normalize_doi


def test_normalize_strips_https_prefix():
    assert normalize_doi("https://doi.org/10.1234/x") == "10.1234/x"


def test_normalize_strips_doi_prefix():
    assert normalize_doi("doi:10.1234/x") == "10.1234/x"
    assert normalize_doi("DOI:10.1234/x") == "10.1234/x"


def test_normalize_strips_dx_doi_prefix():
    assert normalize_doi("https://dx.doi.org/10.1234/x") == "10.1234/x"
    assert normalize_doi("http://dx.doi.org/10.1234/x") == "10.1234/x"


def test_normalize_lowercases():
    assert normalize_doi("10.1038/S44168") == "10.1038/s44168"


def test_normalize_empty():
    assert normalize_doi("") == ""
    assert normalize_doi("   ") == ""


def test_is_arxiv_doi():
    assert is_arxiv_doi("10.48550/arxiv.2502.10978")
    assert is_arxiv_doi("10.48550/arXiv.2403.03407")
    assert not is_arxiv_doi("10.1038/x")


def test_extract_arxiv_id_from_url():
    assert extract_arxiv_id("https://arxiv.org/abs/2502.10978") == "2502.10978"
    assert extract_arxiv_id("10.48550/arxiv.2403.03407") == "2403.03407"
    assert extract_arxiv_id("2510.03514v2") == "2510.03514v2"
    assert extract_arxiv_id("") == ""


def test_extract_arxiv_id_ignores_missing_pattern():
    assert extract_arxiv_id("https://example.com/no-arxiv-here") == ""
