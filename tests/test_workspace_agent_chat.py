"""Tests for the interactive AI Agent Console bridge and HTTP endpoints."""

from __future__ import annotations

import http.client
import json
from pathlib import Path
import threading

from research_hub.workspace.core import Workspace
from research_hub.workspace.server import WorkspaceServer


def _seed_agent_workspace(root: Path) -> tuple[Workspace, dict[str, str]]:
    ws = Workspace(root)
    ws.create_project(
        id="agent-proj",
        title="LLM Survey Agent Project",
        archetype="review",
        goal="Test AI Agent workspace curation and sync proposals",
    )
    s1 = ws.add_record(
        "agent-proj",
        kind="source",
        data={
            "title": "Calibration Limits of LLM Survey Agents",
            "locator": "https://example.org/calibration-limits",
            "year": "2024",
            "doi": "10.1000/cal-2024",
        },
    )["id"]
    s2 = ws.add_record(
        "agent-proj",
        kind="source",
        data={
            "title": "Human Population Grounding Benchmarks",
            "locator": "https://example.org/population-benchmarks",
            "year": "2023",
            "doi": "10.1000/pop-2023",
        },
    )["id"]
    return ws, {"s1": s1, "s2": s2}


def _fetch_csrf(base: str) -> str:
    host_port = base.removeprefix("http://")
    conn = http.client.HTTPConnection(host_port, timeout=5)
    try:
        conn.request("GET", "/app/")
        resp = conn.getresponse()
        body = resp.read().decode("utf-8", errors="ignore")
        assert resp.status == 200
        for line in body.splitlines():
            pass
    finally:
        conn.close()
    return ""


def _http_call(server: WorkspaceServer, method: str, path: str, payload: dict | None = None):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        headers = {}
        body_bytes = None
        if payload is not None:
            body_bytes = json.dumps(payload).encode("utf-8")
            headers = {
                "Content-Type": "application/json",
                "X-CSRF-Token": server.csrf,
            }
        conn.request(method, path, body=body_bytes, headers=headers)
        resp = conn.getresponse()
        return resp.status, json.loads(resp.read().decode("utf-8"))
    finally:
        conn.close()


def test_agent_console_status_chat_read_only_and_confirm_apply(tmp_path: Path):
    ws, ids = _seed_agent_workspace(tmp_path / "ws")
    server = WorkspaceServer(ws.root, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        st_code, st_body = _http_call(server, "GET", "/api/v1/projects/agent-proj/integrations/agent/status")
        assert st_code == 200 and st_body["ok"] is True
        engine_ids = {e["id"] for e in st_body["available_engines"]}
        assert {"auto", "fast", "claude", "codex", "gemini"}.issubset(engine_ids)

        # 1. Chat turn proposing archive_source is strictly read-only
        records_before = ws.records("agent-proj")
        chat_code, chat_body = _http_call(
            server,
            "POST",
            "/api/v1/projects/agent-proj/integrations/agent/chat",
            {"message": "幫我刪除 Calibration Limits 這篇文獻", "engine": "fast"},
        )
        assert chat_code == 200 and chat_body["ok"] is True
        assert chat_body["engine_used"] == "fast"
        assert chat_body["requires_confirmation"] is True
        assert len(chat_body["proposed_actions"]) == 1
        assert chat_body["proposed_actions"][0]["type"] == "archive_source"
        assert chat_body["proposed_actions"][0]["source_id"] == ids["s1"]
        assert ws.records("agent-proj") == records_before

        # 2. Tampered / stale plan digest is rejected with 409 stale_preview
        stale_code, stale_body = _http_call(
            server,
            "POST",
            "/api/v1/projects/agent-proj/integrations/agent/apply",
            {
                "proposed_actions": chat_body["proposed_actions"],
                "expected_plan_digest": "deadbeef" * 8,
            },
        )
        assert stale_code == 409 and stale_body["code"] == "stale_preview"
        assert ws.records("agent-proj") == records_before

        # 3. Confirmed apply archives the paper
        apply_code, apply_body = _http_call(
            server,
            "POST",
            "/api/v1/projects/agent-proj/integrations/agent/apply",
            {
                "proposed_actions": chat_body["proposed_actions"],
                "expected_plan_digest": chat_body["plan_digest"],
            },
        )
        assert apply_code == 200 and apply_body["ok"] is True
        assert apply_body["applied_count"] == 1
        curations = [r for r in ws.records("agent-proj") if r["kind"] == "source_curation"]
        assert curations[-1]["data"]["source_id"] == ids["s1"]
        assert curations[-1]["data"]["archived"] is True

        # 4. Restore command brings back the archived source
        res_code, res_chat = _http_call(
            server,
            "POST",
            "/api/v1/projects/agent-proj/integrations/agent/chat",
            {"message": "復原 Calibration Limits 這篇文獻", "engine": "fast"},
        )
        assert res_code == 200
        assert res_chat["proposed_actions"][0]["type"] == "restore_source"
        res_apply_code, _ = _http_call(
            server,
            "POST",
            "/api/v1/projects/agent-proj/integrations/agent/apply",
            {
                "proposed_actions": res_chat["proposed_actions"],
                "expected_plan_digest": res_chat["plan_digest"],
            },
        )
        assert res_apply_code == 200
        curations_after = [r for r in ws.records("agent-proj") if r["kind"] == "source_curation"]
        assert curations_after[-1]["data"]["source_id"] == ids["s1"]
        assert curations_after[-1]["data"]["archived"] is False

        # 5. Tag, category, screening, and read-only inventory query
        tag_code, tag_chat = _http_call(
            server,
            "POST",
            "/api/v1/projects/agent-proj/integrations/agent/chat",
            {"message": "為 2024 論文加上 #benchmark #llm", "engine": "fast"},
        )
        assert tag_code == 200
        assert tag_chat["proposed_actions"][0]["type"] == "add_tags"
        assert tag_chat["proposed_actions"][0]["tags"] == ["benchmark", "llm"]

        inv_code, inv_chat = _http_call(
            server,
            "POST",
            "/api/v1/projects/agent-proj/integrations/agent/chat",
            {"message": "列出目前文獻狀態", "engine": "fast"},
        )
        assert inv_code == 200 and inv_chat["requires_confirmation"] is False
        assert "2 篇作用中文獻" in inv_chat["reply"]

        # 6. Non-list tags payload in apply() returns 409 stale_preview (never HTTP 500 TypeError)
        bad_tags_code, bad_tags_body = _http_call(
            server,
            "POST",
            "/api/v1/projects/agent-proj/integrations/agent/apply",
            {
                "proposed_actions": [{"type": "add_tags", "source_id": ids["s1"], "tags": 123, "summary": "bad"}],
                "expected_plan_digest": "a" * 64,
            },
        )
        assert bad_tags_code == 409 and bad_tags_body["code"] == "stale_preview"

        # 7. Missing explicit title with year does NOT widen to other papers; matched sync displays title
        miss_code, miss_chat = _http_call(
            server,
            "POST",
            "/api/v1/projects/agent-proj/integrations/agent/chat",
            {"message": 'Upload to NotebookLM only "Missing Paper" (2024)', "engine": "fast"},
        )
        assert miss_code == 200
        assert miss_chat["proposed_actions"] == []
        assert miss_chat["requires_confirmation"] is False

        hit_code, hit_chat = _http_call(
            server,
            "POST",
            "/api/v1/projects/agent-proj/integrations/agent/chat",
            {"message": 'Upload to NotebookLM only "Calibration Limits" (2024)', "engine": "fast"},
        )
        assert hit_code == 200 and hit_chat["requires_confirmation"] is True
        assert hit_chat["proposed_actions"][0]["selected_source_ids"] == [ids["s1"]]
        assert "Calibration Limits of LLM Survey Agents" in hit_chat["reply"]
        assert "Calibration Limits of LLM Survey Agents" in hit_chat["proposed_actions"][0]["summary"]

        # 8. Hashtag removal is classified as remove_tags (never archive_source)
        for rm_prompt in ("Remove #review from all papers", "移除所有文獻的 #review"):
            rm_code, rm_chat = _http_call(
                server,
                "POST",
                "/api/v1/projects/agent-proj/integrations/agent/chat",
                {"message": rm_prompt, "engine": "fast"},
            )
            assert rm_code == 200 and rm_chat["requires_confirmation"] is True
            assert len(rm_chat["proposed_actions"]) == 2
            assert all(a["type"] == "remove_tags" and a["tags"] == ["review"] for a in rm_chat["proposed_actions"])

        # 9. Batch > 50 actions is explicitly rejected instead of silently truncated to 50
        ws.create_project(
            id="agent-big",
            title="Large Batch Project",
            archetype="review",
            goal="Verify 50-action batch safety rejection",
        )
        for idx in range(51):
            ws.add_record(
                "agent-big",
                kind="source",
                data={"title": f"Batch Paper Number {idx:02d}", "locator": f"https://example.org/p/{idx}", "year": "2024"},
            )
        big_code, big_chat = _http_call(
            server,
            "POST",
            "/api/v1/projects/agent-big/integrations/agent/chat",
            {"message": "Archive all papers", "engine": "fast"},
        )
        assert big_code == 200
        assert big_chat["proposed_actions"] == []
        assert big_chat["requires_confirmation"] is False
        assert "51" in big_chat["reply"] and "50" in big_chat["reply"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
