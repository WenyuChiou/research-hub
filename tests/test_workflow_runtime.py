"""Offline behavior tests for the workflow state manager and evidence boundary."""

from __future__ import annotations

import copy
import hashlib
import io
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import yaml

from research_hub import mcp_server
from research_hub.cli import build_parser, main
from research_hub.evidence_harness import (
    ROLE_PROFILES,
    filter_agent_results,
    synthesize_evidence_packet,
    validate_evidence_packet,
)
from research_hub.doctor import check_agent_collab_harness
from research_hub.workflow_runtime import (
    WorkflowContractError,
    decide_workflow,
    harness_status,
    initialize_workflow,
    load_state,
    migrate_workflow,
    prepare_external_action,
    record_external_result,
    resume_workflow,
    validate_workflow,
    workflow_status,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "research_workflow_state_valid.yml"


def _state() -> dict:
    return yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))


def _write(path: Path, state: dict) -> None:
    path.write_text(yaml.safe_dump(state, sort_keys=False), encoding="utf-8")


def _gated_state(path: Path) -> dict:
    state = _state()
    state["status"] = "waiting_for_human"
    state["pending_action"]["gate"] = "external_write"
    _write(path, state)
    return state


def test_init_validate_status_and_cli_mcp_parity(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("RESEARCH_HUB_WORKFLOW_ROOT", str(tmp_path))
    result = initialize_workflow(tmp_path, workflow_id="wf-contract")
    state_path = Path(result["state_path"])
    assert validate_workflow(state_path)["ok"] is True

    cli_rc = main(["workflow", "status", "--state", str(state_path), "--json"])
    cli_report = json.loads(capsys.readouterr().out)
    mcp_fn = getattr(mcp_server.workflow_status, "fn", mcp_server.workflow_status)
    mcp_report = mcp_fn(str(state_path))
    assert cli_rc == 0
    assert cli_report["workflow_id"] == mcp_report["workflow_id"] == "wf-contract"
    assert cli_report["status"] == mcp_report["status"] == "running"


def test_parser_exposes_all_workflow_commands():
    parser = build_parser()
    for command in ("init", "status", "validate", "decide", "resume", "migrate"):
        extra = [
            "--outcome", "accept", "--actor", "human:test", "--rationale", "approved",
            "--action-hash", "a" * 64,
        ] if command == "decide" else []
        args = parser.parse_args(["workflow", command, *extra])
        assert args.workflow_command == command
        assert args.json is False


def test_mcp_rejects_workflow_state_outside_canonical_research_dir(tmp_path):
    unsafe = tmp_path / "workflow_state.yml"
    mcp_fn = getattr(mcp_server.workflow_validate, "fn", mcp_server.workflow_validate)
    report = mcp_fn(str(unsafe))
    assert report["ok"] is False
    assert "under a .research directory" in report["error"]


def test_mcp_workflow_root_is_server_controlled(monkeypatch, tmp_path):
    trusted = tmp_path / "trusted"
    trusted.mkdir()
    monkeypatch.setenv("RESEARCH_HUB_WORKFLOW_ROOT", str(trusted))
    mcp_fn = getattr(mcp_server.workflow_initialize, "fn", mcp_server.workflow_initialize)
    rejected = mcp_fn(str(tmp_path / "outside"))
    accepted = mcp_fn(str(trusted / "project"), workflow_id="mcp-safe")
    assert rejected["ok"] is False
    assert "RESEARCH_HUB_WORKFLOW_ROOT" in rejected["error"]
    assert accepted["ok"] is True
    assert Path(accepted["state_path"]).is_relative_to(trusted)


def test_migration_is_dry_run_by_default_then_atomic_with_backup(tmp_path):
    legacy = _state()
    opaque_hex_identifier = "A" * 64
    legacy["schema_version"] = "1.0"
    legacy["workflow_id"] = opaque_hex_identifier
    for key in (
        "trace_id", "correlation_id", "policy_checkpoint_ref", "policy_hash",
        "evidence_packet_refs", "attempt_history", "pending_external_action",
        "external_write_ledger", "recovery_status", "migration_history",
    ):
        legacy.pop(key)
    legacy.pop("blocker")
    legacy["artifacts"][0]["sha256"] = legacy["artifacts"][0]["sha256"].upper()
    legacy["actions"][0].pop("action_hash")
    legacy["pending_action"].pop("action_hash")
    legacy["pending_action"].pop("resource_bounds")
    decision = legacy["decisions"][0]
    decision.pop("action_hash")
    decision.pop("authorization_source")
    decision["summary"] = decision.pop("rationale")
    decision["summary"] = opaque_hex_identifier
    decision["preview_hash"] = "d" * 64
    legacy["artifacts"][0]["path"] = opaque_hex_identifier
    legacy["pending_action"]["scope"] = [opaque_hex_identifier]
    path = tmp_path / "state.yml"
    _write(path, legacy)
    original = path.read_bytes()

    preview = migrate_workflow(path)
    assert preview["dry_run"] is True
    assert path.read_bytes() == original
    assert workflow_status(path)["migration_required"] is True

    applied = migrate_workflow(path, apply=True)
    assert applied["applied"] is True
    assert Path(applied["backup_path"]).read_bytes() == original
    assert load_state(path)["schema_version"] == "1.1"
    assert validate_workflow(path)["ok"] is True
    migrated_state = load_state(path)
    assert migrated_state["artifacts"][0]["sha256"].islower()
    assert migrated_state["workflow_id"] == opaque_hex_identifier
    assert migrated_state["artifacts"][0]["path"] == opaque_hex_identifier
    assert migrated_state["pending_action"]["scope"] == [opaque_hex_identifier]
    assert migrated_state["decisions"][0]["rationale"] == opaque_hex_identifier


@pytest.mark.parametrize(
    ("outcome", "expected_status"),
    [("decline", "declined"), ("cancel", "cancelled")],
)
def test_decline_and_cancel_are_terminal_non_success(tmp_path, outcome, expected_status):
    path = tmp_path / "state.yml"
    state = _gated_state(path)
    result = decide_workflow(
        path,
        outcome=outcome,
        actor="human:researcher",
        rationale=f"researcher chose {outcome}",
        action_hash=state["pending_action"]["action_hash"],
    )
    assert result["ok"] is False
    assert result["state"]["status"] == expected_status
    assert result["state"]["pending_action"] is None
    resumed = resume_workflow(path)
    assert resumed["resumed"] is False
    assert resumed["reason"] == f"terminal:{expected_status}"


def test_crash_after_external_write_requires_reconciliation(tmp_path):
    state_path = Path(initialize_workflow(tmp_path)["state_path"])
    action = {"action_id": "write-zotero-note", "tool": "zotero", "mode": "write", "scope": ["item:ABC"]}
    prepared = prepare_external_action(state_path, action)
    resumed = resume_workflow(state_path)
    assert prepared["ok"] is True
    assert resumed["ok"] is False
    assert resumed["reason"] == "reconcile_required"
    assert resumed["state"]["status"] == "blocked"


def test_unresolved_external_action_cannot_be_overwritten(tmp_path):
    state_path = Path(initialize_workflow(tmp_path)["state_path"])
    prepare_external_action(state_path, {"action_id": "first", "payload": {"value": "A"}})
    with pytest.raises(WorkflowContractError, match="unresolved external action"):
        prepare_external_action(state_path, {"action_id": "second", "payload": {"value": "B"}})


def test_external_action_hash_binds_full_payload_and_rejects_spoof(tmp_path):
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first = Path(initialize_workflow(first_root)["state_path"])
    second = Path(initialize_workflow(second_root)["state_path"])
    first_result = prepare_external_action(first, {"action_id": "write", "payload": {"value": "A"}})
    second_result = prepare_external_action(second, {"action_id": "write", "payload": {"value": "B"}})
    assert first_result["action_hash"] != second_result["action_hash"]
    third = Path(initialize_workflow(tmp_path / "third")["state_path"])
    with pytest.raises(WorkflowContractError, match="complete action payload"):
        prepare_external_action(
            third,
            {"action_id": "write", "payload": {"value": "B"}, "action_hash": first_result["action_hash"]},
        )


def test_concurrent_prepare_serializes_and_only_one_wins(tmp_path):
    state_path = Path(initialize_workflow(tmp_path)["state_path"])

    def prepare(value):
        try:
            return prepare_external_action(state_path, {"action_id": value, "payload": value})["ok"]
        except WorkflowContractError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(prepare, ("A", "B")))
    assert sorted(results) == [False, True]


def test_duplicate_external_write_hash_is_rejected(tmp_path):
    state_path = Path(initialize_workflow(tmp_path)["state_path"])
    action = {"action_id": "upload-nlm", "tool": "notebooklm", "mode": "write", "scope": ["notebook:1"]}
    prepared = prepare_external_action(state_path, action)
    record_external_result(state_path, action_hash=prepared["action_hash"], result_ref="nlm:source:1")
    with pytest.raises(WorkflowContractError, match="already recorded"):
        prepare_external_action(state_path, action)


def test_configured_harness_unavailable_is_misconfigured(monkeypatch, tmp_path):
    policy = tmp_path / "policy.json"
    policy.write_text("{}", encoding="utf-8")

    def unavailable(name):
        if name == "agent_collab_harness":
            raise ImportError(name)
        raise AssertionError(name)

    monkeypatch.setattr("research_hub.workflow_runtime.importlib.import_module", unavailable)
    status = harness_status(policy)
    assert status["status"] == "misconfigured"
    assert status["available"] is False


def test_public_harness_strict_json_rejects_duplicate_policy_keys(tmp_path):
    pytest.importorskip("agent_collab_harness")
    policy = tmp_path / "duplicate-policy.json"
    policy.write_text('{"schema_version": 1, "schema_version": 1}', encoding="utf-8")
    status = harness_status(policy)
    assert status["status"] == "misconfigured"
    assert "duplicate JSON key" in status["message"]


def test_doctor_reports_optional_harness_state(monkeypatch):
    monkeypatch.setattr(
        "research_hub.workflow_runtime.harness_status",
        lambda: {
            "status": "unavailable",
            "available": False,
            "configured": False,
            "version": None,
            "policy_path": None,
            "message": "optional harness is not installed",
        },
    )
    result = check_agent_collab_harness()
    assert result.name == "agent_collab_harness"
    assert result.status == "INFO"


def test_accept_rejects_self_asserted_actor_and_unsigned_human(tmp_path):
    path = tmp_path / "state.yml"
    state = _gated_state(path)
    for actor in ("delegated-executor", "human:self-asserted"):
        with pytest.raises(WorkflowContractError):
            decide_workflow(
                path,
                outcome="accept",
                actor=actor,
                rationale="self asserted",
                action_hash=state["pending_action"]["action_hash"],
            )


def test_local_tty_accept_requires_exact_action_hash(monkeypatch, tmp_path, capsys):
    path = tmp_path / "state.yml"
    state = _gated_state(path)
    action_hash = state["pending_action"]["action_hash"]

    class TTYInput(io.StringIO):
        def isatty(self):
            return True

    monkeypatch.setattr("sys.stdin", TTYInput(f"accept {action_hash}\n"))
    result = main([
        "workflow", "decide", "--state", str(path), "--outcome", "accept",
        "--actor", "human:researcher", "--rationale", "exact local approval",
        "--action-hash", action_hash, "--interactive", "--json",
    ])
    report = json.loads(capsys.readouterr().out)
    assert result == 0
    assert report["decision"]["authorization_source"] == "local_tty"


def test_signed_release_checkpoint_authorizes_accept(monkeypatch, tmp_path):
    harness = pytest.importorskip("agent_collab_harness")
    secret = "test-human-secret"
    key_hash = hashlib.sha256(secret.encode("utf-8")).hexdigest()
    policy = {
        "schema_version": 1,
        "policy_id": "research-hub-test",
        "limits": {
            "max_cycles": 3,
            "max_tool_calls": 10,
            "max_elapsed_seconds": 60,
            "checkpoint_transcript_bytes": 100,
            "max_transcript_bytes": 200,
            "max_same_failure_retries": 2,
            "max_no_evidence_cycles": 2,
            "max_children_per_parent": 4,
            "max_concurrency": 2,
            "max_task_packet_tokens": 500,
            "max_parent_summary_tokens": 100,
            "max_memory_digest_tokens": 100,
            "max_child_result_words": 50,
        },
        "human_authorization": {"key_hashes": {"owner": key_hash}},
    }
    decision = {
        "gate": "external_write",
        "actor": "human:owner",
        "decision": "approve",
        "timestamp": "2026-08-31T00:00:00Z",
        "rationale": "approved exact action",
        "affected_action_hash": "f" * 64,
    }
    decision["authorization"] = {
        "scheme": "hmac-sha256",
        "key_id": "owner",
        "signature": harness.sign_human_record(decision, secret),
    }
    checkpoint = {
        "schema_version": 1,
        "task_id": "research-task",
        "parent_id": None,
        "status": "running",
        "cycle": 0,
        "tool_calls": 0,
        "elapsed_seconds": 0,
        "transcript_bytes": 0,
        "same_failure_retries": 0,
        "no_evidence_cycles": 0,
        "active_children": 0,
        "children_spawned": 0,
        "last_checkpoint_transcript_bytes": 0,
        "task_packet_tokens": 0,
        "parent_summary_tokens": 0,
        "memory_digest_tokens": 0,
        "child_result_words": 0,
        "evidence_refs": [],
        "decisions": [decision],
        "overrides": [],
        "stop_reason": None,
        "pending_action_hash": "f" * 64,
        "updated_at": "2026-08-31T00:00:00Z",
    }
    policy_path = tmp_path / "policy.json"
    checkpoint_path = tmp_path / "checkpoint.json"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
    initialized = initialize_workflow(
        tmp_path / "project",
        policy_path=policy_path,
        checkpoint_ref=checkpoint_path,
    )
    state_path = Path(initialized["state_path"])
    state = load_state(state_path)
    state.update(status="waiting_for_human", pending_action=copy.deepcopy(_state()["pending_action"]))
    state["pending_action"]["gate"] = "external_write"
    _write(state_path, state)
    monkeypatch.setenv("RESEARCH_HUB_AGENT_POLICY", str(policy_path))
    monkeypatch.setenv("AGENT_COLLAB_HUMAN_KEYS_JSON", json.dumps({"owner": secret}))
    result = decide_workflow(
        state_path,
        outcome="accept",
        actor="human:ignored",
        rationale="untrusted caller text",
        action_hash="f" * 64,
    )
    assert result["ok"] is True
    assert result["decision"]["authorization_source"] == "policy_checkpoint"
    assert result["decision"]["decided_by"] == "human:owner"


def test_policy_checkpoint_and_revision_conditions_block_resume(monkeypatch, tmp_path):
    state_path = Path(initialize_workflow(tmp_path)["state_path"])
    monkeypatch.setattr(
        "research_hub.workflow_runtime._evaluate_configured_policy",
        lambda document: {
            "decision": "checkpoint",
            "checkpoint_required": True,
            "spawn_allowed": False,
            "reasons": ["checkpoint_required:test"],
        },
    )
    blocked = resume_workflow(state_path)
    assert blocked["ok"] is False
    assert blocked["state"]["status"] == "blocked"

    revision_path = tmp_path / "revision.yml"
    state = _gated_state(revision_path)
    monkeypatch.setattr("research_hub.workflow_runtime._evaluate_configured_policy", lambda document: None)
    decide_workflow(
        revision_path,
        outcome="revise",
        actor="human:researcher",
        rationale="replace the action",
        action_hash=state["pending_action"]["action_hash"],
    )
    revision = resume_workflow(revision_path)
    assert revision["ok"] is False
    assert revision["reason"] == "revision_required"

    same_hash_state = load_state(revision_path)
    same_hash_state["pending_action"] = copy.deepcopy(state["pending_action"])
    _write(revision_path, same_hash_state)
    same_hash = resume_workflow(revision_path)
    assert same_hash["ok"] is False
    assert same_hash["reason"] == "revision_required"

    replacement_state = load_state(revision_path)
    replacement_state["pending_action"]["action_hash"] = "1" * 64
    replacement_state["pending_action"]["gate"] = None
    _write(revision_path, replacement_state)
    replacement = resume_workflow(revision_path)
    assert replacement["ok"] is True


def test_cli_json_adapter_normalizes_expected_io_errors(monkeypatch, capsys):
    monkeypatch.setattr(
        "research_hub.cli_workflow.workflow_status",
        lambda path: (_ for _ in ()).throw(OSError("disk unavailable")),
    )
    assert main(["workflow", "status", "--json"]) == 1
    assert json.loads(capsys.readouterr().out) == {"ok": False, "error": "disk unavailable"}


def test_evidence_agent_split_filters_failures_and_rejects_unsupported_claim():
    assert ROLE_PROFILES["no_tool_synthesizer"].tools == ()
    results = filter_agent_results([None, {"ok": False}, {"ok": True, "evidence_ref": "research:1"}])
    assert results == [{"ok": True, "evidence_ref": "research:1"}]
    synthesis = synthesize_evidence_packet(
        query="Does the intervention improve retention?",
        researcher_results=results,
        sources=[],
        claims=[{
            "claim_id": "c1",
            "claim_text": "The intervention improves retention.",
            "supporting_source_ids": [],
            "opposing_source_ids": [],
            "verification_status": "supported",
            "uncertainty": "No source was attached.",
            "verification_records": [],
        }],
    )
    assert synthesis["ok"] is False
    assert any("supporting source" in item["message"] for item in synthesis["findings"])


def test_evidence_validator_rejects_identity_conflict_non_support_and_duplicate_ids():
    source = {
        "source_id": "s1",
        "locator": "https://example.test/paper",
        "identifier": "10.1000/example",
        "title": "Example",
        "authors": ["Researcher"],
        "year": 2026,
        "retrieved_at": "2026-08-30T00:00:00Z",
        "identity_status": "conflict",
    }
    claim = {
        "claim_id": "c1",
        "claim_text": "The source supports the claim.",
        "supporting_source_ids": ["s1"],
        "opposing_source_ids": [],
        "verification_status": "supported",
        "uncertainty": "Identity conflict remains.",
        "verification_records": [{
            "source_id": "s1",
            "status": "does_not_support",
            "verifier_output_ref": "verifier:1",
        }],
    }
    packet = {
        "schema_version": "1.0",
        "query": "test",
        "sources": [source, copy.deepcopy(source)],
        "claims": [claim, copy.deepcopy(claim)],
        "contradictions": [],
        "gaps": [],
        "confidence": "low",
        "provenance": {
            "researcher_outputs": ["research:1"],
            "synthesizer": "no-tool",
            "validated_at": "2026-08-30T00:00:00Z",
        },
        "warnings": [],
        "human_decisions": [],
    }
    messages = [finding["message"] for finding in validate_evidence_packet(packet)]
    assert any("duplicate source IDs" in message for message in messages)
    assert any("duplicate claim IDs" in message for message in messages)
    assert any("non-verified source" in message for message in messages)
    assert any("did not confirm claim support" in message for message in messages)
