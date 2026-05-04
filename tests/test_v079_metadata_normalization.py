from __future__ import annotations

from research_hub.pipeline import _normalize_paper_metadata


def test_journal_preprint_for_arxiv_doi_becomes_arxiv():
    pp = {"journal": "preprint", "doi": "10.48550/arXiv.2604.18011", "volume": ""}
    _normalize_paper_metadata(pp)
    assert pp["journal"] == "arXiv"


def test_journal_preprint_for_non_arxiv_doi_becomes_empty():
    pp = {"journal": "preprint", "doi": "10.1109/X.2025.001"}
    _normalize_paper_metadata(pp)
    assert pp["journal"] == ""


def test_journal_empty_for_arxiv_doi_becomes_arxiv():
    pp = {"journal": "", "doi": "10.48550/arXiv.2604.18011"}
    _normalize_paper_metadata(pp)
    assert pp["journal"] == "arXiv"


def test_journal_real_value_unchanged():
    pp = {"journal": "AI & SOCIETY", "doi": "10.1007/s00146-026-02960-8"}
    _normalize_paper_metadata(pp)
    assert pp["journal"] == "AI & SOCIETY"


def test_volume_abs_path_stripped():
    pp = {"journal": "arXiv", "volume": "abs/2602.13458", "doi": "10.48550/arxiv.2602.13458"}
    _normalize_paper_metadata(pp)
    assert pp["volume"] == ""


def test_volume_pdf_path_stripped():
    pp = {"journal": "x", "volume": "pdf/2602.13458"}
    _normalize_paper_metadata(pp)
    assert pp["volume"] == ""


def test_volume_real_number_unchanged():
    pp = {"journal": "x", "volume": "42"}
    _normalize_paper_metadata(pp)
    assert pp["volume"] == "42"
