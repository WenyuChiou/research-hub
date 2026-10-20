"""Focused tests for the optional, non-executing follow-up sidecar."""

from copy import deepcopy
import hashlib

import pytest

from research_hub.direction_review import dumps_direction_json
from research_hub.followup import (
    FollowupSidecarError,
    build_followup_sidecar,
    make_followup_attempt,
    validate_followup_sidecar,
)


@pytest.fixture
def inputs():
    candidate = {
        "id": "G1",
        "candidate_version": 1,
        "name": "Grounded household simulation",
        "statement": "Test a human-grounded LLM decision simulation with environmental feedback.",
    }
    evidence = {"sources": [{"source_id": "S1", "version": "v1", "sha256": "a" * 64}]}
    missing = [{
        "need_id": "N1",
        "description": "Find a human-grounded evaluation with environmental feedback.",
        "decision_affected": "Whether the proposed validation is answerable.",
        "material": True,
    }]
    cost = {"status": "unknown", "evidence_refs": []}
    action = {"kind": "literature-query", "query": "human-grounded LLM household simulation"}
    return candidate, evidence, missing, cost, action


def attempt(inputs, *, attempt_id="A1", status="empty", refs=None, action=None, **overrides):
    candidate, evidence, missing, _, default_action = inputs
    values = {
        "candidate": candidate,
        "evidence_snapshot": evidence,
        "material_missing_evidence": missing,
        "action": default_action if action is None else action,
        "attempt_id": attempt_id,
        "status": status,
        "evidence_refs": refs,
    }
    values.update(overrides)
    return make_followup_attempt(**values)


def sidecar(inputs, *, history=None, action=None, evidence=None, candidate=None,
            missing=None, cost=None):
    original_candidate, original_evidence, original_missing, original_cost, original_action = inputs
    return build_followup_sidecar(
        original_candidate if candidate is None else candidate,
        original_evidence if evidence is None else evidence,
        original_missing if missing is None else missing,
        resource_cost=original_cost if cost is None else cost,
        attempt_history=history,
        proposed_action=original_action if action is None else action,
    )


def validate(value, inputs, *, candidate=None, evidence=None, missing=None, cost=None):
    original_candidate, original_evidence, original_missing, original_cost, _ = inputs
    return validate_followup_sidecar(
        value,
        original_candidate if candidate is None else candidate,
        original_evidence if evidence is None else evidence,
        original_missing if missing is None else missing,
        original_cost if cost is None else cost,
    )


def test_identical_empty_attempt_is_flagged_without_retry_authority(inputs):
    record = attempt(inputs, status="empty")
    result = sidecar(inputs, history=[record])

    assert result["repeat_assessment"] == {
        "status": "identical-action-no-progress",
        "attempt_ids": ["A1"],
        "latest_status": "empty",
        "new_evidence_refs": [],
        "no_progress": True,
        "comparison_basis": "exact-canonical-action-hash-and-current-bindings-only",
    }
    assert result["execution_authorized"] is False
    assert result["additional_retry_authority_granted"] is False
    assert "retry_budget" not in result
    assert validate(result, inputs)["record_status"] == "current"


def test_historical_success_does_not_mask_later_failure(inputs):
    success = attempt(inputs, attempt_id="A1", status="success", refs=["S2"])
    failure = attempt(inputs, attempt_id="A2", status="failed", failure_code="search-error")
    result = sidecar(inputs, history=[success, failure])

    assert result["repeat_assessment"]["status"] == "identical-action-no-progress"
    assert result["repeat_assessment"]["latest_status"] == "failed"
    assert result["repeat_assessment"]["no_progress"] is True
    assert result["repeat_assessment"]["attempt_ids"] == ["A1", "A2"]


@pytest.mark.parametrize(
    ("status", "refs", "failure"),
    [
        ("success", ["S2"], None),
        ("empty", [], None),
        ("failed", [], "search-error"),
        ("unavailable", [], "backend-unavailable"),
    ],
)
def test_outcomes_remain_distinct(inputs, status, refs, failure):
    record = attempt(
        inputs,
        status=status,
        refs=refs,
        failure_code=failure,
    )
    result = sidecar(inputs, history=[record], action={"kind": "different", "query": "new"})
    assert result["attempt_history"][0]["record"]["status"] == status


def test_success_requires_evidence_reference(inputs):
    with pytest.raises(FollowupSidecarError, match="success-requires-evidence"):
        attempt(inputs, status="success", refs=[])


def test_unknown_resource_cost_stays_unknown_and_does_not_authorize_work(inputs):
    result = sidecar(inputs)

    assert result["resource_cost"] == {"status": "unknown", "evidence_refs": []}
    assert result["execution_authorized"] is False
    assert result["additional_retry_authority_granted"] is False


def test_old_attempt_binding_is_retained_but_not_compared_as_current(inputs):
    old = attempt(inputs, status="failed", failure_code="search-error")
    candidate, evidence, missing, cost, action = inputs
    new_candidate = deepcopy(candidate)
    new_candidate["candidate_version"] = 2
    new_candidate["statement"] += " Revised."
    new_evidence = {"sources": [{"source_id": "S1", "version": "v2", "sha256": "b" * 64}]}
    result = sidecar(
        inputs,
        candidate=new_candidate,
        evidence=new_evidence,
        history=[old],
        action=action,
    )

    assert result["attempt_history"][0]["binding_status"] == "historical"
    assert result["repeat_assessment"]["status"] == "unknown-stale-history"
    assert validate(result, inputs, candidate=new_candidate, evidence=new_evidence)["record_status"] == "current"


def test_stale_sidecar_candidate_evidence_and_missing_record_fail_closed(inputs):
    result = sidecar(inputs)
    candidate, evidence, missing, _, _ = inputs
    changed_candidate = deepcopy(candidate)
    changed_candidate["candidate_version"] = 2
    changed_evidence = {"sources": [{"source_id": "S1", "version": "v2", "sha256": "c" * 64}]}
    changed_missing = deepcopy(missing)
    changed_missing[0]["description"] += " Include contradictory work."

    assert validate(result, inputs, candidate=changed_candidate)["record_status"] == "unknown"
    assert validate(result, inputs, evidence=changed_evidence)["record_status"] == "unknown"
    assert validate(result, inputs, missing=changed_missing)["record_status"] == "unknown"


def test_changed_resource_cost_fails_closed(inputs):
    result = sidecar(inputs)
    supported_cost = {"status": "supported", "evidence_refs": ["COST-1"]}

    checked = validate(result, inputs, cost=supported_cost)
    assert checked["record_status"] == "unknown"
    assert checked["reason"] == "stale-resource-cost-binding"
    assert checked["additional_retry_authority_granted"] is False


def test_tampered_attempt_record_fails_closed_even_if_outer_hash_is_recomputed(inputs):
    record = attempt(inputs, status="failed", failure_code="search-error")
    result = sidecar(inputs, history=[record])
    result["attempt_history"][0]["record"]["candidate_ref"]["candidate_version"] = 2
    payload = {key: value for key, value in result.items() if key != "sidecar_sha256"}
    result["sidecar_sha256"] = hashlib.sha256(
        dumps_direction_json(payload, pretty=False, sort_keys=True).encode("utf-8")
    ).hexdigest()

    checked = validate(result, inputs)
    assert checked["record_status"] == "unknown"
    assert checked["reason"] == "attempt-hash-mismatch"


def test_tampered_sidecar_hash_returns_unknown(inputs):
    result = sidecar(inputs)
    result["material_missing_evidence"][0]["description"] = "tampered"

    checked = validate(result, inputs)
    assert checked["record_status"] == "unknown"
    assert checked["reason"] == "sidecar-hash-mismatch"


def test_missing_sidecar_fails_closed(inputs):
    checked = validate(None, inputs)

    assert checked["record_status"] == "unknown"
    assert checked["reason"] == "sidecar-shape"
    assert checked["execution_authorized"] is False
    assert checked["additional_retry_authority_granted"] is False
