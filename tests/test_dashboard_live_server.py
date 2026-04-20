from __future__ import annotations

import http.client
import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from research_hub import cli
from research_hub.dashboard import events, executor, http_server
from research_hub.dashboard.types import ClusterCard, DashboardData


@dataclass
class _FakeCompletedProcess:
    returncode: int = 0
    stdout: str = "ok"
    stderr: str = ""


def _fake_dashboard_data() -> DashboardData:
    return DashboardData(
        vault_root="/tmp/vault",
        generated_at="2026-04-15 00:00 UTC",
        persona="researcher",
        total_papers=1,
        total_clusters=1,
        papers_this_week=1,
        clusters=[ClusterCard(slug="alpha", name="Alpha")],
    )


def _post_json(port: int, path: str, payload: dict) -> tuple[int, dict]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
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


def _get_json(port: int, path: str) -> tuple[int, dict]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", path)
    response = conn.getresponse()
    body = response.read().decode("utf-8")
    conn.close()
    return response.status, json.loads(body)


@pytest.fixture
def fake_cfg(tmp_path: Path):
    root = tmp_path / "vault"
    raw = root / "raw"
    hub = root / ".research_hub"
    raw.mkdir(parents=True)
    hub.mkdir(parents=True)
    (hub / "clusters.yaml").write_text("clusters: []\n", encoding="utf-8")
    (hub / "dedup_index.json").write_text("{}", encoding="utf-8")
    (hub / "manifest.jsonl").write_text("", encoding="utf-8")
    return SimpleNamespace(root=root, raw=raw, research_hub_dir=hub, clusters_file=hub / "clusters.yaml")


@pytest.fixture
def live_server(fake_cfg, monkeypatch):
    monkeypatch.setattr(http_server, "collect_dashboard_data", lambda cfg: _fake_dashboard_data())
    monkeypatch.setattr(http_server, "render_dashboard_from_config", lambda cfg: "<html><body>dashboard</body></html>")

    broadcaster = events.EventBroadcaster()
    http_server.DashboardHandler.cfg = fake_cfg
    http_server.DashboardHandler.broadcaster = broadcaster
    server = http_server.ThreadingHTTPServer(("127.0.0.1", 0), http_server.DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_serve_dashboard_binds_localhost_only(fake_cfg):
    with pytest.raises(ValueError):
        http_server.serve_dashboard(
            fake_cfg,
            host="0.0.0.0",
            port=8765,
            allow_external=False,
            open_browser=False,
        )


def test_healthz_returns_version(live_server):
    status, payload = _get_json(live_server, "/healthz")
    assert status == 200
    assert payload["ok"] is True
    assert payload["mode"] == "live"
    assert payload["version"]


def test_api_state_returns_dashboard_json(live_server):
    status, payload = _get_json(live_server, "/api/state")
    assert status == 200
    assert payload["total_papers"] == 1
    assert "clusters" in payload


def test_api_exec_dashboard_runs_subprocess(live_server, monkeypatch):
    calls = {}

    def fake_run(args, **kwargs):
        calls["args"] = args
        calls["kwargs"] = kwargs
        return _FakeCompletedProcess()

    monkeypatch.setattr(executor.subprocess, "run", fake_run)
    status, payload = _post_json(live_server, "/api/exec", {"action": "dashboard"})
    assert status == 200
    assert payload["ok"] is True
    assert calls["args"][:3] == [executor.sys.executable, "-m", "research_hub"]
    assert calls["args"][-1] == "dashboard"


def test_api_exec_unknown_action_rejects(live_server):
    status, payload = _post_json(live_server, "/api/exec", {"action": "nuke"})
    assert status == 400
    assert "ALLOWED_ACTIONS" in payload["error"]


def test_api_exec_missing_required_field_rejects(live_server):
    status, payload = _post_json(
        live_server,
        "/api/exec",
        {"action": "rename", "slug": "alpha", "fields": {}},
    )
    assert status == 400
    assert "missing required fields" in payload["error"]


def test_api_exec_never_uses_shell_true(live_server, monkeypatch):
    calls = {}

    def fake_run(args, **kwargs):
        calls["kwargs"] = kwargs
        return _FakeCompletedProcess()

    monkeypatch.setattr(executor.subprocess, "run", fake_run)
    status, _payload = _post_json(live_server, "/api/exec", {"action": "dashboard"})
    assert status == 200
    assert calls["kwargs"]["shell"] is False


def test_api_exec_timeout_enforced(monkeypatch):
    def fake_run(args, **kwargs):
        raise executor.subprocess.TimeoutExpired(cmd=args, timeout=1)

    monkeypatch.setattr(executor.subprocess, "run", fake_run)
    result = executor.execute_action("dashboard", None, {}, timeout=1)
    assert result.ok is False
    assert "timeout" in result.stderr


def test_execute_action_command_is_list(monkeypatch):
    monkeypatch.setattr(executor.subprocess, "run", lambda args, **kwargs: _FakeCompletedProcess())
    result = executor.execute_action("dashboard", None, {})
    assert isinstance(result.command, list)
    assert all(isinstance(part, str) for part in result.command)


_ACTION_CASES = {
    "rename": {"slug": "alpha", "fields": {"new_name": "Alpha 2"}, "subcommand": ("clusters", "rename"), "expect_slug": "alpha"},
    "merge": {"slug": "alpha", "fields": {"target": "beta"}, "subcommand": ("clusters", "merge"), "expect_slug": "alpha"},
    "split": {"slug": "alpha", "fields": {"query": "topic", "new_name": "Alpha Sub"}, "subcommand": ("clusters", "split"), "expect_slug": "alpha"},
    "bind-zotero": {"slug": "alpha", "fields": {"zotero": "ABCD1234"}, "subcommand": ("clusters", "bind"), "expect_slug": "alpha"},
    "bind-nlm": {"slug": "alpha", "fields": {"notebooklm": "Notebook"}, "subcommand": ("clusters", "bind"), "expect_slug": "alpha"},
    "delete": {"slug": "alpha", "fields": {}, "subcommand": ("clusters", "delete"), "expect_slug": "alpha"},
    "move": {"slug": "paper-1", "fields": {"target_cluster": "beta"}, "subcommand": ("move",), "expect_slug": "paper-1"},
    "label": {"slug": "paper-1", "fields": {"label": "seed"}, "subcommand": ("label",), "expect_slug": "paper-1"},
    "mark": {"slug": "paper-1", "fields": {"status": "reading"}, "subcommand": ("mark",), "expect_slug": "paper-1"},
    "remove": {"slug": "paper-1", "fields": {"dry_run": True}, "subcommand": ("remove",), "expect_slug": "paper-1"},
    "ingest": {"slug": None, "fields": {"cluster_slug": "alpha", "papers_input": "papers.json"}, "subcommand": ("ingest",), "expect_slug": "alpha"},
    "topic-build": {"slug": "alpha", "fields": {}, "subcommand": ("topic", "build"), "expect_slug": "alpha"},
    "dashboard": {"slug": None, "fields": {}, "subcommand": ("dashboard",), "expect_slug": None},
    "pipeline-repair": {"slug": "alpha", "fields": {"execute": False}, "subcommand": ("pipeline", "repair"), "expect_slug": "alpha"},
    "notebooklm-bundle": {"slug": "alpha", "fields": {}, "subcommand": ("notebooklm", "bundle"), "expect_slug": "alpha"},
    "notebooklm-upload": {"slug": "alpha", "fields": {"visible": False}, "subcommand": ("notebooklm", "upload"), "expect_slug": "alpha"},
    "notebooklm-generate": {"slug": "alpha", "fields": {"kind": "brief"}, "subcommand": ("notebooklm", "generate"), "expect_slug": "alpha"},
    "notebooklm-download": {"slug": "alpha", "fields": {"kind": "brief"}, "subcommand": ("notebooklm", "download"), "expect_slug": "alpha"},
    "notebooklm-ask": {"slug": "alpha", "fields": {"question": "Why?", "timeout": "90"}, "subcommand": ("notebooklm", "ask"), "expect_slug": "alpha"},
    "vault-polish-markdown": {"slug": "alpha", "fields": {"apply": False}, "subcommand": ("vault", "polish-markdown"), "expect_slug": "alpha"},
    "bases-emit": {"slug": "alpha", "fields": {"force": True}, "subcommand": ("bases", "emit"), "expect_slug": "alpha"},
    "discover-new": {"slug": "alpha", "fields": {"query": "agents"}, "subcommand": ("discover", "new"), "expect_slug": "alpha"},
    "discover-continue": {"slug": "alpha", "fields": {"scored": "scored.json"}, "subcommand": ("discover", "continue"), "expect_slug": "alpha"},
    "autofill-apply": {"slug": "alpha", "fields": {"scored": "scored.json"}, "subcommand": ("autofill", "apply"), "expect_slug": "alpha"},
    "compose-draft": {
        "slug": None,
        "fields": {
            "cluster_slug": "alpha",
            "outline": "Intro;Methods",
            "quote_slugs": ["q-1", "q-2"],
            "style": "apa",
            "include_bibliography": True,
        },
        "subcommand": ("compose-draft",),
        "expect_slug": "alpha",
    },
    "clusters-analyze": {"slug": "alpha", "fields": {}, "subcommand": ("clusters", "analyze"), "expect_slug": "alpha"},
}


def test_action_matrix_covers_all_allowed_actions():
    assert set(_ACTION_CASES) == set(executor.ALLOWED_ACTIONS)


@pytest.mark.parametrize(
    "action",
    sorted(executor.ALLOWED_ACTIONS),
)
def test_execute_action_all_allowed_actions_build_cleanly(action):
    case = _ACTION_CASES[action]
    slug = case["slug"]
    fields = dict(case["fields"])
    args = executor._build_command_args(action, slug, fields)
    assert isinstance(args, list)
    assert args[:3] == [executor.sys.executable, "-m", "research_hub"]
    assert all(isinstance(part, str) for part in args)
    for token in case["subcommand"]:
        assert token in args, f"{action}: expected {token!r} in args, got {args!r}"
    if case["expect_slug"]:
        assert case["expect_slug"] in args, f"{action}: expected slug token {case['expect_slug']!r} in args, got {args!r}"


def test_events_broadcaster_delivers_to_subscribers():
    broadcaster = events.EventBroadcaster()
    queue = broadcaster.subscribe()
    payload = {"type": "vault_changed"}
    broadcaster.broadcast(payload)
    assert queue.get(timeout=1) == payload


def test_events_broadcaster_removes_dead_clients():
    broadcaster = events.EventBroadcaster()
    queue = broadcaster.subscribe()
    for index in range(100):
        queue.put_nowait({"i": index})
    broadcaster.broadcast({"overflow": True})
    assert queue not in broadcaster._clients


def test_vault_watcher_detects_mtime_change(fake_cfg):
    broadcaster = events.EventBroadcaster()
    queue = broadcaster.subscribe()
    watcher = events.VaultWatcher(fake_cfg, broadcaster, interval_sec=0.05)
    watcher.start()
    try:
        time.sleep(0.08)
        target = fake_cfg.research_hub_dir / "clusters.yaml"
        target.write_text("clusters: [changed]\n", encoding="utf-8")
        event = queue.get(timeout=1)
        assert event["type"] == "vault_changed"
    finally:
        watcher.stop()
        watcher.join(timeout=1)


def test_script_js_has_live_mode_detection():
    text = Path("src/research_hub/dashboard/script.js").read_text(encoding="utf-8")
    assert 'fetch("/healthz"' in text
    assert "LIVE_MODE" in text


def test_script_js_fallback_to_clipboard_when_no_server():
    text = Path("src/research_hub/dashboard/script.js").read_text(encoding="utf-8")
    assert "navigator.clipboard.writeText" in text


def test_cli_serve_dashboard_flag_accepts(monkeypatch):
    monkeypatch.setattr(cli, "get_config", lambda: SimpleNamespace())

    def fake_serve_dashboard(cfg, **kwargs):
        raise SystemExit(0)

    monkeypatch.setattr("research_hub.dashboard.http_server.serve_dashboard", fake_serve_dashboard)
    with pytest.raises(SystemExit):
        cli.main(["serve", "--dashboard", "--port", "0", "--no-browser", "--allow-external"])
