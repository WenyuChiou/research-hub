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
        "project": ("create", "demo", "list", "show", "register", "record", "search"),
        "manuscript": ("bind", "state", "audit", "impact"),
        "task": ("create", "list", "show", "run", "handoff", "import", "decide", "cancel", "recover"),
        "action": ("prepare", "show", "decide", "execute", "reconcile"),
    }.items():
        parent = subparsers.add_parser(resource, help=f"Research workspace {resource} operations")
        children = parent.add_subparsers(dest="workspace_operation", required=True)
        for operation in operations:
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
            if resource == "project" and operation == "register":
                parser.add_argument("--path", required=True)
                parser.add_argument("--role", required=True)
            if resource == "project" and operation == "record":
                parser.add_argument("--kind", required=True)
                parser.add_argument("--data", required=True, help="Record JSON object")
            if resource == "project" and operation == "search":
                parser.add_argument("--query", required=True)
                parser.add_argument("--limit", type=int, default=5)
            if resource == "task" and operation == "create":
                parser.add_argument("--operation", required=True)
                parser.add_argument("--mode", choices=["handoff", "connected"], default="handoff")
                parser.add_argument("--instructions", default="")
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
    values = {key: value for key, value in vars(args).items() if key in {
        "id", "title", "archetype", "goal", "path", "role", "kind", "query", "limit", "operation", "mode", "instructions", "task_id", "task_ids", "action_id", "outcome", "actor", "rationale", "candidate"}}
    proof = None
    try:
        if getattr(args, "project", None):
            values["project_id"] = args.project
        if getattr(args, "data", None):
            values["data"] = json.loads(args.data)
        if getattr(args, "file", None):
            raw = Path(args.file).read_text(encoding="utf-8")
            if len(raw) > 2_100_000:
                raise WorkspaceError("Result file is too large")
            imported = json.loads(raw)
            if not isinstance(imported, dict) or set(imported) - {"prose", "status", "artifacts", "input_hash"}:
                raise WorkspaceError("Result must contain only prose, status, artifacts and input_hash")
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
        result = call_workspace(args.root, resource, operation, values, proof=proof)
    except (ValueError, OSError, EOFError) as exc:
        result = {"ok": False, "error": str(exc), "code": getattr(exc, "code", "invalid_request")}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1
