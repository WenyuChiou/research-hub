"""Offline result handoff checks; not scheduler or semantic acceptance."""

import copy

import pytest

from research_hub.evidence_harness import synthesize_evidence_packet


def _synthesize(results, warnings=None):
    return synthesize_evidence_packet(
        query="Bounded research question", researcher_results=results,
        sources=[], claims=[], warnings=warnings,
    )


@pytest.mark.parametrize("unavailable", [
    None, {}, {"ok": False}, {"status": "failed"},
    {"status": "timeout"}, {"status": "blocked"},
])
def test_failed_sibling_does_not_erase_useful_result_or_coverage_limit(unavailable):
    results = [{"ok": True, "evidence_ref": "research:closest"}, unavailable]
    before = copy.deepcopy(results)
    result = _synthesize(results)
    # ok means packet validation only, not success of both research branches.
    assert result["ok"] is True
    assert result["packet"]["provenance"]["researcher_outputs"] == ["research:closest"]
    assert result["packet"]["warnings"] == [
        "Researcher result 1: unavailable or failed; coverage remains unresolved."
    ]
    assert results == before


@pytest.mark.parametrize("status", ["partial", "interrupted", "unavailable", "unknown", "running"])
def test_noncomplete_prose_keeps_reference_and_explicit_limit(status):
    result = _synthesize([{"status": status, "prose": "Useful source finding",
                           "evidence_ref": "research:contrary"}])
    assert result["ok"] is True
    assert result["packet"]["provenance"]["researcher_outputs"] == ["research:contrary"]
    assert len(result["packet"]["warnings"]) == 1
    assert "coverage remains unresolved" in result["packet"]["warnings"][0]


def test_complete_prose_needs_no_structured_callback_and_preserves_caller_warnings():
    warnings = ["Source version remains uncertain."]
    result = _synthesize([{"status": "completed", "prose": "Bounded finding",
                           "structured_output": None, "evidence_ref": "research:1"}], warnings)
    assert result["ok"] is True
    assert result["packet"]["warnings"] == warnings
    assert result["packet"]["warnings"] is not warnings


def test_unrecognized_status_does_not_copy_arbitrary_payload_into_warning():
    secret_like = "token=synthetic-private-material"
    result = _synthesize([{"status": secret_like, "evidence_ref": "research:1"}])
    assert result["packet"]["warnings"] == [
        "Researcher result 0: completion unknown; coverage remains unresolved."
    ]
    assert secret_like not in str(result)


def test_raw_result_handoff_preserves_failed_and_partial_siblings():
    raw_results = [
        {"status": "completed", "evidence_ref": "research:closest"},
        {"status": "timeout"},
        {"status": "partial", "prose": "A bounded source finding",
         "evidence_ref": "research:contrary"},
    ]
    result = _synthesize(raw_results)
    assert result["ok"] is True  # structural validation only
    assert result["packet"]["provenance"]["researcher_outputs"] == [
        "research:closest", "research:contrary",
    ]
    assert result["packet"]["warnings"] == [
        "Researcher result 1: unavailable or failed; coverage remains unresolved.",
        "Researcher result 2: partial; coverage remains unresolved.",
    ]


def test_fallback_reference_uses_original_slot_after_filtering():
    raw_results = [None, {"status": "partial", "prose": "Useful finding"}]
    result = _synthesize(raw_results)
    assert result["packet"]["provenance"]["researcher_outputs"] == ["result:1"]
    assert result["packet"]["warnings"] == [
        "Researcher result 0: unavailable or failed; coverage remains unresolved.",
        "Researcher result 1: partial; coverage remains unresolved.",
    ]
