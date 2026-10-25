"""Generate synthetic UI contract fixtures through the actual private service.

No server, providers, native probes, real workspace, or public feature enablement.
Run from this repository: PYTHONPATH=src python scripts/generate_sqlite_ui_fixture.py
All socket/subprocess creation is forbidden. Only optional capability probes are
stubbed unavailable; saves, lookup, previews, preparation and snapshots are real.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import uuid


def forbidden(*_args, **_kwargs):
    raise AssertionError("Fixture generation forbids network/subprocess/model calls")


class ForbiddenSocket(socket.socket):
    def __init__(self, *_args, **_kwargs):
        forbidden()


socket.socket = ForbiddenSocket
socket.create_connection = forbidden
subprocess.Popen = forbidden

from research_hub.workspace import executor, writing, text_intake  # noqa: E402
from research_hub.workspace._sqlite_server import SQLiteWorkspaceService  # noqa: E402
from research_hub.workspace.core import WorkspaceError, encoded  # noqa: E402
from research_hub.workspace.service import WorkspaceService  # noqa: E402

executor.codex_capability = lambda: {"status": "unavailable", "message": "Synthetic fixture: provider probe not performed."}
writing.writing_capability = lambda: {"status": "unavailable", "message": "Synthetic fixture: optional writing probe not performed."}
text_intake._publish_copy = forbidden


def check_error(call, code):
    try:
        call()
    except WorkspaceError as error:
        assert error.code == code, (error.code, code)
    else:
        raise AssertionError(f"Expected {code}")


def generate():
    with tempfile.TemporaryDirectory(prefix="hub-synthetic-sqlite-ui-") as temporary:
        root = Path(temporary)
        service = SQLiteWorkspaceService(root)
        ws = service.workspace
        project = "synthetic-sqlite-ui"
        service.dispatch("project", "create", {"id": project, "title": "Synthetic SQLite UI contract"})
        service.dispatch("project", "create", {"id": "other-project", "title": "Other synthetic project"})
        namespace = ws.preparation_namespace()
        raw_text = "\ufeffPREFIX NOT SELECTED\r\nSelected 😀 abstract passage.\r\nSUFFIX NOT SELECTED"
        raw = raw_text.encode("utf-8")
        identity = {"version": 1, "workspace_instance_id": namespace, "key": str(uuid.uuid4())}
        payload = {"project_id": project, "intake_request": identity, "title": "Saved synthetic water abstract",
                   "locator": "", "reading_scope": "abstract", "input_kind": "file", "format": "md",
                   "content_base64": base64.b64encode(raw).decode("ascii")}
        saved = service.dispatch("project", "source_text", payload)
        replay = service.dispatch("project", "source_text", payload)
        assert replay["intake"]["disposition"] == "existing"
        assert replay["record"] == saved["record"] and replay["artifact"] == saved["artifact"]
        check_error(lambda: service.dispatch("project", "source_text", {**payload, "title": "Changed intent"}), "request_key_conflict")
        lookup_payload = {"project_id": project, "workspace_instance_id": namespace, "key": identity["key"]}
        before = ws.db_path.read_bytes()
        found = service.dispatch("project", "source_text_lookup", lookup_payload)
        preview = service.dispatch("project", "preview_text", {"project_id": project, "artifact_id": saved["artifact"]["id"]})
        assert before == ws.db_path.read_bytes(), "Exact reads changed the database"
        assert found["intake"]["state"] == "found" and preview["preview"] == saved["preview"]
        assert saved["preview"]["text"].encode("utf-8") == raw
        assert saved["artifact"]["sha256"] == hashlib.sha256(raw).hexdigest()
        assert "path" not in saved["artifact"] and "path" not in saved["preview"]
        assert saved["preview"]["reference"] == "hub-source:" + saved["record"]["id"]
        assert saved["record"]["data"]["identity_status"] == "unverified"
        assert saved["record"]["data"]["human_acceptance"] == "pending"
        assert not (root / "hub-sources").exists()

        second_payload = {**payload, "intake_request": {**identity, "key": str(uuid.uuid4())},
                          "title": "Second synthetic source — scope unknown", "reading_scope": "unknown",
                          "input_kind": "paste", "format": "txt", "content_base64": base64.b64encode(b"Another saved source.").decode("ascii")}
        second = service.dispatch("project", "source_text", second_payload)
        legacy_text = "Legacy file abstract."
        (root / "legacy.txt").write_bytes(legacy_text.encode())
        legacy_artifact = service.dispatch("project", "register", {"project_id": project, "path": "legacy.txt", "role": "evidence"})["artifact"]
        legacy_record = service.dispatch("project", "record", {"project_id": project, "kind": "source", "data": {"title": "Legacy synthetic source", "locator": "fixture:legacy"}})["record"]
        legacy_preview = service.dispatch("project", "preview_text", {"project_id": project, "artifact_id": legacy_artifact["id"]})
        before_prepare = service.dispatch("project", "show", {"project_id": project})
        selected = "Selected 😀 abstract passage."
        start = raw_text.index(selected)
        selection = {"artifact_id": saved["artifact"]["id"], "source_record_id": saved["record"]["id"], "start": start, "end": start + len(selected)}
        prepare_identity = {**identity, "key": str(uuid.uuid4())}
        prepare_payload = {"project_id": project, "operation": "paper-abstract-draft", "mode": "handoff",
                           "instructions": "Synthetic contract only, no provider.", "source_selection": selection, "prepare_request": prepare_identity}
        prepared = service.dispatch("task", "create", prepare_payload)
        task = prepared["task"]
        assert task["request"]["research_draft"]["profile"]["profile_version"] == 3
        assert task["request"]["research_draft"]["source_pack"]["text"] == selected
        assert service.dispatch("task", "create", prepare_payload)["task"]["id"] == task["id"]
        check_error(lambda: service.dispatch("task", "create", {**prepare_payload, "instructions": "Different intent"}), "request_key_conflict")
        reconciled = service.dispatch("task", "reconcile_preparation", {"project_id": project, "workspace_instance_id": namespace, "key": prepare_identity["key"]})
        assert reconciled["preparation"]["state"] == "found" and reconciled["task"]["id"] == task["id"]
        handoff = service.dispatch("task", "handoff", {"task_id": task["id"]})
        assert "PREFIX NOT SELECTED" not in encoded(handoff) and "SUFFIX NOT SELECTED" not in encoded(handoff)
        assert not list(root.rglob("selected-source.txt"))
        legacy_task = service.dispatch("task", "create", {"project_id": project, "operation": "paper-abstract-draft", "source_selection": {"artifact_id": legacy_artifact["id"], "source_record_id": legacy_record["id"], "start": 0, "end": len(legacy_text)}})["task"]
        assert legacy_task["request"]["research_draft"]["profile"]["profile_version"] == 2
        snapshot = service.dispatch("project", "show", {"project_id": project})
        assert raw_text not in encoded([snapshot["artifacts"], snapshot["records"]])
        assert "Another saved source." not in encoded([snapshot["artifacts"], snapshot["records"]])
        assert len(snapshot["tasks"]) == 2
        with ws.db() as db:
            assert db.execute("SELECT count(*) FROM source_text_blobs").fetchone()[0] == 2
        public = WorkspaceService(root)
        assert type(public._text_intake()) is text_intake.TextIntake
        assert "storage" not in public._text_intake_capability() and "experimental" not in public._text_intake_capability()
        workspace = service.capabilities()
        assert workspace["capabilities"]["text_intake"]["storage"] == {"kind": "workspace_blob", "version": 1}

        # Integrity and storage-version rejection are tested after fixture capture.
        with ws.db(write=True) as db:
            db.execute("UPDATE source_text_blobs SET content=? WHERE artifact_id=?", (raw.replace(b"PREFIX", b"BROKEN"), saved["artifact"]["id"]))
        check_error(lambda: service.dispatch("project", "preview_text", {"project_id": project, "artifact_id": saved["artifact"]["id"]}), "stale_input")
        stale = service.dispatch("project", "source_text_lookup", lookup_payload)
        assert stale["preview_status"] == "stale" and stale["preview"] is None and stale["artifact"]["current"] is False
        assert service.tasks.get(task["id"])["freshness"]["status"] != "current"
        with ws.db(write=True) as db:
            db.execute("UPDATE workspace_metadata SET value=? WHERE name='source_text_storage'", ('{"schema_version":999,"minimum_reader":"future"}',))
        check_error(lambda: service.dispatch("project", "preview_text", {"project_id": project, "artifact_id": second["artifact"]["id"]}), "unsupported_storage")
        assert (root / "legacy.txt").read_bytes() == legacy_text.encode()
        return {"provenance": {"generator": "scripts/generate_sqlite_ui_fixture.py", "source": "actual SQLiteWorkspaceService dispatch; synthetic temporary workspace", "optional_probes": "codex and writing explicitly stubbed unavailable; no provider/native probe executed", "not_acceptance": "No browser, HTTP, installed package, native Windows or scientific quality acceptance"},
                "workspace": workspace, "project_id": project, "intake_payload": payload, "saved": saved,
                "replay": replay, "lookup": found, "second_saved": second, "legacy_preview": legacy_preview,
                "before_prepare": before_prepare, "prepare_payload": prepare_payload, "prepared": prepared,
                "reconciled": reconciled, "snapshot": snapshot, "stale_lookup": stale}


if __name__ == "__main__":
    result = generate()
    destination = Path(__file__).resolve().parents[1] / "web/src/test-fixtures/sqlite-service.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "fixture": str(destination), "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(), "bytes": destination.stat().st_size,
                      "checks": ["exact_utf8_bytes", "save_replay", "save_conflict", "read_only_lookup", "no_source_file_materialization", "unverified_source_authority", "mixed_file_blob", "prepare_replay", "prepare_conflict", "profile3_selected_range", "profile2_legacy", "metadata_nonleak", "public_default_unchanged", "corruption_rejected", "unknown_storage_version_rejected"], "network_subprocess_calls": 0}))
