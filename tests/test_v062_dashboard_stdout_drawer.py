from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from types import SimpleNamespace


def test_executor_response_carries_stdout_field(monkeypatch):
    from research_hub.dashboard import events, http_server

    previous_cfg = http_server.DashboardHandler.cfg
    previous_broadcaster = getattr(http_server.DashboardHandler, "broadcaster", None)
    previous_csrf = http_server.DashboardHandler.csrf_token
    previous_job_queue = getattr(http_server.DashboardHandler, "job_queue", None)

    monkeypatch.setattr(
        http_server,
        "execute_action",
        lambda action, slug, fields, timeout=300: SimpleNamespace(
            ok=True,
            action=action,
            command=["python", "-m", "research_hub", "dashboard"],
            stdout="hello",
            stderr="",
            returncode=0,
            duration_ms=12,
            to_dict=lambda: {
                "ok": True,
                "action": action,
                "command": ["python", "-m", "research_hub", "dashboard"],
                "stdout": "hello",
                "stderr": "",
                "returncode": 0,
                "duration_ms": 12,
            },
        ),
    )

    try:
        http_server.DashboardHandler.cfg = SimpleNamespace(root=".")
        http_server.DashboardHandler.broadcaster = events.EventBroadcaster()
        http_server.DashboardHandler.csrf_token = "csrf"
        http_server.DashboardHandler.job_queue = http_server.JobQueue()
        server = http_server.ThreadingHTTPServer(("127.0.0.1", 0), http_server.DashboardHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        conn = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        conn.request(
            "POST",
            "/api/exec",
            body=json.dumps({"action": "dashboard"}).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-CSRF-Token": "csrf"},
        )
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        conn.close()
        server.shutdown()
        server.server_close()
    finally:
        http_server.DashboardHandler.cfg = previous_cfg
        http_server.DashboardHandler.broadcaster = previous_broadcaster
        http_server.DashboardHandler.csrf_token = previous_csrf
        http_server.DashboardHandler.job_queue = previous_job_queue

    assert response.status == 200
    assert payload["stdout"] == "hello"


def test_sections_cluster_delete_has_preview_apply_labels():
    from research_hub.dashboard.sections import ManageSection

    html = ManageSection()._manage_card(
        SimpleNamespace(slug="agents", name="Agents", created_at="", zotero_collection_key="Z1", notebooklm_notebook_url="", paper_count=0),
        '<option value="agents">Agents</option>',
        "researcher",
    )
    assert 'data-preview-label="Preview cascade (dry-run)"' in html
    assert 'data-apply-label="Apply delete"' in html
