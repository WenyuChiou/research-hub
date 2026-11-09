"""Offline integrity audit of an explicit list of existing abstract tasks.

No discovery, preparation, generation, import, acceptance, or workspace writes.
Run as ``python -m research_hub.workspace.batch_audit manifest.json``.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import csv
import io
import json
from pathlib import Path
import re
import sqlite3
import sys

from .core import Workspace, WorkspaceError, file_hash, safe_path
from .task_summary import selection

_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_SHA = re.compile(r"[a-f0-9]{64}\Z")
_FIELDS = {"article_id", "workspace_root", "project_id", "source_record_id", "task_id",
           "expected_source_sha256", "expected_selected_sha256"}
_COLUMNS = ("article_id", "status", "diagnostic", "recorded_execution_mode", "provider_execution", "human_review",
            "scientific_acceptance", "declared_source_status", "reason_codes",
            "input_hash", "action_hash", "draft_sha256", "source_bound_statements",
            "candidate_files_checked", "selected_codepoints", "reading_scope")


def _json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique)


def validate_manifest(value):
    """Fail the entire envelope before accessing any workspace on ambiguity."""
    if (not isinstance(value, dict) or set(value) != {"version", "entries"}
            or type(value["version"]) is not int or value["version"] != 1
            or not isinstance(value["entries"], list) or not 1 <= len(value["entries"]) <= 100):
        raise ValueError("Invalid manifest")
    articles, tasks = set(), set()
    for entry in value["entries"]:
        if not isinstance(entry, dict):
            raise ValueError("Invalid entry")
        article = entry.get("article_id")
        if not isinstance(article, str) or not _TOKEN.fullmatch(article) or article in articles:
            raise ValueError("Invalid or duplicate article")
        articles.add(article)
        # Explicit unavailable rows preserve the ledger denominator, without
        # pretending that a task exists or accessing a workspace for that row.
        if set(entry) == {"article_id", "declared_status", "reason_codes"}:
            if (entry["declared_status"] not in {"blocked", "unknown"}
                    or not isinstance(entry["reason_codes"], list)
                    or not 1 <= len(entry["reason_codes"]) <= 10
                    or any(not isinstance(code, str) or not _TOKEN.fullmatch(code)
                           for code in entry["reason_codes"])):
                raise ValueError("Invalid declared source status")
            continue
        if set(entry) != _FIELDS:
            raise ValueError("Invalid binding fields")
        for key in ("project_id", "source_record_id", "task_id"):
            if not isinstance(entry[key], str) or not _TOKEN.fullmatch(entry[key]):
                raise ValueError("Invalid identifier")
        if not re.fullmatch(r"[a-f0-9]{32}", entry["task_id"]):
            raise ValueError("Invalid task identifier")
        for key in ("expected_source_sha256", "expected_selected_sha256"):
            if not isinstance(entry[key], str) or not _SHA.fullmatch(entry[key]):
                raise ValueError("Invalid digest")
        root = entry["workspace_root"]
        if not isinstance(root, str) or not Path(root).is_absolute() or ".." in Path(root).parts:
            raise ValueError("Invalid workspace root")
        identity = (str(Path(root)), entry["task_id"])
        if identity in tasks:
            raise ValueError("Duplicate task")
        tasks.add(identity)
    return value["entries"]


class _ReadOnlyWorkspace(Workspace):
    """Use immutable SQLite handles: even SQLite cannot create SHM/journal files.

    Active WAL/journal workspaces are refused, not checkpointed. Callers must
    audit quiescent workspaces. Inherited read helpers use this override too.
    """
    def __init__(self, root):
        original = Path(root)
        safe_path(Path(original.anchor), original)
        if not original.is_dir():
            raise WorkspaceError("Workspace unavailable", "missing_workspace")
        super().__init__(original)
        safe_path(self.root, self.db_path, exists=True)
        self._assert_quiescent()
        self._before = file_hash(self.db_path)

    def _assert_quiescent(self):
        for suffix in ("-wal", "-shm", "-journal"):
            path = Path(str(self.db_path) + suffix)
            if path.exists() or path.is_symlink():
                raise WorkspaceError("Active database is not supported", "active_database")

    @contextmanager
    def db(self, *, write=False):
        if write:
            raise WorkspaceError("Audit is read only", "write_forbidden")
        self._assert_quiescent()
        safe_path(self.root, self.db_path, exists=True)
        connection = sqlite3.connect(self.db_path.as_uri() + "?mode=ro&immutable=1", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA query_only=ON")
            from ._source_storage import check_schema
            check_schema(connection)
            yield connection
        finally:
            connection.close()

    def unchanged(self):
        self._assert_quiescent()
        safe_path(self.root, self.db_path, exists=True)
        if file_hash(self.db_path) != self._before:
            raise WorkspaceError("Database changed during audit", "changed_database")


def audit_entry(entry):
    row = dict.fromkeys(_COLUMNS, "")
    row.update(article_id=entry["article_id"], status="blocked", human_review="unknown",
               scientific_acceptance="not_assessed", recorded_execution_mode="unknown", provider_execution="not_verified",
               source_bound_statements=None, candidate_files_checked=None, selected_codepoints=None, reading_scope="not_assessed")
    if "declared_status" in entry:
        row.update(status="unprepared", diagnostic="not_audited",
                   declared_source_status=entry["declared_status"], reason_codes=";".join(entry["reason_codes"]))
        return row
    try:
        workspace = _ReadOnlyWorkspace(entry["workspace_root"])
        with workspace.db() as db:
            found = db.execute("SELECT body FROM tasks WHERE project=? AND id=?",
                               (entry["project_id"], entry["task_id"])).fetchone()
            if found is None:
                raise WorkspaceError("Scoped task unavailable", "missing_task")
            task = _json(found[0])
            if not isinstance(task, dict):
                raise ValueError("Invalid task")
            if (task.get("id") != entry["task_id"] or task.get("project_id") != entry["project_id"]
                    or task.get("operation") != "paper-abstract-draft"):
                raise WorkspaceError("Task scope mismatch", "invalid_source")
            mode = task.get("mode")
            if mode not in {"handoff", "connected"}:
                raise WorkspaceError("Unknown execution mode", "invalid_source")
            row["recorded_execution_mode"] = mode
            if task.get("status") in {"ready", "awaiting_agent"} and task.get("result") is None:
                row.update(status="unprepared", diagnostic="candidate_not_prepared")
            elif task.get("status") != "awaiting_human":
                row["diagnostic"] = "not_pending_human"
            else:
                pack = task["request"]["research_draft"]["source_pack"]
                if (pack["source_sha256"] != entry["expected_source_sha256"]
                        or pack["text_sha256"] != entry["expected_selected_sha256"]):
                    raise WorkspaceError("Expected source differs", "expected_hash_mismatch")
                _, provenance, _ = selection(workspace, db, entry["project_id"],
                                              entry["source_record_id"], entry["task_id"])
                row.update(status="binding_pass", diagnostic="verified_pending_candidate", human_review="candidate_pending",
                           source_bound_statements=task["result"]["source_binding"]["statements"],
                           candidate_files_checked=len(task["result"]["artifacts"]),
                           selected_codepoints=len(pack["text"]), reading_scope="selected_abstract",
                           **{key: provenance[key] for key in ("input_hash", "action_hash", "draft_sha256")})
        workspace.unchanged()
    except (WorkspaceError, OSError, sqlite3.Error, ValueError, KeyError, TypeError, AttributeError, RecursionError):
        # Neither exception text nor ledger-controlled paths/prose are returned.
        exc = sys.exc_info()[1]
        code = exc.code if isinstance(exc, WorkspaceError) else "invalid_or_unavailable"
        allowed = {"missing_workspace", "missing_file", "missing_task", "active_database", "changed_database",
                   "unsafe_path", "stale_input", "invalid_source", "context_limit", "invalid_output",
                   "expected_hash_mismatch", "unsupported_storage"}
        row.update(status="missing" if code in {"missing_workspace", "missing_file", "missing_task"} else "blocked",
                   diagnostic=code if code in allowed else "invalid_or_unavailable", human_review="unknown",
                   input_hash="", action_hash="", draft_sha256="", source_bound_statements=None,
                   candidate_files_checked=None, selected_codepoints=None, reading_scope="not_assessed")
    return row


def audit(value):
    entries = validate_manifest(value)
    rows = [audit_entry(entry) for entry in entries]
    counts = {state: sum(row["status"] == state for row in rows)
              for state in ("binding_pass", "unprepared", "missing", "blocked")}
    return {"version": 1, "scope": "explicit_existing_tasks", "scientific_acceptance": "not_assessed",
            "counts": counts,
            "verified_totals": {key: sum(row[key] for row in rows if row["status"] == "binding_pass")
                                for key in ("source_bound_statements", "candidate_files_checked", "selected_codepoints")},
            "entries": rows}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--format", choices=("json", "csv"), default="json")
    parser.add_argument("--output", type=Path, help="New report file outside every selected workspace (never overwrite)")
    args = parser.parse_args(argv)
    try:
        with args.manifest.open("rb") as stream:
            raw = stream.read(256_001)
        if len(raw) > 256_000:
            raise ValueError("Manifest too large")
        manifest = _json(raw)
        entries = validate_manifest(manifest)
        if args.output:
            output = args.output.absolute()
            safe_path(Path(output.anchor), output)
            for entry in entries:
                if "workspace_root" in entry and output.resolve().is_relative_to(Path(entry["workspace_root"]).resolve()):
                    raise ValueError("Report must be outside audited workspaces")
        report = audit(manifest)
        if args.format == "json":
            rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        else:
            stream = io.StringIO(newline="")
            writer = csv.DictWriter(stream, fieldnames=_COLUMNS)
            writer.writeheader()
            writer.writerows(report["entries"])
            rendered = stream.getvalue()
        if args.output:
            with args.output.open("x", encoding="utf-8", newline="") as stream:
                stream.write(rendered)
        else:
            sys.stdout.write(rendered)
        return 0 if report["counts"]["binding_pass"] == len(entries) else 1
    except (OSError, ValueError, TypeError, RecursionError):
        print("Batch audit failed: invalid manifest or report destination; no workspace changes made.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
