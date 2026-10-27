"""Read-only, selected-artifact preview contract; no provider/model calls."""
import hashlib
import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from research_hub.workspace.core import Workspace, WorkspaceError
from research_hub.workspace.research_draft import MAX_SOURCE_BYTES, read_selected_text
from research_hub.workspace.server import WorkspaceServer
from research_hub.workspace.service import WorkspaceService, call_workspace
from research_hub.workspace.tasks import TaskService


@pytest.fixture
def selected(tmp_path):
    ws = Workspace(tmp_path)
    ws.create_project(id="selected", title="Selected")
    raw = "Header\r\n研究😀: no reduction.\r\nTail".encode("utf-8")
    (tmp_path / "source.md").write_bytes(raw)
    artifact = ws.register_artifact("selected", path="source.md", role="evidence")
    record = ws.add_record("selected", kind="source", data={"title": "Synthetic", "locator": "fixture:source"})
    return ws, artifact, record, raw


@pytest.fixture
def server(selected):
    host = WorkspaceServer(selected[0].root, port=0)
    worker = threading.Thread(target=host.serve_forever, daemon=True)
    worker.start()
    try:
        yield host
    finally:
        host.shutdown()
        host.server_close()
        worker.join(timeout=3)


def request(host, project, artifact, headers=None):
    path = f"http://127.0.0.1:{host.server_port}/api/v1/projects/{project}/artifacts/{artifact}/text"
    try:
        response = urlopen(Request(path, headers=headers or {}), timeout=4)
    except HTTPError as exc:
        response = exc
    with response:
        return response.status, dict(response.headers), json.loads(response.read())


def test_preview_route_raw_bytes_no_store_and_no_side_effects(selected, server):
    ws, artifact, _, raw = selected
    before_db = ws.db_path.read_bytes()
    status, headers, body = request(server, "selected", artifact["id"])
    assert status == 200
    assert headers["Cache-Control"] == "no-store"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert body == {"ok": True, "preview": {
        "artifact_id": artifact["id"], "path": "source.md", "sha256": hashlib.sha256(raw).hexdigest(),
        "text": raw.decode("utf-8"), "codepoint_length": len(raw.decode("utf-8")),
        "bytes_read": len(raw), "truncated": False}}
    assert ws.db_path.read_bytes() == before_db
    assert (ws.root / "source.md").read_bytes() == raw
    assert TaskService(ws).list("selected") == []


@pytest.mark.parametrize("headers", [{"Origin": "https://other.example"}, {"Sec-Fetch-Site": "cross-site"}, {"Host": "other.example"}])
def test_untrusted_origin_cannot_read(selected, server, headers):
    status, response_headers, body = request(server, "selected", selected[1]["id"], headers)
    assert status == 403 and body["code"] == "forbidden"
    assert "研究" not in json.dumps(body, ensure_ascii=False)
    assert response_headers["Cache-Control"] == "no-store"


def test_preview_and_preparation_share_exact_reader(selected, monkeypatch):
    ws, artifact, record, raw = selected
    from research_hub.workspace import research_draft as route
    calls = []
    original = route.read_selected_text
    def spy(*args):
        calls.append(args[2])
        return original(*args)
    monkeypatch.setattr(route, "read_selected_text", spy)
    preview = WorkspaceService(ws.root).preview_text("selected", artifact_id=artifact["id"])["preview"]
    start = preview["text"].index("研究")
    task = TaskService(ws).create("selected", operation="paper-abstract-draft", source_selection={
        "artifact_id": artifact["id"], "source_record_id": record["id"], "start": start, "end": preview["codepoint_length"]})
    pack = task["request"]["research_draft"]["source_pack"]
    assert calls == [artifact["id"], artifact["id"]]
    assert pack["source_sha256"] == preview["sha256"]
    assert pack["text"] == preview["text"][start:]
    assert "\r\n" in pack["text"]


def test_no_unrelated_scan_or_process(selected, monkeypatch):
    import subprocess
    ws, artifact, _, _ = selected
    svc = WorkspaceService(ws.root)
    monkeypatch.setattr(svc.workspace, "artifacts", lambda *_: pytest.fail("all-artifact scan"))
    monkeypatch.setattr(svc.workspace, "records", lambda *_: pytest.fail("all-record scan"))
    monkeypatch.setattr(subprocess, "run", lambda *_args, **_kwargs: pytest.fail("unexpected process/model probe"))
    assert svc.preview_text("selected", artifact_id=artifact["id"])["ok"]


@pytest.mark.parametrize("kind", ["cross_project", "unregistered", "analysis", "pdf", "invalid_utf8", "oversized", "stale", "superseded", "linked", "traversal"])
def test_preview_failures_expose_no_text(selected, kind):
    ws, artifact, _, raw = selected
    project = "selected"
    if kind == "cross_project":
        ws.create_project(id="other", title="Other")
        project = "other"
    elif kind == "unregistered":
        artifact = {"id": "not-registered"}
    elif kind == "traversal":
        artifact = {"id": "../../source.md"}
    elif kind == "analysis":
        artifact = ws.register_artifact("selected", path="source.md", role="analysis")
    elif kind == "pdf":
        (ws.root / "source.pdf").write_bytes(b"%PDF secret content")
        artifact = ws.register_artifact("selected", path="source.pdf", role="evidence")
    elif kind in {"invalid_utf8", "oversized"}:
        (ws.root / "source.md").write_bytes(b"\xffsecret" if kind == "invalid_utf8" else b"z" * (MAX_SOURCE_BYTES + 1))
        artifact = ws.register_artifact("selected", path="source.md", role="evidence")
    elif kind in {"stale", "superseded"}:
        (ws.root / "source.md").write_bytes(b"changed private content")
        if kind == "superseded":
            ws.register_artifact("selected", path="source.md", role="evidence")
    else:
        (ws.root / "source.md").unlink()
        (ws.root / "linked.txt").write_bytes(raw)
        (ws.root / "source.md").symlink_to(ws.root / "linked.txt")
    body = call_workspace(ws.root, "project", "preview_text", {"project_id": project, "artifact_id": artifact["id"]})
    assert body["ok"] is False
    assert "preview" not in body and "text" not in body
    assert str(ws.root) not in json.dumps(body)
    assert "private content" not in json.dumps(body)


def test_preview_os_error_does_not_leak_absolute_path(selected, monkeypatch):
    from research_hub.workspace import research_draft as route
    def denied(*_args, **_kwargs):
        raise PermissionError("denied /secret/private-root/paper.md")
    monkeypatch.setattr(route, "safe_path", denied)
    body = call_workspace(selected[0].root, "project", "preview_text", {"project_id": "selected", "artifact_id": selected[1]["id"]})
    assert not body["ok"]
    assert "/secret" not in json.dumps(body)
    assert body["code"] == "source_unavailable"


def test_exact_byte_ceiling_and_empty_read_are_truthful(selected):
    ws, _, _, _ = selected
    for raw in (b"a" * MAX_SOURCE_BYTES, b""):
        (ws.root / "source.md").write_bytes(raw)
        a = ws.register_artifact("selected", path="source.md", role="evidence")
        preview = read_selected_text(ws, "selected", a["id"])
        assert preview["bytes_read"] == len(raw)
        assert preview["codepoint_length"] == len(raw)
        assert preview["truncated"] is False
    # Empty preview is allowed for reading; the shared prepare path still rejects
    # any empty abstract selection rather than fabricating a result.


def test_preview_path_is_workspace_relative_even_for_absolute_registration(selected):
    ws, artifact, _, _ = selected
    with ws.db(write=True) as db:
        body = json.loads(db.execute("SELECT body FROM artifacts WHERE id=?", (artifact["id"],)).fetchone()[0])
        body["path"] = str(ws.root / "source.md")
        db.execute("UPDATE artifacts SET body=? WHERE id=?", (json.dumps(body), artifact["id"]))
    preview = read_selected_text(ws, "selected", artifact["id"])
    assert preview["path"] == "source.md"
    assert str(ws.root) not in json.dumps(preview)
