"""Project and artifact authority without relocating researchers' files.

SQLite owns project metadata and the execution ledger. Existing workflow YAML
and the writing skill's manuscript state remain separate authorities, referenced
here rather than copied into competing state machines.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile
import uuid


class WorkspaceError(ValueError):
    def __init__(self, message: str, code: str = "invalid_request"):
        super().__init__(message)
        self.code = code


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def encoded(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value) -> str:
    return hashlib.sha256(encoded(value).encode("utf-8")).hexdigest()


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else _stream_hash(stream)


def _stream_hash(stream) -> str:
    value = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        value.update(block)
    return value.hexdigest()


def safe_path(root: Path, value: str | Path, *, exists: bool = False) -> Path:
    """Reject escape paths, symlinks and Windows junctions before file access."""
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        relative = candidate.absolute().relative_to(root)
    except ValueError as exc:
        raise WorkspaceError("Path is outside the selected workspace", "unsafe_path") from exc
    if ".." in relative.parts:
        raise WorkspaceError("Parent traversal is not allowed", "unsafe_path")
    if any(":" in part or part.endswith((".", " ")) for part in relative.parts):
        raise WorkspaceError("Ambiguous path component is not allowed", "unsafe_path")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise WorkspaceError("Linked paths are not allowed", "unsafe_path")
        if current.exists() and getattr(current.lstat(), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
            raise WorkspaceError("Reparse paths are not allowed", "unsafe_path")
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise WorkspaceError("Resolved path escapes the workspace", "unsafe_path")
    if exists and not resolved.is_file():
        raise WorkspaceError("The selected file does not exist", "missing_file")
    return resolved


def atomic_json(path: Path, value, *, replace: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".hub-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(encoded(value) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


ROLES = {"main_manuscript", "evidence", "figure", "table", "supplement", "analysis", "reviewer_response"}
RECORD_FIELDS = {
    "question": ("text",), "source": ("title", "locator"), "claim": ("text",),
    "screening": ("source_id", "decision", "rationale"),
    "analysis": ("question", "method", "result", "limitation"),
    "outline": ("section", "function", "claim", "evidence", "bridge"),
    "review": ("comment", "severity"),
}


class Workspace:
    def __init__(self, root: str | Path):
        original = Path(root).expanduser().absolute()
        if original.is_symlink() or (original.exists() and getattr(original.lstat(), "st_file_attributes", 0) & 0x400):
            raise WorkspaceError("Workspace root must not be a linked directory", "unsafe_path")
        self.root = original.resolve()
        self.control = safe_path(self.root, ".research")
        self.db_path = safe_path(self.root, ".research/workspace.sqlite3")

    @contextmanager
    def db(self, *, write: bool = False):
        if not write and not self.db_path.exists():
            raise WorkspaceError("No workspace yet; create a project first", "not_initialized")
        safe_path(self.root, self.db_path)
        if write:
            self.control.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db_path if write else self.db_path.as_uri() + "?mode=ro", timeout=5, uri=not write)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            if write:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, body TEXT NOT NULL)")
                connection.execute("CREATE TABLE IF NOT EXISTS artifacts (id TEXT PRIMARY KEY, project TEXT NOT NULL REFERENCES projects(id), body TEXT NOT NULL)")
                connection.execute("CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, project TEXT NOT NULL REFERENCES projects(id), kind TEXT NOT NULL, body TEXT NOT NULL)")
                connection.execute("CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, project TEXT NOT NULL REFERENCES projects(id), body TEXT NOT NULL)")
                connection.execute("CREATE TABLE IF NOT EXISTS decisions (id INTEGER PRIMARY KEY, task TEXT NOT NULL REFERENCES tasks(id), body TEXT NOT NULL)")
                connection.execute("CREATE TABLE IF NOT EXISTS actions (id TEXT PRIMARY KEY, project TEXT NOT NULL REFERENCES projects(id), body TEXT NOT NULL)")
            yield connection
            if write:
                connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def list_projects(self) -> list[dict]:
        if not self.db_path.exists():
            return []
        with self.db() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT body FROM projects ORDER BY id")]

    def create_project(self, *, id: str, title: str, archetype: str = "empirical", goal: str = "") -> dict:
        if not isinstance(id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", id):
            raise WorkspaceError("Project ID must be 1–63 lowercase letters, digits or hyphens")
        if not isinstance(title, str) or not title.strip() or archetype not in {"empirical", "review"}:
            raise WorkspaceError("A title and empirical/review archetype are required")
        if not isinstance(goal, str):
            raise WorkspaceError("Goal must be text")
        project = {"id": id, "title": title.strip(), "archetype": archetype, "goal": goal, "created_at": now()}
        with self.db(write=True) as db:
            if db.execute("SELECT 1 FROM projects WHERE id=?", (id,)).fetchone():
                raise WorkspaceError("Project already exists; existing data was preserved", "conflict")
            from research_hub.workflow_runtime import initialize_workflow, load_state
            workflow_path = safe_path(self.root, f".research/projects/{id}/workflow_state.yml")
            if workflow_path.exists():
                if load_state(workflow_path).get("workflow_id") != f"workspace-{id}":
                    raise WorkspaceError("Existing workflow belongs to another project", "conflict")
            else:
                initialize_workflow(self.root, workflow_id=f"workspace-{id}", state_path=workflow_path)
            db.execute("INSERT INTO projects VALUES (?,?)", (id, encoded(project)))
        return project

    def project(self, project_id: str) -> dict:
        with self.db() as db:
            row = db.execute("SELECT body FROM projects WHERE id=?", (project_id,)).fetchone()
        if row is None:
            raise WorkspaceError("Unknown project", "not_found")
        return json.loads(row[0])

    def project_dir(self, project_id: str) -> Path:
        self.project(project_id)
        return safe_path(self.root, f".research/projects/{project_id}")

    def artifacts(self, project_id: str, *, history: bool = False) -> list[dict]:
        self.project(project_id)
        with self.db() as db:
            items = [json.loads(r[0]) for r in db.execute("SELECT body FROM artifacts WHERE project=? ORDER BY rowid", (project_id,))]
        if not history:
            items = [item for item in items if not item.get("superseded_by")]
        for item in items:
            try:
                path = safe_path(self.root, item["path"], exists=True)
                item["current"] = file_hash(path) == item["sha256"]
            except (WorkspaceError, OSError):
                item["current"] = False
        return items

    def register_artifact(self, project_id: str, *, path: str, role: str) -> dict:
        self.project(project_id)
        if role not in ROLES:
            raise WorkspaceError("Unsupported artifact role")
        target = safe_path(self.root, path, exists=True)
        if target.suffix.lower() not in {".md", ".tex", ".docx", ".pdf", ".csv", ".json", ".txt", ".png", ".svg", ".jpg", ".xlsx", ".bib", ".py", ".r"}:
            raise WorkspaceError("Unsupported research artifact format")
        if role in {"main_manuscript", "reviewer_response"} and target.suffix.lower() not in {".md", ".tex", ".docx"}:
            raise WorkspaceError("Editable manuscripts must be Word, LaTeX or Markdown")
        relative = target.relative_to(self.root).as_posix()
        if relative.startswith(".research/"):
            raise WorkspaceError("Internal state cannot be registered as research evidence")
        item = {"id": uuid.uuid4().hex, "path": relative, "role": role, "sha256": file_hash(target), "registered_at": now()}
        with self.db(write=True) as db:
            for row in db.execute("SELECT id,body FROM artifacts WHERE project=?", (project_id,)):
                previous = json.loads(row[1])
                if not previous.get("superseded_by") and (previous["path"] == relative or (role == "main_manuscript" and previous["role"] == role)):
                    if previous["path"] == relative and previous["sha256"] == item["sha256"] and previous["role"] == role:
                        return {**previous, "current": True}
                    previous["superseded_by"] = item["id"]
                    db.execute("UPDATE artifacts SET body=? WHERE id=?", (encoded(previous), row[0]))
            db.execute("INSERT INTO artifacts VALUES (?,?,?)", (item["id"], project_id, encoded(item)))
        return {**item, "current": True}

    def records(self, project_id: str) -> list[dict]:
        self.project(project_id)
        with self.db() as db:
            return [{"id": r[0], "kind": r[1], "data": json.loads(r[2])} for r in db.execute("SELECT id,kind,body FROM records WHERE project=? ORDER BY rowid", (project_id,))]

    def add_record(self, project_id: str, *, kind: str, data: dict) -> dict:
        self.project(project_id)
        if kind not in RECORD_FIELDS or not isinstance(data, dict):
            raise WorkspaceError("Unsupported record kind or payload")
        data = json.loads(encoded(data))
        for field in RECORD_FIELDS[kind]:
            if not isinstance(data.get(field), str) or not data[field].strip():
                raise WorkspaceError(f"{kind} requires nonempty {field}")
        if kind == "source":
            # Identity claims from callers are not verifier evidence.
            data["identity_status"] = "unverified"
        if kind == "claim":
            links = data.get("source_ids", [])
            sources = {r["id"] for r in self.records(project_id) if r["kind"] == "source"}
            if not isinstance(links, list) or any(not isinstance(v, str) or v not in sources for v in links):
                raise WorkspaceError("Claim references an unknown source")
            data.update(source_ids=links, verification_status="unverified", human_acceptance="pending")
        if kind == "screening":
            if data["decision"] not in {"include", "exclude"}:
                raise WorkspaceError("Screening decision must be include or exclude")
            if not any(r["id"] == data["source_id"] and r["kind"] == "source" for r in self.records(project_id)):
                raise WorkspaceError("Screening references an unknown source")
        if kind == "review":
            if data["severity"] not in {"S0", "S1", "S2", "S3", "S4"}:
                raise WorkspaceError("Review severity must be S0–S4")
            data["status"] = "OPEN"
        record_id = uuid.uuid4().hex
        data["recorded_at"] = now()
        with self.db(write=True) as db:
            db.execute("INSERT INTO records VALUES (?,?,?,?)", (record_id, project_id, kind, encoded(data)))
        return {"id": record_id, "kind": kind, "data": data}

    def snapshot(self, project_id: str) -> dict:
        from .tasks import TaskService
        project = self.project(project_id)
        artifacts = self.artifacts(project_id)
        state_path = safe_path(self.root, self.project_dir(project_id) / "manuscript_state.json")
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else None
        workflow_path = safe_path(self.root, self.project_dir(project_id) / "workflow_state.yml")
        workflow = None
        if workflow_path.exists():
            from research_hub.workflow_runtime import load_state
            workflow = load_state(workflow_path)
        warnings = [f"Source changed or unavailable: {a['path']}" for a in artifacts if not a["current"]]
        if state is None:
            warnings.append("Bind the public writing adapter to initialize manuscript authority; no manuscript checks have passed yet.")
        else:
            from .writing import check_alignment
            try:
                check_alignment(self, project_id, state)
            except (WorkspaceError, TypeError, KeyError, AttributeError) as exc:
                warnings.append(f"Manuscript authority needs review: {exc}")
        with self.db() as db:
            actions = [json.loads(r[0]) for r in db.execute("SELECT body FROM actions WHERE project=? ORDER BY rowid DESC", (project_id,))]
        return {"ok": True, "project": project, "artifacts": artifacts, "records": self.records(project_id), "actions": actions,
                "tasks": TaskService(self).list(project_id), "manuscript": state, "workflow": workflow, "warnings": warnings}
