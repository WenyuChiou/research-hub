"""Workspace CLI: explicit project roots and machine-readable results."""

from __future__ import annotations

import json
from pathlib import Path
import sys

from .core import WorkspaceError
from .service import WorkspaceService, call_workspace
from .tasks import _LOCAL_HUMAN


def add_workspace_parsers(subparsers):
    for resource, operations in {
        "project": ("create", "demo", "list", "show", "register", "record", "search", "discovery-check", "discovery-save", "discovery-replay"),
        "manuscript": ("bind", "state", "audit", "impact"),
        "task": ("audit-batch", "create", "list", "show", "run", "handoff", "import", "decide", "cancel", "recover"),
        "action": ("prepare", "show", "decide", "execute", "reconcile"),
    }.items():
        parent = subparsers.add_parser(resource, help=f"Research workspace {resource} operations")
        children = parent.add_subparsers(dest="workspace_operation", required=True)
        for operation in operations:
            if resource == "task" and operation == "audit-batch":
                from .batch_audit import add_arguments

                parser = children.add_parser(
                    operation, help="Audit explicit existing abstract tasks offline",
                    description="Read-only binding audit of selected tasks; no generation or human acceptance.",
                )
                add_arguments(parser)
                continue
            parser = children.add_parser(operation)
            parser.add_argument("--root", required=True, help="Explicit local research workspace directory")
            parser.add_argument("--json", action="store_true")
            if (resource == "project" and operation not in {"list", "create", "demo"}) or resource == "manuscript" or (resource == "task" and operation in {"create", "list"}):
                parser.add_argument("--project", required=True)
            if resource == "project" and operation == "create":
                parser.add_argument("id")
                parser.add_argument("--title", required=True)
                parser.add_argument("--archetype", choices=["empirical", "review"], default="empirical")
                parser.add_argument("--goal", default="")
            if resource == "project" and operation in {"discovery-check", "discovery-save"}:
                parser.add_argument("--path", required=True, help="Explicit native observations JSON inside root")
            if resource == "project" and operation == "discovery-replay":
                parser.add_argument("--artifact-id", required=True)
            if resource == "project" and operation == "register":
                parser.add_argument("--path", required=True)
                parser.add_argument("--role", required=True)
                parser.add_argument("--source-record-id", help="Explicit existing project source owning this evidence reference")
            if resource == "project" and operation == "record":
                parser.add_argument("--kind", required=True)
                parser.add_argument("--data", required=True, help="Record JSON object")
                mode = parser.add_mutually_exclusive_group()
                mode.add_argument("--dry-run", action="store_true", help="Preview source metadata without opening the declared workspace")
                mode.add_argument("--apply", action="store_true", help="With --batch only: atomically save source metadata in the selected project")
                parser.add_argument("--batch", action="store_true", help="With --dry-run or --apply: an array of source data objects")
                parser.add_argument("--existing-records", help="With --dry-run --batch only: caller-supplied project-bound source snapshot JSON")
            if resource == "project" and operation == "search":
                parser.add_argument("--query", required=True)
                parser.add_argument("--limit", type=int, default=5)
            if resource == "task" and operation == "create":
                parser.add_argument("--operation", required=True)
                parser.add_argument("--mode", choices=["handoff", "connected"], default="handoff")
                parser.add_argument("--instructions", default="")
                parser.add_argument("--source-selection", help="Exact selected abstract range JSON (research profile only)")
            if resource == "task" and operation not in {"create", "list"}:
                parser.add_argument("task_id")
            if resource == "action":
                if operation == "prepare":
                    parser.add_argument("--project", required=True)
                    parser.add_argument("--task-ids", nargs="+", required=True)
                else:
                    parser.add_argument("action_id")
            if resource == "task" and operation == "import":
                parser.add_argument("--file", required=True, help="Host result JSON including input_hash, prose, status and artifacts")
            if resource in {"task", "action"} and operation == "decide":
                parser.add_argument("--outcome", choices=["accept", "decline", "revise", "cancel"], required=True)
                parser.add_argument("--actor", required=True)
                parser.add_argument("--rationale", required=True)
            if resource == "manuscript" and operation == "audit":
                parser.add_argument("--check", choices=["state", "consistency", "prose", "candidate", "docx", "regression"], default="state")
                parser.add_argument("--candidate")


def dispatch_workspace(args) -> int:
    resource, operation = args.command, args.workspace_operation
    if resource == "task" and operation == "audit-batch":
        from .batch_audit import run

        return run(args)
    record_route = resource == "project" and operation == "record"
    source_preview = record_route and getattr(args, "dry_run", False)
    source_apply = record_route and getattr(args, "apply", False)
    batch = getattr(args, "batch", False)
    existing_records = getattr(args, "existing_records", None)
    values = {key: value for key, value in vars(args).items() if key in {
        "artifact_id", "id", "title", "archetype", "goal", "path", "role", "kind", "query", "limit", "operation", "mode", "instructions", "task_id", "task_ids", "action_id", "outcome", "actor", "rationale", "candidate", "source_record_id"}}
    proof = None
    try:
        if batch and not (source_preview or source_apply):
            raise WorkspaceError("Batch requires an explicit dry-run or apply mode")
        if source_apply and (not batch or getattr(args, "kind", None) != "source"):
            raise WorkspaceError("Apply requires project record --kind source --batch")
        if existing_records is not None and not (source_preview and batch):
            raise WorkspaceError("Existing-records is only for batch dry-run; apply reads live selected storage")
        if (source_preview or source_apply) and (not getattr(args, "project", None) or not getattr(args, "data", None)):
            raise WorkspaceError("Source preview requires a declared project and JSON data")
        if getattr(args, "project", None):
            values["project_id"] = args.project
        if getattr(args, "source_selection", None):
            values["source_selection"] = json.loads(args.source_selection)
        if getattr(args, "data", None):
            if source_preview or source_apply:
                from .source_handoff import parse_preview_data, parse_preview_array
                values["data"] = parse_preview_array(args.data) if batch else parse_preview_data(args.data)
            else:
                values["data"] = json.loads(args.data)
        if getattr(args, "file", None):
            raw = Path(args.file).read_text(encoding="utf-8")
            if len(raw) > 2_100_000:
                raise WorkspaceError("Result file is too large")
            imported = json.loads(raw)
            if not isinstance(imported, dict) or set(imported) - {"prose", "status", "artifacts", "input_hash", "draft_response"}:
                raise WorkspaceError("Result must contain only prose, status, artifacts, input_hash and profile draft_response")
            values.update(imported)
        if resource == "manuscript" and operation == "audit":
            values["operation"] = args.check
        if operation == "decide":
            if not sys.stdin.isatty() or not sys.stderr.isatty():
                raise WorkspaceError("Human decisions require an interactive terminal; no --yes or agent proof is accepted", "human_required")
            if resource == "action":
                from .actions import ActionService
                task = ActionService(WorkspaceService(args.root).workspace).get(args.action_id)
            else:
                task = WorkspaceService(args.root).tasks.get(args.task_id)
            action_hash = task["action_hash"]
            print(f"Review {resource} {task['id']}, outcome {args.outcome}, exact candidate {action_hash}", file=sys.stderr)
            print("Type the complete candidate hash to confirm:", file=sys.stderr)
            if input().strip() != action_hash:
                raise WorkspaceError("Decision not confirmed; task remains pending", "human_required")
            values["action_hash"] = action_hash
            proof = _LOCAL_HUMAN
        if source_preview:
            from .source_handoff import parse_preview_snapshot, preview_source_batch, preview_source_handoff
            if batch:
                snapshot = parse_preview_snapshot(existing_records) if existing_records is not None else None
                result = preview_source_batch(values.pop("project_id"), existing_records=snapshot, **values)
            else:
                result = preview_source_handoff(values.pop("project_id"), **values)
        elif source_apply:
            result = call_workspace(args.root, "project", "record-batch", values, proof=proof)
        else:
            result = call_workspace(args.root, resource, operation, values, proof=proof)
    except (ValueError, OSError, EOFError) as exc:
        result = {"ok": False, "error": str(exc), "code": getattr(exc, "code", "invalid_request")}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1
