"""Read-only, versioned provenance for a pending source-bound abstract task.

This is not a registered observation or a human acceptance capability. Callers
select IDs only; candidate paths come exclusively from the scoped task ledger.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import PurePosixPath

from .core import WorkspaceError, digest, safe_path

_SHA = re.compile(r"[a-f0-9]{64}\Z")
_ID = re.compile(r"[a-f0-9]{32}\Z")
_NAMES = {"draft.md", "draft-response.json", "raw-draft-response.json", "selected-source.txt", "binding-check.json"}
_PROVENANCE = {"kind", "version", "project_id", "source_record_id", "task_id", "input_hash", "action_hash", "draft_sha256"}


def valid_provenance(value):
    return (isinstance(value, dict) and set(value) == _PROVENANCE
            and value.get("kind") == "abstract-task" and type(value.get("version")) is int and value["version"] == 1
            and all(isinstance(value.get(k), str) and bool(value[k]) for k in ("project_id", "source_record_id"))
            and isinstance(value.get("task_id"), str) and bool(_ID.fullmatch(value["task_id"]))
            and all(isinstance(value.get(k), str) and _SHA.fullmatch(value[k])
                    for k in ("input_hash", "action_hash", "draft_sha256")))


def _candidate_paths(files, task_id):
    if not isinstance(files, list) or len(files) != len(_NAMES):
        raise WorkspaceError("Task candidate files are ambiguous", "invalid_source")
    paths = {}
    parents = set()
    for item in files:
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise WorkspaceError("Task candidate registration is invalid", "invalid_source")
        value, checksum = item["path"], item["sha256"]
        if not isinstance(value, str) or not isinstance(checksum, str) or not _SHA.fullmatch(checksum):
            raise WorkspaceError("Task candidate registration is invalid", "invalid_source")
        path = PurePosixPath(value)
        if (str(path) != value or len(path.parts) != 3 or path.parts[0] != "proposals"
                or not re.fullmatch(re.escape(task_id) + r"-[a-f0-9]{32}", path.parts[1])
                or path.name not in _NAMES or path.name in paths):
            raise WorkspaceError("Task candidate path is outside its owned output", "invalid_source")
        parents.add(path.parent)
        paths[path.name] = item
    if set(paths) != _NAMES or len(parents) != 1:
        raise WorkspaceError("Task candidate files are ambiguous", "invalid_source")
    return paths


def selection(workspace, db, project_id, source_record_id, task_id):
    """Scope first, then verify the original import contract without mutating it."""
    if (not all(isinstance(v, str) and v for v in (project_id, source_record_id, task_id))
            or not _ID.fullmatch(task_id)):
        raise WorkspaceError("Select a project source and its abstract task", "invalid_source")
    source_row = db.execute("SELECT body FROM records WHERE project=? AND id=? AND kind='source'",
                            (project_id, source_record_id)).fetchone()
    task_row = db.execute("SELECT body FROM tasks WHERE project=? AND id=?", (project_id, task_id)).fetchone()
    if source_row is None or task_row is None:
        raise WorkspaceError("Selected source or task is unavailable", "invalid_source")
    try:
        record = {"id": source_record_id, "kind": "source", "data": json.loads(source_row[0])}
        if not isinstance(record["data"], dict):
            raise WorkspaceError("Selected source data is invalid", "invalid_source")
        task = json.loads(task_row[0])
        request, result = task["request"], task["result"]
        bound = request["research_draft"]
        selected = bound["source_selection"]
        if (task["id"] != task_id or task["project_id"] != project_id
                or task["operation"] != "paper-abstract-draft" or task["status"] != "awaiting_human"
                or request["task_id"] != task_id or request["project"] != {"id": project_id}
                or request["operation"] != "paper-abstract-draft"
                or selected["source_record_id"] != source_record_id
                or bound["source_pack"]["source_record_id"] != source_record_id
                or result["status"] != "completed" or result["semantic_acceptance"] != "pending"):
            raise WorkspaceError("Task draft is not pending for this source", "invalid_source")
        if (result["input_hash"] != digest(request)
                or task["action_hash"] != digest({"request": request, "result": result})):
            raise WorkspaceError("Task candidate revision changed", "stale_input")
        # Require explicit ownership even for historical file-backed tasks whose
        # general preview reader permits absent legacy ownership.
        artifact_row = db.execute("SELECT body FROM artifacts WHERE project=? AND id=?",
                                  (project_id, selected["artifact_id"])).fetchone()
        artifact = json.loads(artifact_row[0]) if artifact_row else {}
        if (artifact.get("project_id") != project_id or artifact.get("id") != selected["artifact_id"]
                or artifact.get("source_record_id") != source_record_id):
            raise WorkspaceError("Task input is not bound to this source", "invalid_source")
        if (request.get("artifacts") != [{**artifact, "current": True}]
                or request.get("records") != [] or request.get("adapter_sha256") is not None
                or any(k in request for k in ("manuscript_state_path", "manuscript_state_sha256", "manuscript_state"))):
            raise WorkspaceError("Task input scope is invalid", "invalid_source")
        revision = request.get("revision_context")
        if revision is not None:
            attempts = task.get("attempts")
            prior = attempts[-1] if isinstance(attempts, list) and attempts else {}
            previous = prior.get("result", {})
            decision = prior.get("decision", {})
            if (not isinstance(revision, dict) or set(revision) != {"prose", "artifacts", "reviewed_action_hash"}
                    or decision.get("decision") != "revise"
                    or revision != {"prose": previous.get("prose"), "artifacts": previous.get("artifacts"),
                                    "reviewed_action_hash": decision.get("affected_action_hash")}):
                raise WorkspaceError("Task revision provenance is unavailable", "invalid_source")
            _candidate_paths(revision["artifacts"], task_id)
        paths = _candidate_paths(result["artifacts"], task_id)
        # Scope and canonical paths are established before any source/output read.
        from .tasks import TaskService
        TaskService(workspace).check_inputs(task)
        from .research_draft import parse_response, parse_resolved_response, resolve_response, render_response, task_profile_version
        documents = {}
        for name, item in paths.items():
            path = safe_path(workspace.root, item["path"], exists=True)
            with path.open("rb") as stream:
                raw = stream.read(200_001)
            if len(raw) > 200_000:
                raise WorkspaceError("Task candidate exceeds review limit", "context_limit")
            if hashlib.sha256(raw).hexdigest() != item["sha256"]:
                raise WorkspaceError("Task candidate bytes changed", "stale_input")
            documents[name] = raw.decode("utf-8")
        raw_response = parse_response(documents["raw-draft-response.json"])
        response, report = resolve_response(raw_response, bound["source_pack"], profile_version=task_profile_version(task))
        check = parse_response(documents["binding-check.json"])
        if (parse_resolved_response(documents["draft-response.json"]) != response
                or result["source_binding"] != report
                or set(check) != set(report) | {"checked_at", "profile", "source_receipt"}
                or not isinstance(check["checked_at"], str)
                or {k: check[k] for k in report} != report
                or check["profile"] != bound["profile"]
                or check["source_receipt"] != {k: v for k, v in bound["source_pack"].items() if k != "text"}
                or documents["selected-source.txt"] != bound["source_pack"]["text"]
                or documents["draft.md"] != result["prose"]
                or documents["draft.md"] != render_response(response)):
            raise WorkspaceError("Task candidate does not match its bound response", "invalid_source")
        provenance = {"kind": "abstract-task", "version": 1, "project_id": project_id,
                      "source_record_id": source_record_id, "task_id": task_id,
                      "input_hash": result["input_hash"], "action_hash": task["action_hash"],
                      "draft_sha256": paths["draft.md"]["sha256"]}
        return record, provenance, result["prose"]
    except (AttributeError, KeyError, TypeError, ValueError, OSError) as exc:
        if isinstance(exc, WorkspaceError):
            raise
        # Never leak file paths, source prose, or malformed ledger contents.
        raise WorkspaceError("Task draft provenance is unavailable", "invalid_source") from exc
