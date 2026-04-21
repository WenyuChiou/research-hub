from __future__ import annotations

import http.client
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from research_hub.dashboard import events, http_server


def _post(port: int, path: str, *, token: str = "test-token") -> tuple[int, dict]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("POST", path, headers={"X-CSRF-Token": token})
    response = conn.getresponse()
    body = response.read().decode("utf-8")
    conn.close()
    return response.status, json.loads(body)


@pytest.fixture
def artifact_server(tmp_path: Path):
    root = tmp_path / "vault"
    root.mkdir()
    broadcaster = events.EventBroadcaster()
    previous_cfg = http_server.DashboardHandler.cfg
    previous_broadcaster = getattr(http_server.DashboardHandler, "broadcaster", None)
    previous_csrf = http_server.DashboardHandler.csrf_token
    http_server.DashboardHandler.cfg = SimpleNamespace(root=root)
    http_server.DashboardHandler.broadcaster = broadcaster
    http_server.DashboardHandler.csrf_token = "test-token"
    server = http_server.ThreadingHTTPServer(("127.0.0.1", 0), http_server.DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield SimpleNamespace(port=server.server_address[1], root=root, broadcaster=broadcaster)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        http_server.DashboardHandler.cfg = previous_cfg
        http_server.DashboardHandler.broadcaster = previous_broadcaster
        http_server.DashboardHandler.csrf_token = previous_csrf


def test_artifact_delete_removes_real_txt_file(artifact_server):
    target = artifact_server.root / ".research_hub" / "artifacts" / "alpha" / "brief.txt"
    target.parent.mkdir(parents=True)
    target.write_text("brief", encoding="utf-8")

    status, payload = _post(artifact_server.port, "/artifact-delete?path=.research_hub/artifacts/alpha/brief.txt")

    assert status == 200
    assert payload["ok"] is True
    assert not target.exists()


def test_artifact_delete_rejects_path_traversal(artifact_server):
    status, payload = _post(artifact_server.port, "/artifact-delete?path=../../etc/passwd")

    assert status == 403
    assert payload["ok"] is False


def test_artifact_delete_missing_file_returns_404(artifact_server):
    status, payload = _post(artifact_server.port, "/artifact-delete?path=missing.txt")

    assert status == 404
    assert payload["ok"] is False


def test_artifact_delete_wrong_csrf_rejected(artifact_server):
    target = artifact_server.root / "brief.txt"
    target.write_text("brief", encoding="utf-8")

    status, payload = _post(artifact_server.port, "/artifact-delete?path=brief.txt", token="wrong")

    assert status == 403
    assert payload["ok"] is False
    assert target.exists()


def test_artifact_delete_directory_rejected(artifact_server):
    target = artifact_server.root / "artifact-dir"
    target.mkdir()

    status, payload = _post(artifact_server.port, "/artifact-delete?path=artifact-dir")

    assert status == 400
    assert payload["ok"] is False
    assert target.exists()


def test_artifact_delete_broadcasts_vault_changed_after_success(artifact_server):
    queue = artifact_server.broadcaster.subscribe()
    target = artifact_server.root / "brief.txt"
    target.write_text("brief", encoding="utf-8")

    status, payload = _post(artifact_server.port, "/artifact-delete?path=brief.txt")

    assert status == 200
    assert payload["ok"] is True
    event = queue.get(timeout=1)
    assert event["type"] == "vault_changed"
    assert event["reason"] == "artifact-deleted"
