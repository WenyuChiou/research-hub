"""Pure validation for an optional, version-bound research follow-up sidecar.

This module records caller-supplied follow-up attempts. It does not search,
execute actions, assess scientific claims, grant retries, or authorize work.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib

from research_hub.direction_review import (
    DirectionReviewError,
    candidate_sha256,
    dumps_direction_json,
)


FORMAT = "research-followup-sidecar/1.0"
ATTEMPT_STATUSES = frozenset({"success", "empty", "failed", "unavailable"})
RESOURCE_STATUSES = frozenset({"supported", "contradicted", "unknown", "not-applicable"})
_HEX = frozenset("0123456789abcdef")


class FollowupSidecarError(ValueError):
    """Raised for malformed sidecar inputs; messages are stable error codes."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise FollowupSidecarError(code)


def _text(value, code: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()), code)
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise FollowupSidecarError("non-scalar-unicode") from exc
    return value


def _sha256(value, code: str) -> None:
    _require(
        isinstance(value, str)
        and len(value) == 64
        and all(character in _HEX for character in value),
        code,
    )


def _hash_json(value) -> str:
    try:
        canonical = dumps_direction_json(value, pretty=False, sort_keys=True)
    except DirectionReviewError as exc:
        raise FollowupSidecarError("non-canonical-json-input") from exc
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _candidate_ref(candidate: dict) -> dict:
    _require(isinstance(candidate, dict), "candidate-object-required")
    candidate_id = _text(candidate.get("id"), "candidate-id-required")
    version = candidate.get("candidate_version")
    _require(type(version) is int and version > 0, "candidate-version-required")
    try:
        digest = candidate_sha256(candidate)
    except DirectionReviewError as exc:
        raise FollowupSidecarError("candidate-not-canonical-json") from exc
    return {
        "candidate_id": candidate_id,
        "candidate_version": version,
        "candidate_sha256": digest,
    }


def _normalize_missing_evidence(rows) -> list[dict]:
    _require(isinstance(rows, list) and bool(rows), "material-missing-evidence-required")
    normalized = []
    seen = set()
    fields = {"need_id", "description", "decision_affected", "material"}
    for row in rows:
        _require(isinstance(row, dict) and set(row) == fields, "missing-evidence-shape")
        need_id = _text(row["need_id"], "missing-evidence-id-required")
        _require(need_id not in seen, "duplicate-missing-evidence-id")
        seen.add(need_id)
        _text(row["description"], "missing-evidence-description-required")
        _text(row["decision_affected"], "missing-evidence-decision-required")
        _require(row["material"] is True, "followup-must-address-material-evidence")
        normalized.append(deepcopy(row))
    return sorted(normalized, key=lambda row: row["need_id"])


def _normalize_resource_cost(value) -> dict:
    _require(
        isinstance(value, dict) and set(value) == {"status", "evidence_refs"},
        "resource-cost-shape",
    )
    status = value["status"]
    _require(isinstance(status, str) and status in RESOURCE_STATUSES, "resource-cost-status")
    refs = value["evidence_refs"]
    _require(
        isinstance(refs, list)
        and all(isinstance(ref, str) and bool(ref.strip()) for ref in refs)
        and len(refs) == len(set(refs)),
        "resource-cost-evidence-refs",
    )
    if status in {"supported", "contradicted"}:
        _require(bool(refs), "resource-cost-evidence-required")
    return {"status": status, "evidence_refs": deepcopy(refs)}


def _normalize_action(action):
    _require(action is None or isinstance(action, (str, dict)), "action-shape")
    if isinstance(action, str):
        _text(action, "action-required")
    if isinstance(action, dict):
        _require(bool(action), "action-required")
    return deepcopy(action)


def make_followup_attempt(
    candidate: dict,
    evidence_snapshot,
    material_missing_evidence: list[dict],
    action,
    *,
    attempt_id: str,
    status: str,
    evidence_refs: list[str] | None = None,
    failure_code: str | None = None,
) -> dict:
    """Bind one already-completed caller attempt; this function never runs it."""
    candidate_ref = _candidate_ref(candidate)
    missing = _normalize_missing_evidence(material_missing_evidence)
    normalized_action = _normalize_action(action)
    _text(attempt_id, "attempt-id-required")
    _require(isinstance(status, str) and status in ATTEMPT_STATUSES, "attempt-status-invalid")
    refs = [] if evidence_refs is None else evidence_refs
    _require(
        isinstance(refs, list)
        and all(isinstance(ref, str) and bool(ref.strip()) for ref in refs)
        and len(refs) == len(set(refs)),
        "attempt-evidence-refs-invalid",
    )
    if status == "success":
        _require(bool(refs) and failure_code is None, "success-requires-evidence")
    elif status == "empty":
        _require(not refs and failure_code is None, "empty-attempt-shape")
    else:
        _text(failure_code, "attempt-failure-code-required")
        _require(not refs, "incomplete-attempt-cannot-claim-evidence")

    payload = {
        "attempt_id": attempt_id,
        "candidate_ref": candidate_ref,
        "evidence_snapshot_sha256": _hash_json(evidence_snapshot),
        "material_missing_evidence": missing,
        "material_missing_evidence_sha256": _hash_json(missing),
        "action": normalized_action,
        "action_sha256": None if normalized_action is None else _hash_json(normalized_action),
        "status": status,
        "evidence_refs": deepcopy(refs),
        "failure_code": failure_code,
    }
    return {**payload, "attempt_sha256": _hash_json(payload)}


def _validate_attempt(record: dict) -> dict:
    fields = {
        "attempt_id",
        "candidate_ref",
        "evidence_snapshot_sha256",
        "material_missing_evidence",
        "material_missing_evidence_sha256",
        "action",
        "action_sha256",
        "status",
        "evidence_refs",
        "failure_code",
        "attempt_sha256",
    }
    _require(isinstance(record, dict) and set(record) == fields, "attempt-record-shape")
    _text(record["attempt_id"], "attempt-id-required")
    ref = record["candidate_ref"]
    _require(
        isinstance(ref, dict)
        and set(ref) == {"candidate_id", "candidate_version", "candidate_sha256"},
        "attempt-candidate-ref-shape",
    )
    _text(ref["candidate_id"], "attempt-candidate-id-required")
    _require(type(ref["candidate_version"]) is int and ref["candidate_version"] > 0,
             "attempt-candidate-version-invalid")
    _sha256(ref["candidate_sha256"], "attempt-candidate-hash-invalid")
    _sha256(record["evidence_snapshot_sha256"], "attempt-evidence-hash-invalid")
    missing = _normalize_missing_evidence(record["material_missing_evidence"])
    _sha256(record["material_missing_evidence_sha256"], "attempt-missing-evidence-hash-invalid")
    _require(
        record["material_missing_evidence_sha256"] == _hash_json(missing),
        "attempt-missing-evidence-hash-mismatch",
    )
    action = _normalize_action(record["action"])
    expected_action_hash = None if action is None else _hash_json(action)
    _require(record["action_sha256"] == expected_action_hash, "attempt-action-hash-mismatch")
    status = record["status"]
    _require(isinstance(status, str) and status in ATTEMPT_STATUSES, "attempt-status-invalid")
    refs = record["evidence_refs"]
    _require(
        isinstance(refs, list)
        and all(isinstance(ref, str) and bool(ref.strip()) for ref in refs)
        and len(refs) == len(set(refs)),
        "attempt-evidence-refs-invalid",
    )
    if status == "success":
        _require(bool(refs) and record["failure_code"] is None, "success-requires-evidence")
    elif status == "empty":
        _require(not refs and record["failure_code"] is None, "empty-attempt-shape")
    else:
        _text(record["failure_code"], "attempt-failure-code-required")
        _require(not refs, "incomplete-attempt-cannot-claim-evidence")
    _sha256(record["attempt_sha256"], "attempt-hash-invalid")
    payload = {key: value for key, value in record.items() if key != "attempt_sha256"}
    _require(record["attempt_sha256"] == _hash_json(payload), "attempt-hash-mismatch")
    return deepcopy(record)


def _repeat_assessment(proposed_action, history):
    basis = "exact-canonical-action-hash-and-current-bindings-only"
    if proposed_action is None:
        return {
            "status": "not-planned",
            "attempt_ids": [],
            "no_progress": None,
            "comparison_basis": basis,
        }
    action_hash = _hash_json(proposed_action)
    matching = [
        row["record"]
        for row in history
        if row["binding_status"] == "current" and row["record"]["action_sha256"] == action_hash
    ]
    if not matching:
        stale_matches = [
            row["record"]["attempt_id"]
            for row in history
            if row["binding_status"] == "historical"
            and row["record"]["action_sha256"] == action_hash
        ]
        return {
            "status": "unknown-stale-history" if stale_matches else "new-action",
            "attempt_ids": stale_matches,
            "no_progress": None,
            "comparison_basis": basis,
        }
    latest = matching[-1]
    previous_success_refs = {
        ref
        for row in matching[:-1]
        if row["status"] == "success"
        for ref in row["evidence_refs"]
    }
    new_refs = sorted(set(latest["evidence_refs"]) - previous_success_refs)
    no_progress = latest["status"] != "success" or not new_refs
    return {
        "status": "identical-action-no-progress" if no_progress else "identical-action-new-refs",
        "attempt_ids": [row["attempt_id"] for row in matching],
        "latest_status": latest["status"],
        "new_evidence_refs": new_refs,
        "no_progress": no_progress,
        "comparison_basis": basis,
    }


def build_followup_sidecar(
    candidate: dict,
    evidence_snapshot,
    material_missing_evidence: list[dict],
    *,
    resource_cost: dict,
    attempt_history: list[dict] | None = None,
    proposed_action=None,
) -> dict:
    """Build an optional sidecar from supplied state, without executing work."""
    candidate_ref = _candidate_ref(candidate)
    missing = _normalize_missing_evidence(material_missing_evidence)
    current_evidence_hash = _hash_json(evidence_snapshot)
    missing_hash = _hash_json(missing)
    normalized_cost = _normalize_resource_cost(resource_cost)
    proposed_action = _normalize_action(proposed_action)
    _require(attempt_history is None or isinstance(attempt_history, list), "attempt-history-list-required")

    history = []
    attempt_ids = set()
    for raw in attempt_history or []:
        record = _validate_attempt(raw)
        _require(record["attempt_id"] not in attempt_ids, "duplicate-attempt-id")
        attempt_ids.add(record["attempt_id"])
        _require(
            record["candidate_ref"]["candidate_id"] == candidate_ref["candidate_id"],
            "attempt-candidate-id-mismatch",
        )
        current = (
            record["candidate_ref"] == candidate_ref
            and record["evidence_snapshot_sha256"] == current_evidence_hash
            and record["material_missing_evidence_sha256"] == missing_hash
            and record["material_missing_evidence"] == missing
        )
        history.append({"record": record, "binding_status": "current" if current else "historical"})

    payload = {
        "format": FORMAT,
        "candidate_ref": candidate_ref,
        "evidence_snapshot_sha256": current_evidence_hash,
        "material_missing_evidence": missing,
        "material_missing_evidence_sha256": missing_hash,
        "resource_cost": normalized_cost,
        "attempt_history": history,
        "proposed_action": proposed_action,
        "repeat_assessment": _repeat_assessment(proposed_action, history),
        "execution_authorized": False,
        "additional_retry_authority_granted": False,
    }
    return {**payload, "sidecar_sha256": _hash_json(payload)}


def validate_followup_sidecar(
    sidecar: dict | None,
    candidate: dict,
    evidence_snapshot,
    material_missing_evidence: list[dict],
    resource_cost: dict,
) -> dict:
    """Return current or fail-closed unknown; stale inputs never validate."""
    try:
        fields = {
            "format",
            "candidate_ref",
            "evidence_snapshot_sha256",
            "material_missing_evidence",
            "material_missing_evidence_sha256",
            "resource_cost",
            "attempt_history",
            "proposed_action",
            "repeat_assessment",
            "execution_authorized",
            "additional_retry_authority_granted",
            "sidecar_sha256",
        }
        _require(isinstance(sidecar, dict) and set(sidecar) == fields, "sidecar-shape")
        _require(sidecar["format"] == FORMAT, "sidecar-format-unsupported")
        _sha256(sidecar["sidecar_sha256"], "sidecar-hash-invalid")
        payload = {key: value for key, value in sidecar.items() if key != "sidecar_sha256"}
        _require(sidecar["sidecar_sha256"] == _hash_json(payload), "sidecar-hash-mismatch")
        _require(sidecar["candidate_ref"] == _candidate_ref(candidate), "stale-candidate-binding")
        _require(sidecar["evidence_snapshot_sha256"] == _hash_json(evidence_snapshot),
                 "stale-evidence-binding")
        current_missing = _normalize_missing_evidence(material_missing_evidence)
        _require(
            sidecar["material_missing_evidence_sha256"] == _hash_json(current_missing)
            and sidecar["material_missing_evidence"] == current_missing,
            "stale-missing-evidence-binding",
        )
        _require(sidecar["resource_cost"] == _normalize_resource_cost(resource_cost),
                 "stale-resource-cost-binding")
        _require(sidecar["execution_authorized"] is False, "sidecar-authority-invalid")
        _require(sidecar["additional_retry_authority_granted"] is False, "sidecar-retry-authority-invalid")
        _require(isinstance(sidecar["attempt_history"], list), "sidecar-history-list-required")
        records = []
        for row in sidecar["attempt_history"]:
            _require(isinstance(row, dict) and set(row) == {"record", "binding_status"},
                     "sidecar-history-row-shape")
            records.append(row["record"])
        expected = build_followup_sidecar(
            candidate,
            evidence_snapshot,
            current_missing,
            resource_cost=resource_cost,
            attempt_history=records,
            proposed_action=sidecar["proposed_action"],
        )
        _require(expected == sidecar, "sidecar-reconstruction-mismatch")
    except (FollowupSidecarError, DirectionReviewError) as exc:
        reason = exc.code if isinstance(exc, FollowupSidecarError) else "non-canonical-json-input"
        return {
            "record_status": "unknown",
            "reason": reason,
            "execution_authorized": False,
            "additional_retry_authority_granted": False,
        }
    return {
        "record_status": "current",
        "binding_status": "current",
        "repeat_assessment": deepcopy(sidecar["repeat_assessment"]),
        "execution_authorized": False,
        "additional_retry_authority_granted": False,
    }
