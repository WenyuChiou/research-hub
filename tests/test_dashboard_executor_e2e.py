from __future__ import annotations

import http.client
import json
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from research_hub.clusters import ClusterRegistry
from research_hub.dashboard import events, executor, http_server
from research_hub.dashboard.types import ClusterCard, DashboardData
from research_hub.paper import read_labels

from tests._e2e_sandbox import sandbox_cfg


@dataclass
class _FakeCompletedProcess:
    returncode: int = 0
    stdout: str = "ok"
    stderr: str = ""


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _post_json(port: int, path: str, payload: dict) -> tuple[int, dict]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request(
        "POST",
        path,
        body=json.dumps(payload),
        headers={"Content-Type": "application/json"},
    )
    response = conn.getresponse()
    body = response.read().decode("utf-8")
    conn.close()
    return response.status, json.loads(body)


def _make_dashboard_data() -> DashboardData:
    return DashboardData(
        vault_root="/tmp/vault",
        generated_at="2026-04-20 00:00 UTC",
        persona="researcher",
        total_papers=5,
        total_clusters=2,
        papers_this_week=5,
        clusters=[
            ClusterCard(slug="alpha", name="Alpha"),
            ClusterCard(slug="beta", name="Beta"),
        ],
    )


@pytest.fixture
def live_server(sandbox_cfg, monkeypatch):
    monkeypatch.setattr(http_server, "collect_dashboard_data", lambda cfg: _make_dashboard_data())
    monkeypatch.setattr(http_server, "render_dashboard_from_config", lambda cfg, csrf_token="": "<html></html>")
    broadcaster = events.EventBroadcaster()
    http_server.DashboardHandler.cfg = sandbox_cfg
    http_server.DashboardHandler.broadcaster = broadcaster
    http_server.DashboardHandler.csrf_token = ""
    server = http_server.ThreadingHTTPServer(("127.0.0.1", 0), http_server.DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _listen_for_sse(port: int) -> tuple[queue.Queue, threading.Thread]:
    out: queue.Queue = queue.Queue()

    def worker() -> None:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        conn.request("GET", "/api/events")
        response = conn.getresponse()
        event_name = "message"
        data_lines: list[str] = []
        try:
            while True:
                try:
                    line = response.fp.readline()
                except TimeoutError:
                    break
                if not line:
                    break
                text = line.decode("utf-8").rstrip("\r\n")
                if text.startswith("event:"):
                    event_name = text.split(":", 1)[1].strip()
                    continue
                if text.startswith("data:"):
                    data_lines.append(text.split(":", 1)[1].lstrip())
                    continue
                if text == "":
                    if data_lines:
                        payload = json.loads("\n".join(data_lines))
                        out.put((event_name, payload))
                    event_name = "message"
                    data_lines = []
        finally:
            conn.close()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return out, thread


_CATEGORY_A_CASES = [
    ("rename", "alpha", {"new_name": "Alpha Renamed"}, lambda cfg: ClusterRegistry(cfg.clusters_file).get("alpha").name == "Alpha Renamed"),
    ("delete", "alpha", {}, lambda cfg: ClusterRegistry(cfg.clusters_file).get("alpha") is not None),
    ("move", "alpha-paper-1", {"target_cluster": "beta"}, lambda cfg: (cfg.raw / "beta" / "alpha-paper-1.md").exists()),
    ("label", "alpha-paper-1", {"label": "reviewed"}, lambda cfg: read_labels(cfg, "alpha-paper-1").labels == ["reviewed"]),
    ("mark", "alpha-paper-1", {"status": "cited"}, lambda cfg: "status: cited" in _read_text(cfg.raw / "alpha" / "alpha-paper-1.md")),
    ("remove", "alpha-paper-2", {}, lambda cfg: not (cfg.raw / "alpha" / "alpha-paper-2.md").exists()),
    ("topic-build", "alpha", {}, lambda cfg: any((cfg.raw / "alpha" / "topics").glob("*.md"))),
    ("dashboard", None, {}, lambda cfg: (cfg.research_hub_dir / "dashboard.html").exists()),
    ("pipeline-repair", "alpha", {"execute": False}, lambda cfg: True),
    ("vault-polish-markdown", "alpha", {"apply": False}, lambda cfg: True),
    ("bases-emit", "alpha", {"force": True}, lambda cfg: (cfg.hub / "alpha" / "alpha.base").exists()),
    ("clusters-analyze", "alpha", {}, lambda cfg: (Path.cwd() / "docs" / "cluster_autosplit_alpha.md").exists()),
]


@pytest.mark.parametrize(("action", "slug", "fields", "assertion"), _CATEGORY_A_CASES, ids=[case[0] for case in _CATEGORY_A_CASES])
def test_e2e_category_a_real_cli(action, slug, fields, assertion, sandbox_cfg):
    if action == "delete":
        slug = "beta"
    result = executor.execute_action(action, slug, dict(fields), timeout=30)
    assert result.returncode == 0, result.stderr or result.stdout
    assert result.ok is True
    assert assertion(sandbox_cfg)


_CATEGORY_B_CASES = [
    ("notebooklm-bundle", "alpha", {}, ["notebooklm", "bundle", "--cluster", "alpha"]),
    ("notebooklm-upload", "alpha", {"visible": False}, ["notebooklm", "upload", "--cluster", "alpha", "--headless"]),
    ("notebooklm-generate", "alpha", {"kind": "brief"}, ["notebooklm", "generate", "--cluster", "alpha", "--type", "brief"]),
    ("notebooklm-download", "alpha", {"kind": "brief"}, ["notebooklm", "download", "--cluster", "alpha", "--type", "brief"]),
    ("notebooklm-ask", "alpha", {"question": "Why?", "timeout": "90"}, ["notebooklm", "ask", "--cluster", "alpha", "--question", "Why?", "--timeout", "90"]),
    ("discover-new", "alpha", {"query": "agents"}, ["discover", "new", "--cluster", "alpha", "--query", "agents"]),
    ("discover-continue", "alpha", {"scored": "scored.json"}, ["discover", "continue", "--cluster", "alpha", "--scored", "scored.json"]),
    ("autofill-apply", "alpha", {"scored": "scored.json"}, ["autofill", "apply", "--cluster", "alpha", "--scored", "scored.json"]),
]


@pytest.mark.parametrize(("action", "slug", "fields", "expected_tokens"), _CATEGORY_B_CASES, ids=[case[0] for case in _CATEGORY_B_CASES])
def test_e2e_category_b_cli_shape(monkeypatch, action, slug, fields, expected_tokens):
    calls: dict[str, object] = {}

    def fake_run(args, **kwargs):
        calls["args"] = args
        calls["kwargs"] = kwargs
        return _FakeCompletedProcess()

    monkeypatch.setattr(executor.subprocess, "run", fake_run)
    result = executor.execute_action(action, slug, dict(fields), timeout=30)
    assert result.ok is True
    assert result.returncode == 0
    assert calls["kwargs"]["shell"] is False
    for token in expected_tokens:
        assert token in calls["args"]


def test_e2e_merge_moves_papers_and_removes_source(sandbox_cfg):
    result = executor.execute_action("merge", "alpha", {"target": "beta"}, timeout=30)
    registry = ClusterRegistry(sandbox_cfg.clusters_file)
    assert result.ok is True, result.stderr
    assert registry.get("alpha") is None
    assert registry.get("beta") is not None
    assert len(list((sandbox_cfg.raw / "beta").glob("*.md"))) == 5


def test_e2e_split_creates_new_cluster(sandbox_cfg):
    result = executor.execute_action(
        "split",
        "alpha",
        {"query": "shared query", "new_name": "Shared Query"},
        timeout=30,
    )
    registry = ClusterRegistry(sandbox_cfg.clusters_file)
    assert result.ok is True, result.stderr
    assert registry.get("shared-query") is not None
    assert (sandbox_cfg.raw / "shared-query" / "alpha-paper-3.md").exists()


def test_e2e_bind_zotero_updates_registry(sandbox_cfg):
    result = executor.execute_action("bind-zotero", "alpha", {"zotero": "ZK1"}, timeout=30)
    cluster = ClusterRegistry(sandbox_cfg.clusters_file).get("alpha")
    assert result.ok is True, result.stderr
    assert cluster is not None
    assert cluster.zotero_collection_key == "ZK1"


def test_e2e_bind_nlm_updates_registry(sandbox_cfg):
    result = executor.execute_action("bind-nlm", "alpha", {"notebooklm": "URL"}, timeout=30)
    cluster = ClusterRegistry(sandbox_cfg.clusters_file).get("alpha")
    assert result.ok is True, result.stderr
    assert cluster is not None
    assert cluster.notebooklm_notebook == "URL"


def test_e2e_ingest_dry_run_returns_zero(sandbox_cfg):
    result = executor.execute_action(
        "ingest",
        None,
        {
            "cluster_slug": "alpha",
            "papers_input": str(Path.cwd() / "papers_input.json"),
            "dry_run": True,
        },
        timeout=30,
    )
    assert result.ok is True, result.stderr
    assert result.returncode == 0
    assert not (sandbox_cfg.raw / "alpha" / "dry-run-ingest-paper.md").exists()


def test_e2e_compose_draft_writes_markdown(sandbox_cfg):
    result = executor.execute_action(
        "compose-draft",
        None,
        {
            "cluster_slug": "alpha",
            "outline": "Introduction;Methods",
            "quote_slugs": ["alpha-paper-1"],
            "style": "apa",
            "include_bibliography": True,
        },
        timeout=30,
    )
    drafts = list((sandbox_cfg.root / "drafts").glob("*-alpha-draft.md"))
    assert result.ok is True, result.stderr
    assert drafts
    assert "# Alpha - Draft" in _read_text(drafts[0])


def test_e2e_sse_event_after_action(live_server):
    stream, thread = _listen_for_sse(live_server)
    status, payload = _post_json(
        live_server,
        "/api/exec",
        {"action": "rename", "slug": "alpha", "fields": {"new_name": "Alpha Live"}},
    )
    assert status == 200
    assert payload["ok"] is True

    deadline = time.time() + 5
    seen: list[tuple[str, dict]] = []
    while time.time() < deadline:
        try:
            item = stream.get(timeout=0.5)
        except queue.Empty:
            continue
        seen.append(item)
        if item[0] == "state-change":
            assert item[1]["action"] == "rename"
            break
    else:
        raise AssertionError(f"missing state-change SSE event; saw {seen!r}")

    thread.join(timeout=1)


def test_e2e_error_rendering(live_server, monkeypatch):
    failed = executor.ExecResult(
        ok=False,
        action="rename",
        command=["python", "-m", "research_hub", "clusters", "rename"],
        stdout="",
        stderr="rename failed",
        returncode=2,
        duration_ms=1,
    )
    monkeypatch.setattr(http_server, "execute_action", lambda action, slug, fields, timeout=300: failed)
    status, payload = _post_json(
        live_server,
        "/api/exec",
        {"action": "rename", "slug": "alpha", "fields": {"new_name": "bad"}},
    )
    assert status == 200
    assert payload["ok"] is False
    assert "stderr" in payload
    assert payload["stderr"] == "rename failed"
    assert payload["error"] == "rename failed"


def test_e2e_timeout_handling(live_server, monkeypatch):
    def fake_run(args, **kwargs):
        time.sleep(0.1)
        raise executor.subprocess.TimeoutExpired(cmd=args, timeout=kwargs["timeout"])

    monkeypatch.setattr(executor.subprocess, "run", fake_run)
    started = time.monotonic()
    status, payload = _post_json(
        live_server,
        "/api/exec",
        {"action": "dashboard", "fields": {}, "timeout": 1},
    )
    elapsed = time.monotonic() - started
    assert elapsed < 10
    assert status == 200
    assert payload["ok"] is False
    assert payload["returncode"] == -1
    assert payload.get("error") == "timeout"
    assert "timeout after 1s" in payload["stderr"]
