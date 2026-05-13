"""v0.87.1 #3 — abstract fallback chain incl. OpenAlex inverted-index reconstruction."""

from __future__ import annotations

from unittest.mock import patch

from research_hub.search.abstract_recovery import (
    RecoveredAbstract,
    _is_substantive,
    _recover_from_openalex,
    recover_abstract,
)


def test_is_substantive_accepts_long_real_abstract() -> None:
    text = "This paper investigates the application of large language models to flood risk assessment in urban Brisbane, demonstrating that a multi-agent architecture can outperform classical machine learning baselines on storm tide, creek, and overland flow flood types." * 2
    assert _is_substantive(text)


def test_is_substantive_rejects_no_abstract_placeholder() -> None:
    assert not _is_substantive("(no abstract)")
    assert not _is_substantive("[no abstract]")
    assert not _is_substantive("NO ABSTRACT AVAILABLE")
    assert not _is_substantive("Abstract not available")


def test_is_substantive_rejects_short_text() -> None:
    # Anything <200 chars is not substantive enough for downstream use
    assert not _is_substantive("Too short.")
    assert not _is_substantive("A" * 199)
    assert _is_substantive("A" * 200)


def test_is_substantive_rejects_empty_and_whitespace() -> None:
    assert not _is_substantive("")
    assert not _is_substantive("   ")
    assert not _is_substantive("\n\n")


def test_openalex_reconstructs_inverted_index() -> None:
    """OpenAlex stores `abstract_inverted_index: {word: [positions]}`."""
    fake_payload = {
        "abstract_inverted_index": {
            "This": [0],
            "is": [1],
            "the": [2, 4],
            "test": [3],
            "abstract": [5],
        }
    }

    class FakeResp:
        status_code = 200
        def json(self): return fake_payload

    with patch("research_hub.search.abstract_recovery.requests.get", return_value=FakeResp()):
        result = _recover_from_openalex("10.test/abc")

    assert result.source == "openalex"
    assert result.text == "This is the test the abstract"


def test_openalex_handles_missing_inverted_index() -> None:
    class FakeResp:
        status_code = 200
        def json(self): return {"id": "W123"}

    with patch("research_hub.search.abstract_recovery.requests.get", return_value=FakeResp()):
        result = _recover_from_openalex("10.test/abc")

    assert result.text == ""
    assert result.source == ""


def test_openalex_handles_http_error() -> None:
    class FakeResp:
        status_code = 404
        def json(self): return {}

    with patch("research_hub.search.abstract_recovery.requests.get", return_value=FakeResp()):
        result = _recover_from_openalex("10.test/missing")

    assert result.text == ""


def test_recover_chain_prefers_substantive_over_placeholder() -> None:
    """The pre-v0.87.1 bug: Crossref returns '(no abstract)' (13 chars),
    chain short-circuits and never tries OpenAlex. Fixed by
    _is_substantive check."""
    substantive_text = ("A" * 250)

    with patch(
        "research_hub.search.abstract_recovery._recover_from_crossref",
        return_value=RecoveredAbstract(text="(no abstract)", source="crossref"),
    ), patch(
        "research_hub.search.abstract_recovery._recover_from_openalex",
        return_value=RecoveredAbstract(text=substantive_text, source="openalex"),
    ):
        result = recover_abstract("10.test/abc")

    assert result.source == "openalex"
    assert result.text == substantive_text


def test_recover_chain_falls_through_to_s2_when_all_short() -> None:
    """When Crossref/OpenAlex/Unpaywall all return placeholders, S2 wins
    if it has a substantive abstract."""
    substantive_text = ("S2 paper content " * 30)

    with patch(
        "research_hub.search.abstract_recovery._recover_from_crossref",
        return_value=RecoveredAbstract(text="(no abstract)", source="crossref"),
    ), patch(
        "research_hub.search.abstract_recovery._recover_from_openalex",
        return_value=RecoveredAbstract(text="", source=""),
    ), patch(
        "research_hub.search.abstract_recovery._recover_from_unpaywall",
        return_value=RecoveredAbstract(text="", source="", oa_url=""),
    ), patch(
        "research_hub.search.abstract_recovery._recover_from_semantic_scholar",
        return_value=RecoveredAbstract(text=substantive_text, source="s2"),
    ):
        result = recover_abstract("10.test/abc")

    assert result.source == "s2"


def test_recover_chain_returns_longest_when_none_substantive() -> None:
    """If every source returns short text, return the longest one rather than nothing."""
    with patch(
        "research_hub.search.abstract_recovery._recover_from_crossref",
        return_value=RecoveredAbstract(text="short", source="crossref"),
    ), patch(
        "research_hub.search.abstract_recovery._recover_from_openalex",
        return_value=RecoveredAbstract(text="this is somewhat longer than crossref", source="openalex"),
    ), patch(
        "research_hub.search.abstract_recovery._recover_from_unpaywall",
        return_value=RecoveredAbstract(text="", source="", oa_url=""),
    ), patch(
        "research_hub.search.abstract_recovery._recover_from_semantic_scholar",
        return_value=RecoveredAbstract(text="", source=""),
    ):
        result = recover_abstract("10.test/abc")

    # Longest of the 4 = openalex (37 chars > 5 chars)
    assert result.source == "openalex"


def test_recover_chain_returns_empty_when_doi_missing() -> None:
    assert recover_abstract("").text == ""
