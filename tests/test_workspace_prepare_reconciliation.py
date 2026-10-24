"""Synthetic offline preparation identity; no model execution or quality claims."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
import sqlite3
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import uuid

import pytest

from research_hub.workspace.core import Workspace, WorkspaceError
from research_hub.workspace.service import WorkspaceService
from research_hub.workspace.server import WorkspaceServer


@pytest.fixture
def prepared_input(tmp_path):
    ws = Workspace(tmp_path)
    ws.create_project(id="paper", title="Synthetic paper")
    text = "Synthetic abstract: no reduction was observed."
    (tmp_path / "source.txt").write_text(text, encoding="utf-8")
    artifact = ws.register_artifact("paper", path="source.txt", role="evidence")
    source = ws.add_record("paper", kind="source", data={"title": "Synthetic", "locator": "fixture:paper"})
    return ws, {"operation": "paper-abstract-draft", "mode": "connected", "source_selection": {
        "artifact_id": artifact["id"], "source_record_id": source["id"], "start": 0, "end": len(text)}}


def envelope(ws):
    return {"version": 1, "workspace_instance_id": ws.preparation_namespace(), "key": str(uuid.uuid4())}


def submit(ws, payload, key):
    return WorkspaceService(ws.root).dispatch("task", "create", {
        "project_id": "paper", **payload, "prepare_request": key})


def test_dropped_success_response_replays_same_task(prepared_input):
    ws, payload = prepared_input
    key = envelope(ws)
    submit(ws, payload, key)  # committed response deliberately discarded
    result = submit(ws, payload, key)
    assert result["preparation"]["disposition"] == "existing"
    assert result["task"]["status"] == "ready"
    assert len(WorkspaceService(ws.root).tasks.list("paper")) == 1
    found = WorkspaceService(ws.root).tasks.reconcile_preparation("paper", **{
        "key": key["key"], "workspace_instance_id": key["workspace_instance_id"]})
    assert found["task"]["id"] == result["task"]["id"]


def test_concurrent_same_key_creates_one_task(prepared_input):
    ws, payload = prepared_input
    key = envelope(ws)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: submit(ws, payload, key), range(2)))
    assert len({item["task"]["id"] for item in results}) == 1
    assert sorted(item["preparation"]["disposition"] for item in results) == ["created", "existing"]
    with ws.db() as db:
        assert db.execute("SELECT count(*) FROM tasks").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM prepare_requests").fetchone()[0] == 1


def test_same_key_different_payload_conflicts(prepared_input):
    ws, payload = prepared_input
    key = envelope(ws)
    submit(ws, payload, key)
    with pytest.raises(WorkspaceError) as error:
        submit(ws, {**payload, "instructions": "Different intent"}, key)
    assert error.value.code == "request_key_conflict"
    assert len(WorkspaceService(ws.root).tasks.list("paper")) == 1


def test_keyless_clients_and_task_table_unchanged(prepared_input):
    ws, payload = prepared_input
    service = WorkspaceService(ws.root)
    first = service.dispatch("task", "create", {"project_id": "paper", **payload})
    second = service.dispatch("task", "create", {"project_id": "paper", **payload})
    assert first["task"]["id"] != second["task"]["id"]
    assert set(first) == {"ok", "task"}
    with ws.db() as db:
        assert [row[1] for row in db.execute("PRAGMA table_info(tasks)")] == ["id", "project", "body"]
        assert db.execute("SELECT count(*) FROM prepare_requests").fetchone()[0] == 0


@pytest.mark.parametrize("field,value", [
    ("key", ""), ("key", "a" * 10000), ("key", "../other"), ("key", None),
    ("key", "00000000-0000-1000-8000-000000000000"),
    ("key", "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"),
    ("workspace_instance_id", "invalid"), ("version", True), ("version", 2),
])
def test_invalid_identity_never_creates(prepared_input, field, value):
    ws, payload = prepared_input
    key = {**envelope(ws), field: value}
    with pytest.raises(WorkspaceError):
        submit(ws, payload, key)
    assert WorkspaceService(ws.root).tasks.list("paper") == []


@pytest.mark.parametrize("key", [None, {}, [], {"version": 1, "extra": "no"}])
def test_invalid_envelope_does_not_fall_back(prepared_input, key):
    with pytest.raises(WorkspaceError):
        submit(*prepared_input, key)
    assert WorkspaceService(prepared_input[0].root).tasks.list("paper") == []


def test_unsupported_operation_and_wrong_workspace(prepared_input):
    ws, payload = prepared_input
    key = envelope(ws)
    with pytest.raises(WorkspaceError, match="only for abstract"):
        submit(ws, {**payload, "operation": "draft"}, key)
    key["workspace_instance_id"] = str(uuid.uuid4())
    with pytest.raises(WorkspaceError) as error:
        submit(ws, payload, key)
    assert error.value.code == "workspace_mismatch"
    assert WorkspaceService(ws.root).tasks.list("paper") == []


def test_project_isolation_and_namespace_replacement(prepared_input, tmp_path):
    ws, payload = prepared_input
    key = envelope(ws)
    first = submit(ws, payload, key)
    ws.create_project(id="other", title="Other")
    tasks = WorkspaceService(ws.root).tasks
    assert tasks.reconcile_preparation("other", key=key["key"], workspace_instance_id=key["workspace_instance_id"])["preparation"]["state"] == "not_observed"
    a = ws.register_artifact("other", path="source.txt", role="evidence")
    r = ws.add_record("other", kind="source", data={"title": "Other", "locator": "fixture:other"})
    other = {**payload, "source_selection": {**payload["source_selection"], "artifact_id": a["id"], "source_record_id": r["id"]}}
    second = WorkspaceService(ws.root).dispatch("task", "create", {"project_id": "other", **other, "prepare_request": key})
    assert first["task"]["id"] != second["task"]["id"]
    assert len(tasks.list("paper")) == len(tasks.list("other")) == 1
    replacement = Workspace(tmp_path / "replacement")
    replacement.create_project(id="paper", title="Same public project name")
    assert replacement.preparation_namespace() != ws.preparation_namespace()
    with pytest.raises(WorkspaceError) as error:
        submit(replacement, payload, key)
    assert error.value.code == "workspace_mismatch"


def test_mapping_insert_failure_rolls_back_task(prepared_input):
    ws, payload = prepared_input
    key = envelope(ws)
    with ws.db(write=True) as db:
        db.execute("CREATE TRIGGER fail_mapping BEFORE INSERT ON prepare_requests BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        submit(ws, payload, key)
    with ws.db() as db:
        assert db.execute("SELECT count(*) FROM tasks").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM prepare_requests").fetchone()[0] == 0
    with ws.db(write=True) as db:
        db.execute("DROP TRIGGER fail_mapping")
    assert submit(ws, payload, key)["preparation"]["disposition"] == "created"


def test_after_commit_projection_failure_is_recoverable(prepared_input, monkeypatch):
    from research_hub.workspace.tasks import TaskService
    ws, payload = prepared_input
    key = envelope(ws)
    original = TaskService._with_freshness
    monkeypatch.setattr(TaskService, "_with_freshness", lambda *_: (_ for _ in ()).throw(OSError("synthetic response failure")))
    with pytest.raises(OSError):
        submit(ws, payload, key)
    monkeypatch.setattr(TaskService, "_with_freshness", original)
    recovered = submit(ws, payload, key)
    assert recovered["preparation"]["disposition"] == "existing"
    assert len(TaskService(ws).list("paper")) == 1


def test_failure_after_both_inserts_before_commit_rolls_back(prepared_input, monkeypatch):
    ws, payload = prepared_input
    key = envelope(ws)
    service = WorkspaceService(ws.root)
    original = service.workspace.db

    @contextmanager
    def fail_commit(*, write=False):
        with original(write=write) as db:
            yield db
            if write:
                assert db.execute("SELECT count(*) FROM prepare_requests").fetchone()[0] == 1
                raise OSError("synthetic interruption before commit")

    monkeypatch.setattr(service.workspace, "db", fail_commit)
    with pytest.raises(OSError):
        service.dispatch("task", "create", {"project_id": "paper", **payload, "prepare_request": key})
    with ws.db() as db:
        assert db.execute("SELECT count(*) FROM tasks").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM prepare_requests").fetchone()[0] == 0


def test_retention_mapping_cannot_be_orphaned_by_task_delete(prepared_input):
    ws, payload = prepared_input
    task = submit(ws, payload, envelope(ws))["task"]
    with pytest.raises(sqlite3.IntegrityError):
        with ws.db(write=True) as db:
            db.execute("DELETE FROM tasks WHERE id=?", (task["id"],))
    assert len(WorkspaceService(ws.root).tasks.list("paper")) == 1


def test_foreign_project_mapping_is_error_not_absence(prepared_input):
    ws, payload = prepared_input
    key = envelope(ws)
    submit(ws, payload, key)
    ws.create_project(id="other", title="Other")
    with ws.db(write=True) as db:
        db.execute("UPDATE prepare_requests SET project='other'")
    with pytest.raises(WorkspaceError) as error:
        WorkspaceService(ws.root).tasks.reconcile_preparation("other", key=key["key"], workspace_instance_id=key["workspace_instance_id"])
    assert error.value.code == "ledger_unavailable"


def test_invalid_source_creates_no_task_or_mapping(prepared_input):
    ws, payload = prepared_input
    key = envelope(ws)
    payload["source_selection"]["artifact_id"] = "unavailable"
    with pytest.raises(WorkspaceError):
        submit(ws, payload, key)
    with ws.db() as db:
        assert db.execute("SELECT count(*) FROM tasks").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM prepare_requests").fetchone()[0] == 0


def test_explicit_defaults_match_omitted_defaults(prepared_input):
    ws, payload = prepared_input
    key = envelope(ws)
    payload = {k: v for k, v in payload.items() if k != "mode"}
    original = submit(ws, payload, key)
    replay = submit(ws, {**payload, "mode": "handoff", "instructions": ""}, key)
    assert replay["task"]["id"] == original["task"]["id"]


def test_stale_and_cancelled_task_is_returned_not_rebuilt(prepared_input):
    ws, payload = prepared_input
    key = envelope(ws)
    first = submit(ws, payload, key)["task"]
    (ws.root / "source.txt").write_text("Changed source", encoding="utf-8")
    tasks = WorkspaceService(ws.root).tasks
    replay = submit(ws, payload, key)["task"]
    assert replay["id"] == first["id"]
    assert replay["request"] == first["request"]
    with pytest.raises(WorkspaceError):
        tasks.check_inputs(replay)
    tasks.cancel(first["id"])
    assert submit(ws, payload, key)["task"]["status"] == "cancelled"
    assert len(tasks.list("paper")) == 1


def test_lookup_miss_is_read_only_and_late_prepare_uses_same_key(prepared_input):
    ws, payload = prepared_input
    key = envelope(ws)
    before = ws.db_path.read_bytes()
    tasks = WorkspaceService(ws.root).tasks
    lookup = tasks.reconcile_preparation("paper", key=key["key"], workspace_instance_id=key["workspace_instance_id"])
    assert lookup == {"ok": True, "preparation": {"state": "not_observed", "key": key["key"]}}
    assert ws.db_path.read_bytes() == before
    submit(ws, payload, key)
    assert submit(ws, payload, key)["preparation"]["disposition"] == "existing"


def test_old_workspace_explicit_upgrade_preserves_tasks(prepared_input):
    ws, payload = prepared_input
    task = WorkspaceService(ws.root).tasks.create("paper", **payload)
    with ws.db(write=True) as db:
        db.execute("DROP TABLE prepare_requests")
        db.execute("DROP TABLE workspace_metadata")
    before = ws.db_path.read_bytes()
    assert ws.preparation_namespace() is None
    assert ws.db_path.read_bytes() == before
    ws.initialize_preparations()
    namespace = ws.preparation_namespace()
    assert namespace
    assert WorkspaceService(ws.root).tasks.get(task["id"])["request"] == task["request"]
    ws.initialize_preparations()
    assert ws.preparation_namespace() == namespace


def test_uninitialized_read_does_not_create_workspace(tmp_path):
    ws = Workspace(tmp_path / "empty")
    assert ws.preparation_namespace() is None
    ws.initialize_preparations()
    assert not ws.root.exists()


@pytest.fixture
def server(prepared_input):
    host = WorkspaceServer(prepared_input[0].root, port=0)
    thread = threading.Thread(target=host.serve_forever, daemon=True)
    thread.start()
    try:
        yield host
    finally:
        host.shutdown()
        host.server_close()
        thread.join(timeout=3)


def http(host, path, *, data=None, headers=None):
    request = Request(f"http://127.0.0.1:{host.server_port}/api/v1{path}",
                      data=None if data is None else json.dumps(data).encode(), headers=headers or {})
    try:
        response = urlopen(request, timeout=4)
    except HTTPError as error:
        response = error
    with response:
        return response.status, dict(response.headers), json.loads(response.read())


def test_http_prepare_and_read_contract(prepared_input, server):
    ws, payload = prepared_input
    key = envelope(ws)
    headers = {"Content-Type": "application/json", "X-CSRF-Token": server.csrf}
    status, _, first = http(server, "/projects/paper/tasks", data={**payload, "prepare_request": key}, headers=headers)
    assert status == 200
    status, _, second = http(server, "/projects/paper/tasks", data={**payload, "prepare_request": key}, headers=headers)
    assert status == 200 and first["task"]["id"] == second["task"]["id"]
    before = ws.db_path.read_bytes()
    status, response_headers, found = http(server, f"/projects/paper/preparations/{key['key']}", headers={"X-Workspace-Instance": key["workspace_instance_id"]})
    assert status == 200 and response_headers["Cache-Control"] == "no-store"
    assert found["task"]["id"] == first["task"]["id"]
    assert found["task"]["status"] == "ready" and found["task"]["result"] is None
    assert found["task"]["attempts"] == []
    assert ws.db_path.read_bytes() == before
    status, _, denied = http(server, "/projects/paper/tasks", data={**payload, "prepare_request": key}, headers={"Content-Type": "application/json"})
    assert status == 403 and denied["code"] == "forbidden"
    status, _, missing_scope = http(server, f"/projects/paper/preparations/{key['key']}")
    assert status == 400 and missing_scope["code"] == "invalid_request"
    status, _, unknown_project = http(server, f"/projects/missing/preparations/{key['key']}", headers={"X-Workspace-Instance": key["workspace_instance_id"]})
    assert status == 400 and unknown_project["code"] == "not_found"


@pytest.mark.parametrize("extra", [{"Origin": "https://other.example"}, {"Host": "other.example"}, {"Sec-Fetch-Site": "cross-site"}])
def test_key_does_not_bypass_origin(prepared_input, server, extra):
    ws, payload = prepared_input
    key = envelope(ws)
    submit(ws, payload, key)
    status, _, body = http(server, f"/projects/paper/preparations/{key['key']}", headers={"X-Workspace-Instance": key["workspace_instance_id"], **extra})
    assert status == 403 and body["code"] == "forbidden"
    assert "task" not in body
