"""Hash-bound local delivery actions with durable receipts and reconciliation.

This first workspace action is a new delivery ZIP, not a publication, a cloud
upload, or an edit to canonical Word/LaTeX files. Other integrations must enter
this lifecycle before claiming its protection.
"""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import uuid
import zipfile

from .core import WorkspaceError, digest, encoded, file_hash, now, safe_path
from .tasks import TaskService, _LOCAL_HUMAN


class ActionService:
    def __init__(self, workspace):
        self.workspace = workspace

    def get(self, action_id: str, db=None) -> dict:
        if db is None:
            with self.workspace.db() as connection:
                return self.get(action_id, connection)
        row = db.execute("SELECT body FROM actions WHERE id=?", (action_id,)).fetchone()
        if row is None:
            raise WorkspaceError("Unknown action", "not_found")
        return json.loads(row[0])

    def _save(self, db, action):
        action["updated_at"] = now()
        db.execute("UPDATE actions SET body=? WHERE id=?", (encoded(action), action["id"]))

    def prepare_delivery(self, project_id: str, *, task_ids: list[str]) -> dict:
        if not isinstance(task_ids, list) or not task_ids or len(set(task_ids)) != len(task_ids):
            raise WorkspaceError("Delivery requires distinct accepted task IDs")
        project = self.workspace.project(project_id)
        tasks = TaskService(self.workspace)
        selected = [tasks.get(task_id) for task_id in task_ids]
        for task in selected:
            if task["project_id"] != project_id or task["status"] != "completed" or task["result"]["semantic_acceptance"] != "accept":
                raise WorkspaceError("Only human-accepted tasks from this project can be delivered", "acceptance_required")
            tasks.check_inputs(task)
        files = {}
        for task in selected:
            for item in task["result"]["artifacts"]:
                path, checksum = item["path"], item["sha256"]
                if path in files and files[path] != checksum:
                    raise WorkspaceError("Accepted tasks refer to conflicting candidate revisions", "stale_candidate")
                if file_hash(safe_path(self.workspace.root, path, exists=True)) != checksum:
                    raise WorkspaceError("Accepted candidate changed", "stale_candidate")
                files[path] = checksum
        if not files:
            raise WorkspaceError("Register exact candidate files in the accepted task result before delivery", "candidate_required")
        # Delivery is an accepted proposal handoff, not a claim that the public
        # skill's manuscript release checks have all passed.
        packet = {"schema_version": 1, "kind": "accepted-proposal-delivery", "project": project,
                  "tasks": selected, "files": files,
                  "release_authorization": "not_publication_authorization"}
        for path, sha256 in files.items():
            if file_hash(safe_path(self.workspace.root, path, exists=True)) != sha256:
                raise WorkspaceError("Accepted candidate changed", "stale_candidate")
        action_hash = digest(packet)
        with self.workspace.db(write=True) as db:
            for row in db.execute("SELECT body FROM actions WHERE project=?", (project_id,)):
                existing = json.loads(row[0])
                if existing["action_hash"] == action_hash:
                    return existing
            action = {"id": uuid.uuid4().hex, "project_id": project_id, "kind": "delivery_bundle", "status": "awaiting_human",
                      "action_hash": action_hash, "packet": packet, "decisions": [], "receipt": None, "updated_at": now()}
            db.execute("INSERT INTO actions VALUES (?,?,?)", (action["id"], project_id, encoded(action)))
        return action

    def decide(self, action_id, *, outcome, actor, rationale, action_hash, proof=None):
        if proof is not _LOCAL_HUMAN:
            raise WorkspaceError("Delivery requires a local human decision", "human_required")
        if outcome not in {"accept", "decline", "cancel"} or not isinstance(actor, str) or not actor.strip() or not isinstance(rationale, str) or not rationale.strip():
            raise WorkspaceError("Invalid action decision")
        with self.workspace.db(write=True) as db:
            action = self.get(action_id, db)
            if action["status"] != "awaiting_human" or action["action_hash"] != action_hash:
                raise WorkspaceError("Action decision is stale", "stale_decision")
            action["decisions"].append({"gate": "local_delivery", "actor": actor, "decision": outcome, "timestamp": now(), "rationale": rationale, "affected_action_hash": action_hash})
            action["status"] = {"accept": "approved", "decline": "declined", "cancel": "cancelled"}[outcome]
            self._save(db, action)
        return action

    def _payload(self, action):
        for task in action["packet"]["tasks"]:
            current = TaskService(self.workspace).get(task["id"])
            if current["action_hash"] != task["action_hash"] or current["status"] != "completed":
                raise WorkspaceError("Accepted task revision is stale", "stale_decision")
            TaskService(self.workspace).check_inputs(current)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
            materials = {"delivery.json": (encoded(action["packet"]) + "\n").encode("utf-8")}
            total = 0
            for path, sha256 in action["packet"]["files"].items():
                source = safe_path(self.workspace.root, path, exists=True)
                with source.open("rb") as source_stream:
                    raw = source_stream.read(100_000_000 - total + 1)
                total += len(raw)
                if total > 100_000_000:
                    raise WorkspaceError("Delivery exceeds 100 MB; use a narrower bundle")
                if hashlib.sha256(raw).hexdigest() != sha256:
                    raise WorkspaceError("Accepted candidate changed", "stale_candidate")
                materials["candidates/" + path] = raw
            for name, raw in sorted(materials.items()):
                archive.writestr(zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0)), raw)
        return stream.getvalue()

    def execute(self, action_id):
        action = self.get(action_id)
        if action["status"] == "completed":
            return self.reconcile(action_id)
        if action["status"] != "approved":
            raise WorkspaceError("Action is not approved or needs reconciliation; no replay", "invalid_transition")
        payload = self._payload(action)
        target = safe_path(self.workspace.root, f".research/deliveries/{action_id}.zip")
        expected = hashlib.sha256(payload).hexdigest()
        with self.workspace.db(write=True) as db:
            current = self.get(action_id, db)
            if current["status"] != "approved":
                raise WorkspaceError("Another executor claimed this action", "conflict")
            current.update(status="pending_external_action", expected_sha256=expected, output_path=target.relative_to(self.workspace.root).as_posix())
            self._save(db, current)
        # Exclusive creation prevents overwrite; a crash leaves pending state.
        target.parent.mkdir(parents=True, exist_ok=True)
        import os
        with target.open("xb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        return self.reconcile(action_id)

    def reconcile(self, action_id):
        with self.workspace.db(write=True) as db:
            action = self.get(action_id, db)
            if action["status"] not in {"pending_external_action", "completed"}:
                raise WorkspaceError("No dispatched action to reconcile", "invalid_transition")
            target = safe_path(self.workspace.root, action["output_path"])
            if not target.is_file() or file_hash(target) != action["expected_sha256"]:
                raise WorkspaceError("Delivery outcome is incomplete or changed; preserve files and investigate. No replay.", "reconcile_required")
            action["status"] = "completed"
            if action["receipt"] is None:
                action["receipt"] = {"path": action["output_path"], "sha256": action["expected_sha256"], "verified_at": now()}
            self._save(db, action)
        return action
