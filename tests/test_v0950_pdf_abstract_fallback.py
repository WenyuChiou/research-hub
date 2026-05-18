"""v0.95.0 — PDF-text abstract fallback (last-resort, fail-safe).

Tests for _extract_abstract_from_text, _recover_from_local_pdf, and the
full recover_abstract chain with pdf_path wired in.

Mocking style mirrors test_v0871_abstract_fallback.py:
  - unittest.mock.patch for module-level function patches
  - RecoveredAbstract for return-value construction
  - No binary PDF fixtures — _extract_pdf is always mocked
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from research_hub.search.abstract_recovery import (
    RecoveredAbstract,
    _extract_abstract_from_text,
    _is_substantive,
    _recover_from_local_pdf,
    recover_abstract,
)


# ---------------------------------------------------------------------------
# _extract_abstract_from_text unit tests
# ---------------------------------------------------------------------------

_LONG_ABSTRACT = (
    "This paper presents a novel approach to multi-agent coordination using "
    "large language models as the central reasoning engine. We demonstrate "
    "that our architecture achieves state-of-the-art performance on three "
    "benchmark datasets, outperforming all prior baselines by a significant "
    "margin. The key insight is that tool-augmented agents with shared memory "
    "dramatically reduce coordination overhead while improving task coherence."
)  # 420 chars — well above the 200-char floor

_PADDED = _LONG_ABSTRACT * 2  # ensure >200 chars for header-based extraction tests


def _make_text_with_header(abstract_body: str) -> str:
    return (
        "Title of the Paper\n"
        "Author One, Author Two\n\n"
        "Abstract\n"
        f"{abstract_body}\n\n"
        "1. Introduction\n"
        "The introduction text follows.\n"
    )


# (a) Header-based extraction returns the abstract text
def test_extract_abstract_header_based() -> None:
    text = _make_text_with_header(_LONG_ABSTRACT)
    result = _extract_abstract_from_text(text)
    assert result is not None
    assert len(result) >= 200
    assert "novel approach" in result


# (a-continued) Source propagates as "local-pdf" when chained through recover_abstract
def test_recover_abstract_local_pdf_source(tmp_path: Path) -> None:
    fake_pdf = tmp_path / "10.1234_test.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 fake")
    text_with_abstract = _make_text_with_header(_LONG_ABSTRACT)

    with patch(
        "research_hub.search.abstract_recovery._recover_from_crossref",
        return_value=RecoveredAbstract(text="", source=""),
    ), patch(
        "research_hub.search.abstract_recovery._recover_from_unpaywall",
        return_value=RecoveredAbstract(text="", source="", oa_url=""),
    ), patch(
        "research_hub.search.abstract_recovery._recover_from_openalex",
        return_value=RecoveredAbstract(text="", source=""),
    ), patch(
        "research_hub.search.abstract_recovery._recover_from_semantic_scholar",
        return_value=RecoveredAbstract(text="", source=""),
    ), patch(
        "research_hub.importer._extract_pdf",
        return_value=text_with_abstract,
    ):
        result = recover_abstract("10.1234/test", pdf_path=fake_pdf)

    assert result.source == "local-pdf"
    assert "novel approach" in result.text


# (b) Rejects text shorter than 200 chars
def test_extract_abstract_rejects_short_text() -> None:
    # Header present but body is too short
    text = "Abstract\nShort abstract.\n\nIntroduction\n"
    result = _extract_abstract_from_text(text)
    assert result is None


def test_extract_abstract_rejects_200_char_boundary() -> None:
    # Exactly 199 chars — must be rejected
    body = "A" * 199
    text = f"Abstract\n{body}\n\nIntroduction\n"
    result = _extract_abstract_from_text(text)
    assert result is None


# (c) Rejects boilerplate matches
def test_extract_abstract_rejects_copyright_boilerplate() -> None:
    body = _LONG_ABSTRACT + " Copyright 2024 IEEE. All rights reserved."
    text = _make_text_with_header(body)
    result = _extract_abstract_from_text(text)
    assert result is None


def test_extract_abstract_rejects_doi_stamp_boilerplate() -> None:
    body = _LONG_ABSTRACT + " DOI: 10.1234/test Published online 2024."
    text = _make_text_with_header(body)
    result = _extract_abstract_from_text(text)
    assert result is None


def test_extract_abstract_rejects_arxiv_stamp_boilerplate() -> None:
    body = _LONG_ABSTRACT + " arXiv: 2401.12345"
    text = _make_text_with_header(body)
    result = _extract_abstract_from_text(text)
    assert result is None


# (c-continued) Garbled text rejection
def test_extract_abstract_rejects_garbled_low_space_ratio() -> None:
    # String of non-space characters — space ratio far below 0.08
    body = "A" * 300  # no spaces at all
    text = f"Abstract\n{body}\n\nIntroduction\n"
    result = _extract_abstract_from_text(text)
    assert result is None


def test_extract_abstract_rejects_garbled_single_char_words() -> None:
    # >30% single-char "words" — typical of column-interleaved PDF
    single_chars = " ".join(["a"] * 120 + ["word"] * 20)  # 120/140 = ~86% single-char
    text = f"Abstract\n{single_chars}\n\nIntroduction\n"
    result = _extract_abstract_from_text(text)
    assert result is None


# (d) PDF fallback fires only after all 4 online sources return non-substantive
def test_pdf_fallback_fires_only_after_all_four_fail(tmp_path: Path) -> None:
    fake_pdf = tmp_path / "paper.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4")
    text = _make_text_with_header(_LONG_ABSTRACT)

    extract_mock = MagicMock(return_value=text)

    with patch(
        "research_hub.search.abstract_recovery._recover_from_crossref",
        return_value=RecoveredAbstract(text="", source=""),
    ), patch(
        "research_hub.search.abstract_recovery._recover_from_unpaywall",
        return_value=RecoveredAbstract(text="", source="", oa_url=""),
    ), patch(
        "research_hub.search.abstract_recovery._recover_from_openalex",
        return_value=RecoveredAbstract(text="", source=""),
    ), patch(
        "research_hub.search.abstract_recovery._recover_from_semantic_scholar",
        return_value=RecoveredAbstract(text="", source=""),
    ), patch(
        "research_hub.importer._extract_pdf",
        extract_mock,
    ):
        result = recover_abstract("10.1/x", pdf_path=fake_pdf)

    assert result.source == "local-pdf"
    extract_mock.assert_called_once_with(fake_pdf)


# (e) When S2 succeeds, _extract_pdf is never called
def test_s2_success_no_pdf_extraction_called(tmp_path: Path) -> None:
    fake_pdf = tmp_path / "paper.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4")

    extract_mock = MagicMock(return_value="")

    with patch(
        "research_hub.search.abstract_recovery._recover_from_crossref",
        return_value=RecoveredAbstract(text="", source=""),
    ), patch(
        "research_hub.search.abstract_recovery._recover_from_unpaywall",
        return_value=RecoveredAbstract(text="", source="", oa_url=""),
    ), patch(
        "research_hub.search.abstract_recovery._recover_from_openalex",
        return_value=RecoveredAbstract(text="", source=""),
    ), patch(
        "research_hub.search.abstract_recovery._recover_from_semantic_scholar",
        return_value=RecoveredAbstract(text="S2 found the abstract " * 15, source="s2"),
    ), patch(
        "research_hub.importer._extract_pdf",
        extract_mock,
    ):
        result = recover_abstract("10.1/x", pdf_path=fake_pdf)

    assert result.source == "s2"
    extract_mock.assert_not_called()


# (f) pdf_path=None → no fallback (default behaviour unchanged)
def test_no_pdf_path_no_fallback() -> None:
    with patch(
        "research_hub.search.abstract_recovery._recover_from_crossref",
        return_value=RecoveredAbstract(text="", source=""),
    ), patch(
        "research_hub.search.abstract_recovery._recover_from_unpaywall",
        return_value=RecoveredAbstract(text="", source="", oa_url=""),
    ), patch(
        "research_hub.search.abstract_recovery._recover_from_openalex",
        return_value=RecoveredAbstract(text="", source=""),
    ), patch(
        "research_hub.search.abstract_recovery._recover_from_semantic_scholar",
        return_value=RecoveredAbstract(text="", source=""),
    ):
        result = recover_abstract("10.1/missing")  # pdf_path defaults to None

    assert result.text == ""
    assert result.source == ""


# (g) pdf_path points to a non-existent file → no fallback
def test_missing_pdf_file_no_fallback(tmp_path: Path) -> None:
    nonexistent = tmp_path / "does_not_exist.pdf"

    with patch(
        "research_hub.search.abstract_recovery._recover_from_crossref",
        return_value=RecoveredAbstract(text="", source=""),
    ), patch(
        "research_hub.search.abstract_recovery._recover_from_unpaywall",
        return_value=RecoveredAbstract(text="", source="", oa_url=""),
    ), patch(
        "research_hub.search.abstract_recovery._recover_from_openalex",
        return_value=RecoveredAbstract(text="", source=""),
    ), patch(
        "research_hub.search.abstract_recovery._recover_from_semantic_scholar",
        return_value=RecoveredAbstract(text="", source=""),
    ):
        result = recover_abstract("10.1/missing", pdf_path=nonexistent)

    assert result.text == ""
    assert result.source == ""


# (h) disable_pdf_fallback=True → pdf_path forced None at the call site
#     Tested via plan_enrichment with a real PDF present but disable flag set.
def test_disable_pdf_fallback_in_plan_enrichment(tmp_path: Path) -> None:
    """When disable_pdf_fallback=True, plan_enrichment must NOT call _extract_pdf
    even if a matching PDF exists in pdfs_dir."""
    pdfs_dir = tmp_path / "pdfs"
    pdfs_dir.mkdir()
    # Create a fake PDF that would match the DOI "10.1234/test"
    fake_pdf = pdfs_dir / "10.1234_test.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4")

    extract_mock = MagicMock(return_value="Abstract\n" + _LONG_ABSTRACT + "\n\nIntroduction\n")

    item = {
        "key": "TESTKEY",
        "data": {
            "DOI": "10.1234/test",
            "title": "Test Paper Title",
            "abstractNote": "",  # empty — triggers recovery
        },
    }

    def fake_backend_get(*args, **kwargs):
        return None

    with patch(
        "research_hub.zotero.enrich.CrossrefBackend",
    ) as MockCrossref, patch(
        "research_hub.zotero.enrich.OpenAlexBackend",
    ) as MockOpenAlex, patch(
        "research_hub.search.abstract_recovery.requests.get",
        return_value=MagicMock(status_code=404, json=lambda: {}),
    ), patch(
        "research_hub.importer._extract_pdf",
        extract_mock,
    ):
        MockCrossref.return_value.get_paper = lambda doi: None
        MockOpenAlex.return_value.get_paper = lambda doi: None

        from research_hub.zotero.enrich import plan_enrichment

        plans = plan_enrichment(
            [item],
            pdfs_dir=pdfs_dir,
            disable_pdf_fallback=True,  # <— opt-out engaged
        )

    # _extract_pdf must never be called when disable_pdf_fallback=True
    extract_mock.assert_not_called()


# ---------------------------------------------------------------------------
# _recover_from_local_pdf unit tests
# ---------------------------------------------------------------------------

def test_recover_from_local_pdf_returns_empty_for_none() -> None:
    result = _recover_from_local_pdf(None)  # type: ignore[arg-type]
    assert result == ""


def test_recover_from_local_pdf_returns_empty_for_missing_file(tmp_path: Path) -> None:
    result = _recover_from_local_pdf(tmp_path / "ghost.pdf")
    assert result == ""


def test_recover_from_local_pdf_uses_extract_pdf(tmp_path: Path) -> None:
    fake_pdf = tmp_path / "paper.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4")
    text = _make_text_with_header(_LONG_ABSTRACT)

    # _extract_pdf is imported lazily inside _recover_from_local_pdf via
    # `from research_hub.importer import _extract_pdf` — patch the source.
    with patch("research_hub.importer._extract_pdf", return_value=text):
        result = _recover_from_local_pdf(fake_pdf)

    assert len(result) >= 200
    assert "novel approach" in result


def test_recover_from_local_pdf_returns_empty_on_extract_exception(tmp_path: Path) -> None:
    fake_pdf = tmp_path / "paper.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4")

    # Patch at the source module since the import is lazy.
    with patch(
        "research_hub.importer._extract_pdf",
        side_effect=RuntimeError("pdfplumber not installed"),
    ):
        result = _recover_from_local_pdf(fake_pdf)

    assert result == ""
