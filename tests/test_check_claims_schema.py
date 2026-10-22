"""Tests for ``scripts/check_claims_schema.py`` and the anti-leakage
schema at ``skills/paper-memory-builder/references/claims.schema.json``.

Three layers:

1. **Meta**: the schema itself conforms to Draft 2020-12.
2. **Positive**: well-formed claims.yml fixtures validate clean.
3. **Negative**: every flavor of the anti-leakage violation is correctly
   rejected. This is the load-bearing layer — guards the schema from
   being silently weakened.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = (
    REPO_ROOT
    / "skills"
    / "paper-memory-builder"
    / "references"
    / "claims.schema.json"
)


@pytest.fixture(scope="module")
def schema() -> dict:
    with SCHEMA_PATH.open(encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def validator(schema):
    return Draft202012Validator(schema)


def _has_errors(validator, data) -> bool:
    return bool(list(validator.iter_errors(data)))


# ---------------------------------------------------------------------------
# Layer 1: meta
# ---------------------------------------------------------------------------

def test_schema_itself_is_valid_draft_2020_12(schema):
    Draft202012Validator.check_schema(schema)


# ---------------------------------------------------------------------------
# Layer 2: positive
# ---------------------------------------------------------------------------

def test_fully_evidenced_supported_claim_passes(validator):
    data = {
        "claims": [
            {
                "id": "C1",
                "text": "Coupled ABM-CAT reduces flood-impact RMSE by 22%.",
                "evidence_artifacts": [
                    "outputs/E2/calibration.csv",
                    "outputs/E2/figure3.png",
                ],
                "figure_or_table": ["Fig3"],
                "status": "supported",
                "sentence_in_manuscript": "...22% reduction in RMSE...",
            }
        ]
    }
    assert not _has_errors(validator, data)


def test_draft_claim_with_evidence_passes(validator):
    data = {
        "claims": [
            {
                "id": "C2",
                "text": "Subsidy treatment narrows post-disaster housing-cost gap.",
                "evidence_artifacts": ["outputs/E5/eh_results.csv"],
                "status": "draft",
                "risk": "Effect size sensitive to calibration window.",
            }
        ]
    }
    assert not _has_errors(validator, data)


def test_gap_claim_with_empty_evidence_and_gap_reason_passes(validator):
    data = {
        "claims": [
            {
                "id": "C3",
                "text": "Intro claim about long-term FFE that no E-run backs yet.",
                "evidence_artifacts": [],
                "status": "gap",
                "gap_reason": "intro-only claim; flag for next E-run scope.",
            }
        ]
    }
    assert not _has_errors(validator, data)


def test_rejected_claim_with_empty_evidence_passes(validator):
    # status='rejected' keeps the row for audit trail; empty evidence
    # is allowed without gap_reason because the claim was dropped.
    data = {
        "claims": [
            {
                "id": "C4",
                "text": "Previously claimed flood-damage threshold.",
                "evidence_artifacts": [],
                "status": "rejected",
            }
        ]
    }
    assert not _has_errors(validator, data)


# ---------------------------------------------------------------------------
# Layer 3: negative (the anti-leakage assertions)
# ---------------------------------------------------------------------------

def test_empty_evidence_with_status_draft_fails(validator):
    """The headline anti-leakage violation: an unsupported claim
    shipped as if it were under-writing-only."""
    data = {
        "claims": [
            {
                "id": "C1",
                "text": "Intro asserts but no experiment backs it.",
                "evidence_artifacts": [],
                "status": "draft",
            }
        ]
    }
    assert _has_errors(validator, data)


def test_empty_evidence_with_status_supported_fails(validator):
    """Even worse: an unsupported claim shipped as 'supported'."""
    data = {
        "claims": [
            {
                "id": "C1",
                "text": "Intro asserts but no experiment backs it.",
                "evidence_artifacts": [],
                "status": "supported",
            }
        ]
    }
    assert _has_errors(validator, data)


def test_absent_evidence_field_with_status_draft_fails(validator):
    """Same as empty list — absent evidence_artifacts is identically
    an anti-leakage violation when status is draft."""
    data = {
        "claims": [
            {
                "id": "C1",
                "text": "Intro asserts but no experiment backs it.",
                "status": "draft",
                # evidence_artifacts missing entirely
            }
        ]
    }
    assert _has_errors(validator, data)


def test_gap_status_without_gap_reason_fails(validator):
    """gap requires gap_reason (per the schema 'if status==gap then
    gap_reason' rule). A gap claim without explanation is the
    documentation equivalent of an anti-leakage violation."""
    data = {
        "claims": [
            {
                "id": "C1",
                "text": "Some unsupported claim.",
                "evidence_artifacts": [],
                "status": "gap",
                # gap_reason missing
            }
        ]
    }
    assert _has_errors(validator, data)


def test_gap_status_with_empty_gap_reason_fails(validator):
    """gap_reason has minLength: 1 — an empty string is not a real reason."""
    data = {
        "claims": [
            {
                "id": "C1",
                "text": "Some unsupported claim.",
                "evidence_artifacts": [],
                "status": "gap",
                "gap_reason": "",
            }
        ]
    }
    assert _has_errors(validator, data)


# ---------------------------------------------------------------------------
# Schema-shape guardrails
# ---------------------------------------------------------------------------

def test_invalid_id_pattern_fails(validator):
    data = {
        "claims": [
            {
                "id": "claim-1",  # must be ^C[0-9]+$
                "text": "Some claim.",
                "evidence_artifacts": ["outputs/e2/data.csv"],
                "status": "draft",
            }
        ]
    }
    assert _has_errors(validator, data)


def test_unknown_status_value_fails(validator):
    data = {
        "claims": [
            {
                "id": "C1",
                "text": "Some claim.",
                "evidence_artifacts": ["outputs/e2/data.csv"],
                "status": "pending",  # not in enum
            }
        ]
    }
    assert _has_errors(validator, data)


def test_empty_claim_text_fails(validator):
    data = {
        "claims": [
            {
                "id": "C1",
                "text": "",
                "evidence_artifacts": ["outputs/e2/data.csv"],
                "status": "draft",
            }
        ]
    }
    assert _has_errors(validator, data)


def test_top_level_missing_claims_field_fails(validator):
    data = {"figures": []}
    assert _has_errors(validator, data)


@pytest.mark.parametrize("status", ["draft", "supported", "gap", "rejected", "dropped", "pending"])
@pytest.mark.parametrize("evidence", [None, [], ["outputs/not-verified.csv"]], ids=["absent", "empty", "pointers"])
@pytest.mark.parametrize("reason", [None, "", "Scope remains unresolved."], ids=["absent-reason", "empty-reason", "reason"])
def test_status_evidence_reason_contract(validator, status, evidence, reason):
    claim = {"id": "C27", "text": "Synthetic contract fixture.", "status": status}
    if evidence is not None:
        claim["evidence_artifacts"] = evidence
    if reason is not None:
        claim["gap_reason"] = reason
    expected = (
        status in {"draft", "supported", "gap", "rejected"}
        and reason != ""
        and (status != "gap" or bool(reason))
        and (bool(evidence) or status in {"gap", "rejected"})
    )
    assert (not _has_errors(validator, {"claims": [claim]})) == expected


@pytest.fixture(scope="module")
def checker():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "check_claims_schema", REPO_ROOT / "scripts/check_claims_schema.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("status", ["rejected", "gap", "draft", "dropped", "pending"])
def test_validation_preserves_ids_unknown_fields_and_original_bytes(
    validator, checker, tmp_path, status, capsys
):
    from copy import deepcopy

    data = {
        "custom_root": {"revision": [3, 7]},
        "claims": [
            {"id": "C27", "text": "Retained historical row.", "status": status,
             "custom_claim": {"review_note": "Keep exactly."}},
            {"id": "C5", "text": "Other historical row.", "status": "rejected"},
        ],
    }
    original = deepcopy(data)
    valid = status == "rejected"
    assert (not _has_errors(validator, data)) == valid
    assert data == original
    path = tmp_path / "claims.yml"
    path.write_text("# Preserve human formatting and notes.\n" + yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    before = path.read_bytes()
    assert bool(checker.validate_file(path, validator)) == (not valid)
    assert checker.main([str(path)]) == (0 if valid else 1)
    if not valid:
        assert "claims[0]" in capsys.readouterr().err
    assert path.read_bytes() == before
    assert yaml.safe_load(path.read_text(encoding="utf-8")) == original


@pytest.mark.parametrize("text", ["claims: [", "", "claims: null\n"])
def test_invalid_yaml_or_root_is_not_rewritten(checker, validator, tmp_path, text):
    path = tmp_path / "claims.yml"
    path.write_text(text, encoding="utf-8")
    before = path.read_bytes()
    assert checker.validate_file(path, validator)
    assert path.read_bytes() == before


def test_documented_claim_examples_match_machine_contract(validator):
    import re

    path = REPO_ROOT / "skills/paper-memory-builder/references/yaml-schemas.md"
    examples = [yaml.safe_load(block) for block in re.findall(r"```yaml\n(.*?)```", path.read_text(encoding="utf-8"), re.S)]
    claims_examples = [data for data in examples if "claims" in data]
    assert claims_examples
    seen = set()
    for data in claims_examples:
        assert not _has_errors(validator, data)
        seen.update(claim["status"] for claim in data["claims"])
    assert {"draft", "gap", "rejected"} <= seen


def test_editorial_removal_documentation_stays_consistent(schema, checker):
    # Target the previously contradictory contract passages, not incidental prose.
    skill = REPO_ROOT / "skills/paper-memory-builder"
    texts = [
        (skill / "SKILL.md").read_text(encoding="utf-8").split("## Anti-leakage rule", 1)[1],
        (skill / "references/yaml-schemas.md").read_text(encoding="utf-8").split("### Anti-leakage rule", 1)[1].split("## `.paper/figures.yml`", 1)[0],
        (skill / "references/revision_history_schema.md").read_text(encoding="utf-8").split("### Sync with", 1)[1].split("## Example", 1)[0],
        checker.__doc__,
    ]
    for text in texts:
        normalized = " ".join(text.lower().split())
        assert "rejected" in normalized
        assert "editorial" in normalized
        assert "not scientific contradiction" in normalized
        assert "gap_reason" in normalized
    assert "rejected" in schema["description"]
    assert "rejected" in schema["$defs"]["claim"]["allOf"][0]["$comment"]
    assert schema["$defs"]["claim"]["properties"]["status"]["enum"] == ["draft", "supported", "rejected", "gap"]
