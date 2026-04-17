from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
import threading
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from research_hub.security import ValidationError
from tests.test_pipeline import _configure, _paper


def _create_cluster(cfg, slug: str, zotero_collection_key: str | None = None) -> None:
    lines = [
        "clusters:",
        f"  {slug}:",
        f"    name: {slug}",
        "    seed_keywords:",
        "      - llm",
        "      - agents",
        f"    obsidian_subfolder: {slug}",
    ]
    if zotero_collection_key:
        lines.append(f"    zotero_collection_key: {zotero_collection_key}")
    cfg.clusters_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _http_json(url: str, *, method: str = "GET", body: dict | None = None, headers: dict[str, str] | None = None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = Request(url, data=data, method=method)
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urlopen(request) as response:
            payload = response.read().decode("utf-8")
            return response.status, payload, dict(response.headers)
    except HTTPError as exc:
        payload = exc.read().decode("utf-8")
        return exc.code, payload, dict(exc.headers)


@pytest.fixture
def dashboard_server(tmp_path, monkeypatch):
    from http.server import ThreadingHTTPServer

    from research_hub.dashboard.events import EventBroadcaster
    from research_hub.dashboard.executor import ExecResult
    from research_hub.dashboard.http_server import DashboardHandler

    cfg = SimpleNamespace(
        root=tmp_path / "vault",
        raw=tmp_path / "vault" / "raw",
        research_hub_dir=tmp_path / "vault" / ".research_hub",
        hub=tmp_path / "vault" / "hub",
        clusters_file=tmp_path / "vault" / ".research_hub" / "clusters.yaml",
    )
    cfg.raw.mkdir(parents=True, exist_ok=True)
    cfg.research_hub_dir.mkdir(parents=True, exist_ok=True)
    cfg.hub.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        "research_hub.dashboard.http_server.execute_action",
        lambda action, slug, fields: ExecResult(
            ok=True,
            action=action,
            command=["research-hub", action],
            stdout="ok",
            stderr="",
            returncode=0,
            duration_ms=1,
        ),
    )

    DashboardHandler.cfg = cfg
    DashboardHandler.broadcaster = EventBroadcaster()
    DashboardHandler.csrf_token = "csrf-test-token"
    server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", DashboardHandler
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_pipeline_routes_to_cluster_collection_when_bound(tmp_path, monkeypatch):
    from research_hub import pipeline

    cfg = _configure(monkeypatch, tmp_path, default_collection="ABCD1234")
    _create_cluster(cfg, "cluster-a", "CLUSTER999")
    (cfg.root / "papers_input.json").write_text(
        json.dumps([_paper("Paper One", "paper-one", "10.1000/one")]),
        encoding="utf-8",
    )

    seen: dict[str, object] = {}

    class StubClient:
        def item_template(self, item_type: str):
            return {"itemType": item_type}

        def create_items(self, items):
            seen["collections"] = items[0]["collections"]
            return {"successful": {"0": {"key": "KEY1"}}}

    monkeypatch.setattr(pipeline, "get_client", lambda: StubClient())
    monkeypatch.setattr(
        pipeline,
        "check_duplicate",
        lambda zot, title, doi="", collection_key=None, **kwargs: (
            seen.setdefault("duplicate_collection", collection_key) and False
        ),
    )
    monkeypatch.setattr(pipeline, "add_note", lambda zot, key, content: True)
    monkeypatch.setattr(pipeline.time, "sleep", lambda seconds: None)

    result = pipeline.run_pipeline(cluster_slug="cluster-a")

    assert result == 0
    assert seen["duplicate_collection"] == "CLUSTER999"
    assert seen["collections"] == ["CLUSTER999"]
    log_text = (cfg.logs / "pipeline_log.txt").read_text(encoding="utf-8")
    assert "Routing to collection: CLUSTER999 (cluster=cluster-a)" in log_text


def test_pipeline_falls_back_to_default_when_cluster_unbound(tmp_path, monkeypatch):
    from research_hub import pipeline

    cfg = _configure(monkeypatch, tmp_path, default_collection="ABCD1234")
    _create_cluster(cfg, "cluster-a")
    (cfg.root / "papers_input.json").write_text(
        json.dumps([_paper("Paper One", "paper-one", "10.1000/one")]),
        encoding="utf-8",
    )

    seen: dict[str, object] = {}

    class StubClient:
        def item_template(self, item_type: str):
            return {"itemType": item_type}

        def create_items(self, items):
            seen["collections"] = items[0]["collections"]
            return {"successful": {"0": {"key": "KEY1"}}}

    monkeypatch.setattr(pipeline, "get_client", lambda: StubClient())
    monkeypatch.setattr(
        pipeline,
        "check_duplicate",
        lambda zot, title, doi="", collection_key=None, **kwargs: (
            seen.setdefault("duplicate_collection", collection_key) and False
        ),
    )
    monkeypatch.setattr(pipeline, "add_note", lambda zot, key, content: True)
    monkeypatch.setattr(pipeline.time, "sleep", lambda seconds: None)

    result = pipeline.run_pipeline(cluster_slug="cluster-a")

    assert result == 0
    assert seen["duplicate_collection"] is None
    assert seen["collections"] == ["ABCD1234"]
    log_text = (cfg.logs / "pipeline_log.txt").read_text(encoding="utf-8")
    assert "Routing to collection: ABCD1234 (cluster=cluster-a)" in log_text


def test_pipeline_falls_back_to_default_when_no_cluster_slug(tmp_path, monkeypatch):
    from research_hub import pipeline

    cfg = _configure(monkeypatch, tmp_path, default_collection="ABCD1234")
    (cfg.root / "papers_input.json").write_text(
        json.dumps([_paper("Paper One", "paper-one", "10.1000/one")]),
        encoding="utf-8",
    )

    seen: dict[str, object] = {}

    class StubClient:
        def item_template(self, item_type: str):
            return {"itemType": item_type}

        def create_items(self, items):
            seen["collections"] = items[0]["collections"]
            return {"successful": {"0": {"key": "KEY1"}}}

    monkeypatch.setattr(pipeline, "get_client", lambda: StubClient())
    monkeypatch.setattr(
        pipeline,
        "check_duplicate",
        lambda zot, title, doi="", collection_key=None, **kwargs: (
            seen.setdefault("duplicate_collection", collection_key) and False
        ),
    )
    monkeypatch.setattr(pipeline, "add_note", lambda zot, key, content: True)
    monkeypatch.setattr(pipeline.time, "sleep", lambda seconds: None)

    result = pipeline.run_pipeline()

    assert result == 0
    assert seen["duplicate_collection"] is None
    assert seen["collections"] == ["ABCD1234"]
    log_text = (cfg.logs / "pipeline_log.txt").read_text(encoding="utf-8")
    assert "Routing to collection: ABCD1234 (cluster=none)" in log_text


def test_validate_slug_accepts_normal_slug():
    from research_hub.security import validate_slug

    assert validate_slug("llm_agents-2025") == "llm_agents-2025"


def test_validate_slug_rejects_dotdot():
    from research_hub.security import validate_slug

    with pytest.raises(ValidationError):
        validate_slug("..")


def test_validate_slug_rejects_absolute_path():
    from research_hub.security import validate_slug

    with pytest.raises(ValidationError):
        validate_slug("/etc/passwd")


def test_validate_slug_rejects_uppercase():
    from research_hub.security import validate_slug

    with pytest.raises(ValidationError):
        validate_slug("Topic-A")


def test_validate_slug_rejects_long_input():
    from research_hub.security import validate_slug

    with pytest.raises(ValidationError):
        validate_slug("a" * 65)


def test_validate_slug_rejects_shell_metacharacters():
    from research_hub.security import validate_slug

    with pytest.raises(ValidationError):
        validate_slug("topic;rm-rf")


def test_validate_identifier_accepts_doi():
    from research_hub.security import validate_identifier

    assert validate_identifier("10.1234/example-doi") == "10.1234/example-doi"


def test_validate_identifier_accepts_arxiv_id():
    from research_hub.security import validate_identifier

    assert validate_identifier("2502.10978v1") == "2502.10978v1"


def test_validate_identifier_rejects_semicolon():
    from research_hub.security import validate_identifier

    with pytest.raises(ValidationError):
        validate_identifier("10.1234/x; rm -rf /")


def test_validate_identifier_rejects_newline():
    from research_hub.security import validate_identifier

    with pytest.raises(ValidationError):
        validate_identifier("10.1234/x\nsecond-line")


def test_safe_join_blocks_traversal(tmp_path):
    from research_hub.security import safe_join

    with pytest.raises(ValidationError):
        safe_join(tmp_path, "..")


def test_safe_join_blocks_absolute_segment(tmp_path):
    from research_hub.security import safe_join

    with pytest.raises(ValidationError):
        safe_join(tmp_path, "/etc")


def test_safe_join_allows_valid_subpath(tmp_path):
    from research_hub.security import safe_join

    assert safe_join(tmp_path, "cluster-a", "crystals") == Path(tmp_path).resolve() / "cluster-a" / "crystals"


def test_mcp_read_crystal_blocks_traversal_slug():
    from research_hub.mcp_server import read_crystal

    with pytest.raises(ValidationError):
        read_crystal.fn("../../etc", "what-is-this-field")


def test_mcp_add_paper_blocks_injection_identifier():
    from research_hub.mcp_server import add_paper

    with pytest.raises(ValidationError):
        add_paper.fn("10.1234/x; rm -rf /")


def test_api_exec_rejects_missing_csrf_token(dashboard_server):
    base_url, _handler = dashboard_server

    status, payload, _headers = _http_json(
        f"{base_url}/api/exec",
        method="POST",
        body={"action": "dashboard", "slug": None, "fields": {}},
        headers={"Content-Type": "application/json"},
    )

    assert status == 403
    assert json.loads(payload) == {"error": "csrf token mismatch"}


def test_api_exec_rejects_wrong_csrf_token(dashboard_server):
    base_url, _handler = dashboard_server

    status, payload, _headers = _http_json(
        f"{base_url}/api/exec",
        method="POST",
        body={"action": "dashboard", "slug": None, "fields": {}},
        headers={
            "Content-Type": "application/json",
            "X-CSRF-Token": "wrong-token",
        },
    )

    assert status == 403
    assert json.loads(payload) == {"error": "csrf token mismatch"}


def test_api_exec_accepts_correct_csrf_token(dashboard_server):
    base_url, handler = dashboard_server

    status, payload, _headers = _http_json(
        f"{base_url}/api/exec",
        method="POST",
        body={"action": "dashboard", "slug": None, "fields": {}},
        headers={
            "Content-Type": "application/json",
            "X-CSRF-Token": handler.csrf_token,
        },
    )

    assert status == 200
    assert json.loads(payload)["ok"] is True


def test_api_exec_rejects_evil_origin(dashboard_server):
    base_url, handler = dashboard_server

    status, payload, _headers = _http_json(
        f"{base_url}/api/exec",
        method="POST",
        body={"action": "dashboard", "slug": None, "fields": {}},
        headers={
            "Content-Type": "application/json",
            "X-CSRF-Token": handler.csrf_token,
            "Origin": "http://evil.com",
        },
    )

    assert status == 403
    assert json.loads(payload) == {"error": "origin not allowed"}


def test_api_exec_accepts_localhost_origin(dashboard_server):
    base_url, handler = dashboard_server
    port = base_url.rsplit(":", 1)[1]

    status, payload, _headers = _http_json(
        f"{base_url}/api/exec",
        method="POST",
        body={"action": "dashboard", "slug": None, "fields": {}},
        headers={
            "Content-Type": "application/json",
            "X-CSRF-Token": handler.csrf_token,
            "Origin": f"http://127.0.0.1:{port}",
        },
    )

    assert status == 200
    assert json.loads(payload)["ok"] is True


def test_html_contains_csrf_meta_tag():
    from research_hub.dashboard.render import render_dashboard

    ctx = SimpleNamespace(
        vault_root="/vault",
        generated_at="2026-04-16T12:00:00Z",
        persona="researcher",
        total_papers=0,
        total_clusters=0,
        total_unread=0,
        papers_this_week=0,
        clusters=[],
        papers=[],
    )

    html = render_dashboard(ctx, csrf_token="csrf-meta-token")

    assert '<meta name="csrf-token" content="csrf-meta-token">' in html


def test_executor_kills_process_on_timeout(monkeypatch):
    from research_hub.dashboard import executor

    seen: dict[str, subprocess.Popen[str]] = {}
    real_popen = subprocess.Popen

    def tracking_popen(*args, **kwargs):
        proc = real_popen(*args, **kwargs)
        seen["proc"] = proc
        return proc

    monkeypatch.setattr(executor, "_build_command_args", lambda action, slug, fields: [sys.executable, "-c", "import time; time.sleep(10)"])
    monkeypatch.setattr(executor.subprocess, "Popen", tracking_popen)

    result = executor.execute_action("dashboard", None, {}, timeout=1)

    assert result.ok is False
    assert result.returncode == -1
    assert "process killed" in result.stderr
    assert seen["proc"].poll() is not None


def test_atomic_write_creates_target_file(tmp_path):
    from research_hub.security import atomic_write_text

    target = tmp_path / "state.json"
    atomic_write_text(target, '{"ok": true}')

    assert target.read_text(encoding="utf-8") == '{"ok": true}'


def test_atomic_write_cleans_up_tmp_on_failure(tmp_path, monkeypatch):
    from research_hub import security

    target = tmp_path / "state.json"
    monkeypatch.setattr(security.os, "replace", lambda src, dst: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(RuntimeError, match="boom"):
        security.atomic_write_text(target, '{"ok": true}')

    assert not list(tmp_path.glob("state.json.tmp.*"))


def test_atomic_write_overwrites_existing(tmp_path):
    from research_hub.security import atomic_write_text

    target = tmp_path / "state.json"
    target.write_text("old", encoding="utf-8")

    atomic_write_text(target, "new")

    assert target.read_text(encoding="utf-8") == "new"


def test_event_broadcaster_drops_oldest_when_queue_is_full():
    from research_hub.dashboard.events import EventBroadcaster

    broadcaster = EventBroadcaster(maxsize=2)
    queue = broadcaster.subscribe()

    broadcaster.broadcast({"type": "one"})
    broadcaster.broadcast({"type": "two"})
    broadcaster.broadcast({"type": "three"})

    assert queue.get_nowait()["type"] == "two"
    assert queue.get_nowait()["type"] == "three"


def test_serve_warns_on_external_bind(monkeypatch, capsys):
    from research_hub import cli

    seen: dict[str, object] = {}

    monkeypatch.setattr(
        "research_hub.dashboard.http_server.serve_dashboard",
        lambda cfg, **kwargs: seen.setdefault("kwargs", kwargs),
    )
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: seen.setdefault("sleep", seconds))

    args = SimpleNamespace(
        dashboard=True,
        host="0.0.0.0",
        port=8765,
        allow_external=True,
        no_browser=True,
        yes=False,
    )

    assert cli._cmd_serve(args, cfg=SimpleNamespace()) == 0

    output = capsys.readouterr().out
    assert "DASHBOARD BOUND TO 0.0.0.0" in output
    assert "Continuing in 5 seconds" in output
    assert seen["sleep"] == 5


def test_serve_yes_skips_warning_delay(monkeypatch, capsys):
    from research_hub import cli

    seen: dict[str, object] = {}

    monkeypatch.setattr(
        "research_hub.dashboard.http_server.serve_dashboard",
        lambda cfg, **kwargs: seen.setdefault("kwargs", kwargs),
    )
    monkeypatch.setattr(
        cli.time,
        "sleep",
        lambda seconds: (_ for _ in ()).throw(AssertionError("sleep should be skipped")),
    )

    args = SimpleNamespace(
        dashboard=True,
        host="0.0.0.0",
        port=8765,
        allow_external=True,
        no_browser=True,
        yes=True,
    )

    assert cli._cmd_serve(args, cfg=SimpleNamespace()) == 0

    output = capsys.readouterr().out
    assert "Continuing immediately because --yes was passed." in output


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX perms only")
def test_init_chmods_config_to_600(tmp_path, monkeypatch):
    from research_hub.init_wizard import run_init

    config_dir = tmp_path / "cfg"
    monkeypatch.setattr(
        "research_hub.init_wizard.platformdirs.user_config_dir",
        lambda *args, **kwargs: str(config_dir),
    )
    monkeypatch.setattr("research_hub.notebooklm.cdp_launcher.find_chrome_binary", lambda: None)

    assert run_init(vault_root=str(tmp_path / "vault"), non_interactive=True, persona="analyst") == 0

    config_path = config_dir / "config.json"
    assert os.stat(config_path).st_mode & 0o777 == 0o600


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX perms only")
def test_init_chmods_research_hub_dir_to_700(tmp_path, monkeypatch):
    from research_hub import config as hub_config
    from research_hub.init_wizard import run_init

    config_dir = tmp_path / "cfg"
    monkeypatch.setattr(
        "research_hub.init_wizard.platformdirs.user_config_dir",
        lambda *args, **kwargs: str(config_dir),
    )
    monkeypatch.setattr(
        "research_hub.config.platformdirs.user_config_dir",
        lambda *args, **kwargs: str(config_dir),
    )
    monkeypatch.setattr("research_hub.notebooklm.cdp_launcher.find_chrome_binary", lambda: None)

    vault_root = tmp_path / "vault"
    assert run_init(vault_root=str(vault_root), non_interactive=True, persona="analyst") == 0
    hub_config._config = None
    hub_config._config_path = None
    cfg = hub_config.get_config()

    assert cfg.research_hub_dir == vault_root / ".research_hub"
    assert os.stat(cfg.research_hub_dir).st_mode & 0o777 == 0o700
