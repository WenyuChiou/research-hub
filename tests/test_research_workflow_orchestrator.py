"""Contract tests for the human-in-the-loop research workflow skill."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "research-workflow-orchestrator"
MIRROR = (
    ROOT
    / "src"
    / "research_hub"
    / "skills_data"
    / "research-workflow-orchestrator"
)

EXPECTED_STAGES = [
    "orient",
    "scope",
    "discover",
    "synthesize",
    "design",
    "execute",
    "write",
    "release",
]
REQUIRED_GATES = {
    "scope_commitment",
    "external_write",
    "experiment_authorization",
    "semantic_revision",
    "release_authorization",
}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _schema() -> dict:
    return _load_json(SKILL / "references" / "workflow-state.schema.json")


def _fixture() -> dict:
    return yaml.safe_load(
        (ROOT / "tests" / "fixtures" / "research_workflow_state_valid.yml").read_text(
            encoding="utf-8"
        )
    )


def _validator() -> Draft202012Validator:
    return Draft202012Validator(_schema(), format_checker=FormatChecker())


def test_skill_ships_complete_progressive_disclosure_bundle():
    expected = {
        Path("SKILL.md"),
        Path("evals/evals.json"),
        Path("references/tool-adapters.md"),
        Path("references/evidence-agent-harness.md"),
        Path("references/workflow-contract.md"),
        Path("references/workflow-state.schema.json"),
    }
    actual = {p.relative_to(SKILL) for p in SKILL.rglob("*") if p.is_file()}
    assert expected <= actual


def test_workflow_contract_defines_stages_and_human_gates():
    contract = (SKILL / "references" / "workflow-contract.md").read_text(
        encoding="utf-8"
    )
    for stage in EXPECTED_STAGES:
        assert f"`{stage}`" in contract
    for gate in REQUIRED_GATES:
        assert f"`{gate}`" in contract
    for decision in ("accept", "decline", "cancel"):
        assert f"`{decision}`" in contract
    assert "Never collect secrets" in contract
    assert "bounded" in contract.lower()


def test_state_schema_has_resumable_decisions_and_artifact_provenance():
    schema = _schema()
    Draft202012Validator.check_schema(schema)
    assert schema["$schema"].startswith("https://json-schema.org/")
    required = set(schema["required"])
    assert {
        "schema_version",
        "workflow_id",
        "current_stage",
        "status",
        "actions",
        "decisions",
        "artifacts",
        "pending_action",
    } <= required

    stage_enum = schema["$defs"]["stage"]["enum"]
    assert stage_enum == EXPECTED_STAGES
    decision_enum = schema["$defs"]["decision"]["properties"]["outcome"]["enum"]
    assert decision_enum == ["accept", "decline", "revise", "cancel"]
    assert "cancelled" in schema["properties"]["status"]["enum"]
    decision_required = set(schema["$defs"]["decision"]["required"])
    assert {"action_id", "action_hash", "scope", "parameters_hash", "resource_bounds", "authorization_source"} <= decision_required
    action_required = set(schema["$defs"]["action"]["required"])
    assert {"action_id", "action_hash", "attempts", "validation_contract", "input_hashes"} <= action_required
    artifact_required = set(schema["$defs"]["artifact"]["required"])
    assert {"path", "stage", "sha256", "created_at"} <= artifact_required


def test_example_state_validates_against_shipped_schema():
    errors = list(_validator().iter_errors(_fixture()))
    assert not errors, "\n".join(error.message for error in errors)


def test_unscoped_approval_and_secret_field_fail_closed():
    state = _fixture()
    del state["decisions"][0]["action_id"]
    assert list(_validator().iter_errors(state))

    state = _fixture()
    state["pending_action"]["api_key"] = "must-never-be-stored"
    assert list(_validator().iter_errors(state))


def test_malformed_action_envelope_is_rejected():
    state = _fixture()
    state["actions"][0]["attempts"] = [
        {
            "number": 1,
            "started_at": "2026-08-30T14:00:00Z",
            "finished_at": "2026-08-30T14:01:00Z",
            "status": "success",
            "outputs": [],
        }
    ]
    assert list(_validator().iter_errors(state))


def test_cancelled_is_clean_terminal_state_with_scoped_cancel_decision():
    state = _fixture()
    state["status"] = "cancelled"
    state["pending_action"] = None
    state["blocker"] = None
    cancel = copy.deepcopy(state["decisions"][0])
    cancel.update({"action_id": "cancel-workflow", "outcome": "cancel", "rationale": "Researcher ended the workflow."})
    state["decisions"].append(cancel)
    assert not list(_validator().iter_errors(state))

    state["decisions"].pop()
    assert list(_validator().iter_errors(state))


def test_waiting_for_human_requires_a_gated_pending_action():
    state = _fixture()
    state["status"] = "waiting_for_human"
    state["pending_action"]["gate"] = None
    assert list(_validator().iter_errors(state))


def test_completed_requires_release_stage_and_accepted_release_gate():
    state = _fixture()
    state["status"] = "completed"
    state["pending_action"] = None
    state["blocker"] = None
    assert list(_validator().iter_errors(state))

    release = copy.deepcopy(state["decisions"][0])
    release.update({"action_id": "release-project", "gate": "release_authorization", "outcome": "decline"})
    state["current_stage"] = "release"
    state["decisions"].append(release)
    assert list(_validator().iter_errors(state))

    state["decisions"][-1]["outcome"] = "accept"
    assert not list(_validator().iter_errors(state))


def test_blocked_requires_nonempty_recovery_condition():
    state = _fixture()
    state["status"] = "blocked"
    state.pop("blocker", None)
    assert list(_validator().iter_errors(state))
    state["blocker"] = ""
    assert list(_validator().iter_errors(state))
    state["blocker"] = "Install the missing scholarly API adapter and resume."
    assert not list(_validator().iter_errors(state))


def test_tool_adapters_cover_each_stage_and_capability_fallback():
    adapters = (SKILL / "references" / "tool-adapters.md").read_text(
        encoding="utf-8"
    )
    for stage in EXPECTED_STAGES:
        assert f"| `{stage}` |" in adapters
    assert "capability negotiation" in adapters.lower()
    assert "elicitation" in adapters.lower()
    assert "chat/CLI fallback" in adapters
    assert "Never put credentials" in adapters


def test_skill_and_installer_mirror_are_byte_identical():
    source_files = {p.relative_to(SKILL) for p in SKILL.rglob("*") if p.is_file()}
    mirror_files = {p.relative_to(MIRROR) for p in MIRROR.rglob("*") if p.is_file()}
    assert source_files == mirror_files
    for rel in source_files:
        assert (SKILL / rel).read_bytes() == (MIRROR / rel).read_bytes()
