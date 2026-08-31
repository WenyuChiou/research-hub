"""CLI adapter for the deterministic workflow domain service."""

from __future__ import annotations

import json
import sys

from research_hub.workflow_runtime import (
    _LOCAL_TTY_CONFIRMATION,
    WorkflowContractError,
    decide_workflow,
    initialize_workflow,
    migrate_workflow,
    resume_workflow,
    validate_workflow,
    workflow_status,
)


def _emit(result: dict, *, emit_json: bool) -> None:
    if emit_json:
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        return
    for key in ("ok", "state_path", "schema_version", "workflow_id", "current_stage", "status", "recovery_status", "migration_required", "applied", "backup_path", "reason"):
        if key in result:
            print(f"{key}: {result[key]}")
    for finding in result.get("findings", []):
        print(f"- {finding['path']}: {finding['message']}")


def dispatch_workflow(args) -> int:
    """Dispatch one workflow subcommand and preserve non-success semantics."""

    try:
        command = args.workflow_command
        if command == "init":
            result = initialize_workflow(
                args.project_root,
                workflow_id=args.workflow_id,
                state_path=args.state,
                policy_path=args.policy,
                checkpoint_ref=args.checkpoint,
            )
        elif command == "status":
            result = workflow_status(args.state)
        elif command == "validate":
            result = validate_workflow(args.state)
        elif command == "decide":
            local_confirmation = None
            if args.outcome == "accept" and args.interactive:
                if not sys.stdin.isatty():
                    raise WorkflowContractError("--interactive accept requires a local TTY")
                expected = f"accept {args.action_hash}"
                print(
                    f"Type '{expected}' to authorize this exact action:",
                    file=sys.stderr,
                )
                if sys.stdin.readline().strip() != expected:
                    raise WorkflowContractError("local TTY confirmation did not match the action hash")
                local_confirmation = _LOCAL_TTY_CONFIRMATION
            result = decide_workflow(
                args.state,
                outcome=args.outcome,
                actor=args.actor,
                rationale=args.rationale,
                action_hash=args.action_hash,
                _local_confirmation=local_confirmation,
            )
        elif command == "resume":
            result = resume_workflow(args.state)
        elif command == "migrate":
            result = migrate_workflow(args.state, apply=args.apply)
        else:  # pragma: no cover - argparse prevents this
            raise WorkflowContractError(f"unknown workflow command: {command}")
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
    _emit(result, emit_json=args.json)
    return 0 if result.get("ok") else 1
