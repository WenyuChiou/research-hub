from __future__ import annotations

import json
import socket
import threading
import time
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from research_hub.api.jobs import JobQueue
from research_hub.api import v1 as api_v1
from research_hub.dashboard import events, http_server
from research_hub.dashboard.types import ClusterCard, CrystalSummary, DashboardData


@pytest.fixture
def fake_cfg(tmp_path):
    root = tmp_path / "vault"
    raw = root / "raw"
    hub = root / ".research_hub"
    raw.mkdir(parents=True)
    hub.mkdir(parents=True)
    return SimpleNamespace(root=root, raw=raw, hub=hub, research_hub_dir=hub, clusters_file=hub / "clusters.yaml")


@pytest.fixture(autouse=True)
def _reset_handler_state(fake_cfg):
    http_server.DashboardHandler.cfg = fake_cfg
    http_server.DashboardHandler.broadcaster = events.EventBroadcaster()
    http_server.DashboardHandler.csrf_token = "csrf"
    http_server.DashboardHandler.api_token = None
    http_server.DashboardHandler.job_queue = JobQueue()


@pytest.fixture
def server(fake_cfg, monkeypatch):
    monkeypatch.setattr(http_server, "render_dashboard_from_config", lambda cfg, csrf_token="": "<html></html>")
    monkeypatch.setattr(http_server, "collect_dashboard_data", lambda cfg: DashboardData(
        vault_root=str(cfg.root),
        generated_at="2026-04-20 00:00 UTC",
        persona="researcher",
        total_papers=0,
        total_clusters=0,
        papers_this_week=0,
    ))

    servers = []
    threads = []

    def _start(*, token: str | None = None):
        http_server.DashboardHandler.api_token = token
        http_server.DashboardHandler.job_queue = JobQueue()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            host, port = sock.getsockname()
        httpd = http_server.ThreadingHTTPServer((host, port), http_server.DashboardHandler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        servers.append(httpd)
        threads.append(thread)
        return port

    try:
        yield _start
    finally:
        for httpd in servers:
            httpd.shutdown()
            httpd.server_close()
        for thread in threads:
            thread.join(timeout=2)


def _request(port: int, method: str, path: str, payload=None, headers=None):
    body = None
    merged_headers = dict(headers or {})
    if payload is not None:
        if isinstance(payload, bytes):
            body = payload
        else:
            body = json.dumps(payload).encode("utf-8")
        merged_headers.setdefault("Content-Type", "application/json")
    request = Request(f"http://127.0.0.1:{port}{path}", data=body, headers=merged_headers, method=method)
    try:
        with urlopen(request, timeout=5) as response:
            raw = response.read().decode("utf-8")
            parsed = json.loads(raw) if raw else None
            return response.status, parsed, dict(response.headers)
    except HTTPError as exc:
        raw = exc.read().decode("utf-8")
        parsed = json.loads(raw) if raw else None
        return exc.code, parsed, dict(exc.headers)


def test_health_endpoint_returns_ok_without_auth(server):
    port = server()
    status, payload, _headers = _request(port, "GET", "/api/v1/health")
    assert status == 200
    assert payload["ok"] is True
    assert payload["version"] == "0.64.2"


def test_health_endpoint_returns_ok_even_with_auth_configured(server):
    port = server(token="secret")
    status, payload, _headers = _request(port, "GET", "/api/v1/health")
    assert status == 200
    assert payload["ok"] is True


def test_unauth_request_returns_401_when_token_set(server):
    port = server(token="secret")
    status, payload, _headers = _request(port, "POST", "/api/v1/search", {"query": "agents"})
    assert status == 401
    assert payload["code"] == "unauthorized"


def test_authorized_request_succeeds_with_correct_bearer(server, monkeypatch):
    monkeypatch.setattr(api_v1, "search_papers", lambda **kwargs: [{"title": "A"}])
    port = server(token="secret")
    status, payload, _headers = _request(
        port,
        "POST",
        "/api/v1/search",
        {"query": "agents"},
        headers={"Authorization": "Bearer secret"},
    )
    assert status == 200
    assert payload["ok"] is True


def test_search_endpoint_wraps_search_papers(server, monkeypatch):
    calls = {}

    def fake_search_papers(**kwargs):
        calls.update(kwargs)
        return [{"title": "Paper", "doi": "10.1/test"}]

    monkeypatch.setattr(api_v1, "search_papers", fake_search_papers)
    port = server()
    status, payload, _headers = _request(
        port,
        "POST",
        "/api/v1/search",
        {"query": "multi agent systems", "limit": 5, "backends": ["openalex"], "field": "cs"},
    )
    assert status == 200
    assert payload["results"][0]["title"] == "Paper"
    assert calls == {
        "query": "multi agent systems",
        "limit": 5,
        "backends": ["openalex"],
        "field": "cs",
    }


def test_websearch_endpoint_wraps_web_search(server, monkeypatch):
    monkeypatch.setattr(
        api_v1,
        "web_search",
        lambda **kwargs: {"ok": True, "provider": "duckduckgo", "results": [{"title": "Doc"}]},
    )
    port = server()
    status, payload, _headers = _request(port, "POST", "/api/v1/websearch", {"query": "rag", "max_results": 3})
    assert status == 200
    assert payload["provider"] == "duckduckgo"
    assert payload["results"][0]["title"] == "Doc"


def test_plan_endpoint_returns_structured_plan(server, monkeypatch):
    monkeypatch.setattr(
        api_v1,
        "plan_research_workflow",
        lambda intent: {"ok": True, "intent_summary": intent, "next_call": {"tool": "auto_research_topic"}},
    )
    port = server()
    status, payload, _headers = _request(port, "POST", "/api/v1/plan", {"intent": "learn rag"})
    assert status == 200
    assert payload["intent_summary"] == "learn rag"


def test_ask_endpoint_reads_cached_crystal(server, monkeypatch):
    monkeypatch.setattr(
        api_v1,
        "ask_cluster",
        lambda cluster, question, detail: {"ok": True, "cluster": cluster, "answer": "Cached answer", "detail": detail},
    )
    port = server()
    status, payload, _headers = _request(
        port,
        "POST",
        "/api/v1/ask",
        {"cluster": "alpha", "question": "what is this?", "detail": "gist"},
    )
    assert status == 200
    assert payload["answer"] == "Cached answer"


def test_auto_endpoint_returns_202_with_job_id(server, monkeypatch):
    monkeypatch.setattr(api_v1, "auto_research_topic", lambda **kwargs: {"ok": True, "cluster_slug": "alpha"})
    port = server()
    status, payload, headers = _request(port, "POST", "/api/v1/auto", {"topic": "agents"})
    assert status == 202
    assert payload["job_id"]
    assert headers["Location"] == payload["status_url"]


def test_jobs_endpoint_returns_running_then_completed(server, monkeypatch):
    def fake_auto_research_topic(**kwargs):
        time.sleep(0.15)
        return {"ok": True, "cluster_slug": "alpha", "steps": []}

    monkeypatch.setattr(api_v1, "auto_research_topic", fake_auto_research_topic)
    port = server()
    status, payload, _headers = _request(port, "POST", "/api/v1/auto", {"topic": "agents"})
    assert status == 202
    job_id = payload["job_id"]

    running_seen = False
    completed_payload = None
    for _ in range(20):
        job_status, job_payload, _ = _request(port, "GET", f"/api/v1/jobs/{job_id}")
        assert job_status == 200
        if job_payload["status"] == "running":
            running_seen = True
        if job_payload["status"] == "completed":
            completed_payload = job_payload
            break
        time.sleep(0.05)

    assert running_seen is True
    assert completed_payload is not None
    assert completed_payload["result"]["cluster_slug"] == "alpha"


def test_clusters_list_endpoint_returns_summary(server, monkeypatch, fake_cfg):
    monkeypatch.setattr(
        api_v1,
        "collect_dashboard_data",
        lambda cfg: DashboardData(
            vault_root=str(fake_cfg.root),
            generated_at="2026-04-20 00:00 UTC",
            persona="researcher",
            total_papers=1,
            total_clusters=1,
            papers_this_week=1,
            clusters=[ClusterCard(slug="alpha", name="Alpha", last_activity="2026-04-19", papers=[])],
            crystal_summary_by_cluster={
                "alpha": CrystalSummary(
                    cluster_slug="alpha",
                    total_canonical=5,
                    generated_count=2,
                    stale_count=0,
                )
            },
        ),
    )
    # v0.52.1: get_clusters now uses the lightweight list_clusters MCP fn
    # (full dashboard build was timing out on real vaults). Mock it here.
    monkeypatch.setattr(
        "research_hub.api.v1.list_clusters",
        lambda: [
            {"slug": "alpha", "name": "Alpha", "paper_count": 0, "crystal_count": 2, "last_activity": "2026-04-19"}
        ],
    )
    port = server()
    status, payload, _headers = _request(port, "GET", "/api/v1/clusters")
    assert status == 200
    assert payload["clusters"][0]["slug"] == "alpha"
    assert payload["clusters"][0]["crystal_count"] == 2


def test_cors_preflight_returns_204_with_headers(server):
    port = server(token="secret")
    status, _payload, headers = _request(port, "OPTIONS", "/api/v1/search")
    assert status == 204
    assert headers["Access-Control-Allow-Origin"] == "*"
    assert "GET" in headers["Access-Control-Allow-Methods"]


def test_bad_json_returns_400_with_error(server):
    port = server()
    status, payload, _headers = _request(
        port,
        "POST",
        "/api/v1/search",
        payload=b"{bad json",
        headers={"Content-Type": "application/json"},
    )
    assert status == 400
    assert payload["code"] == "bad_request"


def test_unknown_path_returns_404(server):
    port = server()
    status, payload, _headers = _request(port, "GET", "/api/v1/nonexistent")
    assert status == 404
    assert payload["code"] == "not_found"
