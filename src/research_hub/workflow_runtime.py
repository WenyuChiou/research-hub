"""Deterministic, resumable state manager for research workflows.

The runtime deliberately does not execute research tools.  It owns the durable
state, validates human decisions, guards external-write idempotency, and hands
an exact next action to CLI or MCP callers.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import shutil
import tempfile
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

from research_hub.locks import file_lock


CURRENT_SCHEMA_VERSION = "1.1"
SUPPORTED_SCHEMA_VERSIONS = {"1.0", CURRENT_SCHEMA_VERSION}
DEFAULT_STATE_PATH = Path(".research") / "workflow_state.yml"
POLICY_ENV = "RESEARCH_HUB_AGENT_POLICY"
CHECKPOINT_ENV = "RESEARCH_HUB_AGENT_CHECKPOINT"
HUMAN_KEYS_ENV = "AGENT_COLLAB_HUMAN_KEYS_JSON"
TERMINAL_STATUSES = {"completed", "cancelled", "declined"}
_LOCAL_TTY_CONFIRMATION = object()


class WorkflowContractError(ValueError):
    """Raised when state or an optional harness contract fails closed."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _schema_path(version: str) -> Path:
    if version != CURRENT_SCHEMA_VERSION:
        raise WorkflowContractError(f"no bundled JSON schema for workflow version: {version}")
    return (
        Path(__file__).with_name("skills_data")
        / "research-workflow-orchestrator"
        / "references"
        / "workflow-state.schema.json"
    )


def _load_schema(version: str) -> dict[str, Any]:
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise WorkflowContractError(f"unsupported workflow schema version: {version}")
    try:
        return json.loads(_schema_path(version).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WorkflowContractError(f"cannot load workflow schema {version}: {exc}") from exc


def validate_state_document(document: dict[str, Any]) -> list[dict[str, str]]:
    """Return stable validation findings for a v1.0 or v1.1 document."""

    if not isinstance(document, dict):
        return [{"path": "$", "message": "workflow state must be an object"}]
    version = str(document.get("schema_version", ""))
    if version == "1.0":
        required = {
            "schema_version",
            "workflow_id",
            "current_stage",
            "status",
            "actions",
            "decisions",
            "artifacts",
            "pending_action",
            "updated_at",
        }
        missing = sorted(required - set(document))
        if missing:
            return [{"path": "$", "message": "missing legacy fields: " + ", ".join(missing)}]
        if document.get("status") in {"completed", "cancelled"} and document.get("pending_action") is not None:
            return [{"path": "$.pending_action", "message": "terminal legacy state must not have a pending action"}]
        return []
    try:
        validator = Draft202012Validator(
            _load_schema(version), format_checker=FormatChecker()
        )
    except WorkflowContractError as exc:
        return [{"path": "$.schema_version", "message": str(exc)}]
    findings: list[dict[str, str]] = []
    for error in sorted(
        validator.iter_errors(document),
        key=lambda item: tuple(str(part) for part in item.path),
    ):
        path = "$" + "".join(
            f"[{part}]" if isinstance(part, int) else f".{part}" for part in error.path
        )
        findings.append({"path": path, "message": error.message})
    return findings


def load_state(path: str | Path) -> dict[str, Any]:
    candidate = Path(path).expanduser().resolve()
    try:
        value = yaml.safe_load(candidate.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise WorkflowContractError(f"cannot read workflow state {candidate}: {exc}") from exc
    if not isinstance(value, dict):
        raise WorkflowContractError(f"workflow state must be an object: {candidate}")
    return value


def _atomic_write_yaml(path: Path, document: dict[str, Any]) -> None:
    """Replace a state file atomically without losing the prior bytes on error."""

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            yaml.safe_dump(document, handle, allow_unicode=True, sort_keys=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def harness_status(policy_path: str | Path | None = None) -> dict[str, Any]:
    """Inspect the optional public harness without turning it into a dependency."""

    configured = str(policy_path or os.environ.get(POLICY_ENV, "")).strip()
    try:
        module = importlib.import_module("agent_collab_harness")
    except ImportError:
        return {
            "status": "misconfigured" if configured else "unavailable",
            "available": False,
            "configured": bool(configured),
            "version": None,
            "policy_path": configured or None,
            "message": (
                "agent-collab-harness is configured but not installed"
                if configured
                else "optional agent-collab-harness is not installed"
            ),
        }

    result: dict[str, Any] = {
        "status": "available",
        "available": True,
        "configured": bool(configured),
        "version": getattr(module, "__version__", "unknown"),
        "policy_path": configured or None,
        "message": "optional harness is available",
    }
    if configured:
        try:
            io_module = importlib.import_module("agent_collab_harness.io")
            policy = io_module.load_json_object(Path(configured).expanduser())
            module.validate_policy(policy)
        except Exception as exc:
            result.update(status="misconfigured", message=f"configured policy is invalid: {exc}")
    return result


def _policy_hash(policy_path: str | Path | None) -> str | None:
    if not policy_path:
        return None
    status = harness_status(policy_path)
    if status["status"] != "available":
        raise WorkflowContractError(status["message"])
    try:
        io_module = importlib.import_module("agent_collab_harness.io")
        policy = io_module.load_json_object(Path(policy_path).expanduser())
    except Exception as exc:
        raise WorkflowContractError(f"cannot read configured policy: {exc}") from exc
    return _canonical_hash(policy)


def _action_hash(action: dict[str, Any]) -> str:
    """Bind identity to the complete action envelope, including its payload."""

    return _canonical_hash(
        {key: value for key, value in action.items() if key not in {"action_hash", "prepared_at"}}
    )


def _lower_hash(value: Any) -> Any:
    if isinstance(value, str):
        return value.lower()
    if isinstance(value, list):
        return [item.lower() if isinstance(item, str) else item for item in value]
    return value


def _normalize_legacy_hash_fields(document: dict[str, Any]) -> None:
    """Normalize only schema-defined hash fields; preserve opaque identifiers."""

    for action in document.get("actions", []):
        action["input_hashes"] = _lower_hash(action.get("input_hashes", []))
    pending = document.get("pending_action")
    if isinstance(pending, dict):
        pending["input_hashes"] = _lower_hash(pending.get("input_hashes", []))
        pending["parameters_hash"] = _lower_hash(pending.get("parameters_hash"))
    for decision in document.get("decisions", []):
        for field in ("parameters_hash", "preview_hash"):
            if field in decision and decision[field] is not None:
                decision[field] = _lower_hash(decision[field])
    for artifact in document.get("artifacts", []):
        artifact["sha256"] = _lower_hash(artifact.get("sha256"))


def _require_valid(document: dict[str, Any]) -> None:
    findings = validate_state_document(document)
    if findings:
        first = findings[0]
        raise WorkflowContractError(f"invalid workflow state at {first['path']}: {first['message']}")


def initialize_workflow(
    project_root: str | Path,
    *,
    workflow_id: str | None = None,
    state_path: str | Path | None = None,
    policy_path: str | Path | None = None,
    checkpoint_ref: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(project_root).expanduser().resolve()
    destination = Path(state_path).expanduser().resolve() if state_path else root / DEFAULT_STATE_PATH
    if destination.exists():
        raise WorkflowContractError(f"workflow state already exists: {destination}")
    configured_policy = policy_path or os.environ.get(POLICY_ENV)
    configured_checkpoint = checkpoint_ref or os.environ.get(CHECKPOINT_ENV)
    now = _now()
    document: dict[str, Any] = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "workflow_id": workflow_id or f"wf-{uuid.uuid4().hex[:16]}",
        "current_stage": "orient",
        "status": "running",
        "updated_at": now,
        "trace_id": uuid.uuid4().hex,
        "correlation_id": uuid.uuid4().hex,
        "policy_checkpoint_ref": str(configured_checkpoint) if configured_checkpoint else None,
        "policy_hash": _policy_hash(configured_policy),
        "evidence_packet_refs": [],
        "actions": [],
        "decisions": [],
        "artifacts": [],
        "attempt_history": [],
        "pending_action": None,
        "pending_external_action": None,
        "external_write_ledger": [],
        "recovery_status": "clean",
        "migration_history": [],
        "blocker": None,
    }
    _require_valid(document)
    _atomic_write_yaml(destination, document)
    return {"ok": True, "state_path": str(destination), "state": document}


def workflow_status(path: str | Path) -> dict[str, Any]:
    document = load_state(path)
    findings = validate_state_document(document)
    return {
        "ok": not findings,
        "state_path": str(Path(path).expanduser().resolve()),
        "schema_version": document.get("schema_version"),
        "migration_required": document.get("schema_version") != CURRENT_SCHEMA_VERSION,
        "workflow_id": document.get("workflow_id"),
        "current_stage": document.get("current_stage"),
        "status": document.get("status"),
        "recovery_status": document.get("recovery_status", "legacy"),
        "pending_action": document.get("pending_action"),
        "pending_external_action": document.get("pending_external_action"),
        "findings": findings,
    }


def validate_workflow(path: str | Path) -> dict[str, Any]:
    document = load_state(path)
    findings = validate_state_document(document)
    return {
        "ok": not findings,
        "state_path": str(Path(path).expanduser().resolve()),
        "schema_version": document.get("schema_version"),
        "findings": findings,
    }


def decide_workflow(
    path: str | Path,
    *,
    outcome: str,
    actor: str,
    rationale: str,
    action_hash: str,
    _local_confirmation: object | None = None,
) -> dict[str, Any]:
    destination = Path(path).expanduser().resolve()
    document = load_state(destination)
    _require_valid(document)
    if document["schema_version"] != CURRENT_SCHEMA_VERSION:
        raise WorkflowContractError("migrate workflow state to 1.1 before recording decisions")
    if document["status"] in TERMINAL_STATUSES:
        raise WorkflowContractError(f"cannot decide a terminal workflow: {document['status']}")
    pending = document.get("pending_action")
    if not isinstance(pending, dict) or not pending.get("gate"):
        raise WorkflowContractError("no gated pending action is waiting for a decision")
    expected_hash = pending["action_hash"]
    if action_hash != expected_hash:
        raise WorkflowContractError("decision action hash does not match the pending action")
    if outcome not in {"accept", "decline", "revise", "cancel"}:
        raise WorkflowContractError(f"unsupported decision outcome: {outcome}")
    if not isinstance(actor, str) or not actor.startswith("human:") or not actor.removeprefix("human:").strip():
        raise WorkflowContractError("decision actor must use a non-empty human: namespace")
    authorization_source = "direct_human_stop"
    if outcome == "accept":
        policy_decision, checkpoint = _evaluate_configured_policy_and_checkpoint(document)
        checkpoint_decision = None
        if policy_decision and policy_decision["decision"] == "continue" and checkpoint:
            for candidate in reversed(checkpoint.get("decisions", [])):
                if (
                    candidate.get("gate") == pending["gate"]
                    and candidate.get("decision") == "approve"
                    and candidate.get("affected_action_hash") == expected_hash
                ):
                    checkpoint_decision = candidate
                    break
        if checkpoint_decision is not None:
            actor = checkpoint_decision["actor"]
            rationale = checkpoint_decision["rationale"]
            authorization_source = "policy_checkpoint"
        elif _local_confirmation is _LOCAL_TTY_CONFIRMATION:
            authorization_source = "local_tty"
        else:
            raise WorkflowContractError(
                "accept requires a verified policy checkpoint or exact local TTY confirmation"
            )
    decision = {
        "action_id": pending["action_id"],
        "action_hash": expected_hash,
        "gate": pending["gate"],
        "outcome": outcome,
        "scope": list(pending["scope"]),
        "parameters_hash": pending["parameters_hash"],
        "resource_bounds": deepcopy(pending.get("resource_bounds", {})),
        "decided_at": _now(),
        "decided_by": actor,
        "rationale": rationale,
        "authorization_source": authorization_source,
    }
    document["decisions"].append(decision)
    if outcome == "accept":
        document.update(status="running", blocker=None, recovery_status="clean")
    elif outcome == "cancel":
        document.update(status="cancelled", pending_action=None, pending_external_action=None)
    elif outcome == "decline":
        document.update(status="declined", pending_action=None, pending_external_action=None)
    else:
        document.update(
            status="blocked",
            blocker="Human revision requested; replace the pending action before resuming.",
            pending_action=None,
            pending_external_action=None,
        )
    document["updated_at"] = _now()
    _require_valid(document)
    _atomic_write_yaml(destination, document)
    return {"ok": outcome == "accept", "decision": decision, "state": document}


def _evaluate_configured_policy_and_checkpoint(
    document: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    checkpoint_ref = document.get("policy_checkpoint_ref")
    policy_path = os.environ.get(POLICY_ENV)
    if not checkpoint_ref and not policy_path and not document.get("policy_hash"):
        return None, None
    if not policy_path:
        raise WorkflowContractError("workflow records a policy but RESEARCH_HUB_AGENT_POLICY is unset")
    status = harness_status(policy_path)
    if status["status"] != "available":
        raise WorkflowContractError(status["message"])
    actual_policy_hash = _policy_hash(policy_path)
    if document.get("policy_hash") and document["policy_hash"] != actual_policy_hash:
        raise WorkflowContractError("configured policy hash differs from workflow state")
    if not checkpoint_ref:
        raise WorkflowContractError("configured policy requires a policy checkpoint reference")
    try:
        module = importlib.import_module("agent_collab_harness")
        io_module = importlib.import_module("agent_collab_harness.io")
        policy = io_module.load_json_object(Path(policy_path).expanduser())
        checkpoint = io_module.load_json_object(Path(checkpoint_ref).expanduser())
        if document.get("policy_hash") and document["policy_hash"] != _canonical_hash(policy):
            raise WorkflowContractError("configured policy changed during evaluation")
        authorization_keys = io_module.load_human_authorization_keys(
            os.environ.get(HUMAN_KEYS_ENV)
        )
        decision = module.evaluate_policy(
            checkpoint,
            policy,
            authorization_keys=authorization_keys,
        )
    except Exception as exc:
        raise WorkflowContractError(f"policy evaluation failed closed: {exc}") from exc
    return decision.to_dict(), checkpoint


def _evaluate_configured_policy(document: dict[str, Any]) -> dict[str, Any] | None:
    decision, _checkpoint = _evaluate_configured_policy_and_checkpoint(document)
    return decision


def resume_workflow(path: str | Path) -> dict[str, Any]:
    destination = Path(path).expanduser().resolve()
    document = load_state(destination)
    _require_valid(document)
    if document["schema_version"] != CURRENT_SCHEMA_VERSION:
        raise WorkflowContractError("migrate workflow state to 1.1 before resuming")
    if document["status"] in TERMINAL_STATUSES:
        return {"ok": False, "resumed": False, "reason": f"terminal:{document['status']}", "state": document}
    if (
        document["status"] == "blocked"
        and isinstance(document.get("blocker"), str)
        and document["blocker"].startswith("Human revision requested")
    ):
        latest_revision = next(
            (decision for decision in reversed(document["decisions"]) if decision["outcome"] == "revise"),
            None,
        )
        replacement = document.get("pending_action")
        replacement_hash = replacement.get("action_hash") if isinstance(replacement, dict) else None
        if latest_revision is None or not replacement_hash or replacement_hash == latest_revision["action_hash"]:
            return {
                "ok": False,
                "resumed": False,
                "reason": "revision_required",
                "state": document,
            }
        if replacement.get("gate") and not any(
            decision["outcome"] == "accept"
            and decision["action_hash"] == replacement_hash
            and decision["gate"] == replacement["gate"]
            and decision["authorization_source"] in {"policy_checkpoint", "local_tty"}
            for decision in document["decisions"]
        ):
            return {
                "ok": False,
                "resumed": False,
                "reason": "replacement_acceptance_required",
                "state": document,
            }
    policy_decision = _evaluate_configured_policy(document)
    if policy_decision and (
        policy_decision["decision"] != "continue"
        or policy_decision.get("checkpoint_required")
        or not policy_decision.get("spawn_allowed", False)
    ):
        document.update(
            status="blocked",
            blocker="Agent policy did not authorize resume: " + "; ".join(policy_decision["reasons"]),
            recovery_status="blocked",
            updated_at=_now(),
        )
        _atomic_write_yaml(destination, document)
        return {"ok": False, "resumed": False, "policy_decision": policy_decision, "state": document}
    if document.get("pending_external_action"):
        document.update(
            status="blocked",
            blocker="External action outcome is unknown; reconcile it before retrying.",
            recovery_status="reconcile_required",
            updated_at=_now(),
        )
        _atomic_write_yaml(destination, document)
        return {"ok": False, "resumed": False, "reason": "reconcile_required", "state": document}
    pending = document.get("pending_action")
    if isinstance(pending, dict) and pending.get("retry_count", 0) >= pending.get("max_retries", 0):
        document.update(
            status="blocked",
            blocker="Retry bound exhausted for the pending action.",
            recovery_status="blocked",
            updated_at=_now(),
        )
        _atomic_write_yaml(destination, document)
        return {"ok": False, "resumed": False, "reason": "retry_exhausted", "state": document}
    document.update(status="running", blocker=None, recovery_status="clean", updated_at=_now())
    _require_valid(document)
    _atomic_write_yaml(destination, document)
    return {"ok": True, "resumed": True, "policy_decision": policy_decision, "state": document}


def migrate_document(document: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    version = str(document.get("schema_version", ""))
    if version == CURRENT_SCHEMA_VERSION:
        return deepcopy(document), []
    if version != "1.0":
        raise WorkflowContractError(f"unsupported workflow schema version: {version}")
    _require_valid(document)
    migrated = deepcopy(document)
    now = _now()
    migrated["schema_version"] = CURRENT_SCHEMA_VERSION
    migrated.setdefault("trace_id", uuid.uuid4().hex)
    migrated.setdefault("correlation_id", uuid.uuid4().hex)
    migrated.setdefault("policy_checkpoint_ref", None)
    migrated.setdefault("policy_hash", None)
    migrated.setdefault("evidence_packet_refs", [])
    migrated.setdefault("attempt_history", [])
    migrated.setdefault("pending_external_action", None)
    migrated.setdefault("external_write_ledger", [])
    migrated.setdefault("recovery_status", "clean")
    migrated.setdefault("migration_history", []).append(
        {"from_version": "1.0", "to_version": CURRENT_SCHEMA_VERSION, "migrated_at": now}
    )
    migrated.setdefault("blocker", None)
    _normalize_legacy_hash_fields(migrated)
    for action in migrated.get("actions", []):
        action.setdefault("action_hash", _action_hash(action))
    pending = migrated.get("pending_action")
    if isinstance(pending, dict):
        pending.setdefault("action_hash", _action_hash(pending))
        pending.setdefault("resource_bounds", {})
    for decision in migrated.get("decisions", []):
        decision.setdefault("action_hash", _canonical_hash(decision))
        decision.setdefault("rationale", decision.pop("summary", "Migrated v1.0 decision"))
        decision.setdefault("authorization_source", "legacy_migration")
    migrated["updated_at"] = now
    _require_valid(migrated)
    return migrated, ["schema_version: 1.0 -> 1.1", "added recovery, policy, trace, and migration fields"]


def migrate_workflow(path: str | Path, *, apply: bool = False) -> dict[str, Any]:
    destination = Path(path).expanduser().resolve()
    original = load_state(destination)
    migrated, changes = migrate_document(original)
    report: dict[str, Any] = {
        "ok": True,
        "applied": False,
        "dry_run": not apply,
        "state_path": str(destination),
        "from_version": original.get("schema_version"),
        "to_version": migrated.get("schema_version"),
        "changes": changes,
        "state": migrated,
    }
    if not apply or not changes:
        return report
    backup = destination.with_name(f"{destination.name}.v{original['schema_version']}.bak")
    if backup.exists():
        backup = destination.with_name(f"{destination.name}.{uuid.uuid4().hex[:8]}.bak")
    shutil.copy2(destination, backup)
    try:
        _atomic_write_yaml(destination, migrated)
    except Exception:
        # The atomic writer preserves the original destination.  Keep the backup
        # as explicit recovery evidence and propagate the failure.
        raise
    report.update(applied=True, dry_run=False, backup_path=str(backup))
    return report


def prepare_external_action(path: str | Path, action: dict[str, Any]) -> dict[str, Any]:
    """Persist an external action before execution and reject duplicate hashes."""

    destination = Path(path).expanduser().resolve()
    with file_lock(destination):
        document = load_state(destination)
        _require_valid(document)
        if document["schema_version"] != CURRENT_SCHEMA_VERSION:
            raise WorkflowContractError("migrate workflow state before external action preparation")
        if document.get("pending_external_action") is not None:
            raise WorkflowContractError("an unresolved external action must be reconciled before preparing another")
        action_hash = action.get("action_hash") or _action_hash(action)
        if action.get("action_hash") and action["action_hash"] != _action_hash(action):
            raise WorkflowContractError("provided external action hash does not bind the complete action payload")
        if any(item["action_hash"] == action_hash for item in document["external_write_ledger"]):
            raise WorkflowContractError(f"external action already recorded: {action_hash}")
        pending = {**deepcopy(action), "action_hash": action_hash, "prepared_at": _now()}
        document.update(
            pending_external_action=pending,
            recovery_status="pending_external_action",
            updated_at=_now(),
        )
        _atomic_write_yaml(destination, document)
    return {"ok": True, "action_hash": action_hash, "state": document}


def record_external_result(path: str | Path, *, action_hash: str, result_ref: str) -> dict[str, Any]:
    destination = Path(path).expanduser().resolve()
    with file_lock(destination):
        document = load_state(destination)
        _require_valid(document)
        pending = document.get("pending_external_action")
        if not isinstance(pending, dict) or pending.get("action_hash") != action_hash:
            raise WorkflowContractError("external result does not match the pending action")
        document["external_write_ledger"].append(
            {"action_hash": action_hash, "result_ref": result_ref, "completed_at": _now()}
        )
        document.update(
            pending_external_action=None,
            recovery_status="clean",
            updated_at=_now(),
        )
        _require_valid(document)
        _atomic_write_yaml(destination, document)
    return {"ok": True, "duplicate_prevented": True, "state": document}
