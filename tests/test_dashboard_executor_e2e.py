from __future__ import annotations

import http.client
import json
import queue
import socket
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest

from research_hub.clusters import ClusterRegistry
from research_hub.dashboard import events, executor, http_server
from research_hub.dashboard.types import ClusterCard, DashboardData
from research_hub.paper import read_labels

from tests._e2e_sandbox import _install_subprocess_network_guard, sandbox_cfg


@dataclass
class _FakeCompletedProcess:
    returncode: int = 0
    stdout: str = "ok"
    stderr: str = ""


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_subprocess_guard_records_even_caught_attempts(tmp_path, monkeypatch):
    attempts = _install_subprocess_network_guard(tmp_path, monkeypatch)
    # Emit audit events directly: exercise the child guard without invoking
    # DNS, opening a connection, sending a packet, or launching another helper.
    blocked_events = [
        "socket.getaddrinfo", "socket.connect", "socket.sendto", "subprocess.Popen",
    ]
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys\n"
            "assert sys._research_hub_e2e_offline\n"
            "from research_hub.doctor import check_nlm_chrome_orphans\n"
            "probe = check_nlm_chrome_orphans()\n"
            "assert probe.status == 'INFO'\n"
            "assert 'not checked' in probe.message\n"
            "try:\n"
            "    from patchright.sync_api import sync_playwright\n"
            "except ImportError:\n"
            "    pass\n"
            "else:\n"
            "    try:\n"
            "        sync_playwright()\n"
            "    except RuntimeError as exc:\n"
            "        assert 'not checked' in str(exc)\n"
            "    else:\n"
            "        raise AssertionError('browser probe was not stubbed')\n"
            f"for event in {blocked_events!r}:\n"
            "    try:\n"
            "        sys.audit(event)\n"
            "    except RuntimeError:\n"
            "        pass\n"
            "    else:\n"
            "        raise AssertionError(event + ' was not blocked')\n",
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert child.returncode == 0, child.stderr
    assert attempts.read_text(encoding="utf-8").splitlines() == blocked_events


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


class _ClosingBroadcaster(events.EventBroadcaster):
    """Only teardown interrupts reads; normal events use the real broadcaster."""
    _stop = object()

    def subscribe(self):
        subscription = super().subscribe()
        original_get = subscription.get

        def get(*args, **kwargs):
            event = original_get(*args, **kwargs)
            if event is self._stop:
                raise ConnectionResetError("offline test stream teardown")
            return event

        subscription.get = get
        return subscription

    def stop_subscribers(self):
        with self._lock:
            subscriptions = list(self._clients)
        for subscription in subscriptions:
            subscription.put_nowait(self._stop)


class _OwnedDashboardHandler(http_server.DashboardHandler):
    """Close the fixture's keep-alive connection once teardown has started."""
    def handle_one_request(self):
        super().handle_one_request()
        if self.server.stopping.is_set():
            self.close_connection = True


class _OwnedHTTPServer(http_server.ThreadingHTTPServer):
    """Track only this fixture's accepted sockets and worker threads."""
    def __init__(self, *args, **kwargs):
        self.owned_threads = []
        self.owned_sockets = []
        self.stopping = threading.Event()
        super().__init__(*args, **kwargs)

    @property
    def port(self):
        return self.server_address[1]

    def process_request(self, request, client_address):
        self.owned_sockets.append(request)
        thread = threading.Thread(target=self.process_request_thread,
                                  args=(request, client_address), daemon=True)
        self.owned_threads.append(thread)
        thread.start()


def _join_owned_threads(threads, timeout):
    deadline = time.monotonic() + timeout
    pending = list(threads)
    while pending:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        per_thread = min(0.05, remaining / len(pending))
        for owned_thread in pending:
            owned_thread.join(timeout=per_thread)
        pending = [owned_thread for owned_thread in pending if owned_thread.is_alive()]


@contextmanager
def _live_server_context(sandbox_cfg, monkeypatch):
    monkeypatch.setattr(http_server, "collect_dashboard_data", lambda cfg: _make_dashboard_data())
    monkeypatch.setattr(http_server, "render_dashboard_from_config", lambda cfg, csrf_token="": "<html></html>")
    broadcaster = _ClosingBroadcaster()
    monkeypatch.setattr(http_server.DashboardHandler, "cfg", sandbox_cfg)
    monkeypatch.setattr(http_server.DashboardHandler, "broadcaster", broadcaster, raising=False)
    monkeypatch.setattr(http_server.DashboardHandler, "csrf_token", "")
    server = _OwnedHTTPServer(("127.0.0.1", 0), _OwnedDashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    server.owned_threads.append(thread)
    thread.start()
    try:
        yield server
    finally:
        server.stopping.set()
        server.shutdown()
        # Wake queue.get(30) and close keep-alive sockets. Neither the stop
        # sentinel nor socket shutdown is part of the action/event assertion.
        broadcaster.stop_subscribers()
        for connection in server.owned_sockets:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass  # A completed request may already have closed its socket.
            connection.close()
        server.server_close()
        _join_owned_threads(server.owned_threads, timeout=3)
        assert not [t.name for t in server.owned_threads if t.is_alive()], "Fixture threads leaked"
        with broadcaster._lock:
            assert not broadcaster._clients, "Fixture SSE subscriptions leaked"


@pytest.fixture
def live_server(sandbox_cfg, monkeypatch):
    with _live_server_context(sandbox_cfg, monkeypatch) as server:
        yield server


def _listen_for_sse(server) -> tuple[queue.Queue, threading.Thread]:
    out: queue.Queue = queue.Queue()
    ready = threading.Event()

    def worker() -> None:
        conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=10)
        response = None
        event_name = "message"
        data_lines: list[str] = []
        try:
            conn.request("GET", "/api/events")
            response = conn.getresponse()
            while True:
                line = response.fp.readline()
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
                        if event_name == "hello":
                            ready.set()
                        if event_name == "state-change":
                            break
                    event_name = "message"
                    data_lines = []
        except OSError as exc:
            if not server.stopping.is_set():
                out.put(("reader-error", {"message": str(exc)}))
        finally:
            if response is not None:
                response.close()
            conn.close()

    thread = threading.Thread(target=worker, daemon=True)
    server.owned_threads.append(thread)
    thread.start()
    assert ready.wait(timeout=5), "SSE did not complete the real hello handshake"
    return out, thread


def test_sse_fixture_teardown_joins_threads_without_state_change(sandbox_cfg, monkeypatch):
    # Exercise assertion-failure cleanup while both the real reader and real
    # handler are waiting. No synthetic event can satisfy the action test.
    with pytest.raises(AssertionError, match="simulated action assertion"):
        with _live_server_context(sandbox_cfg, monkeypatch) as server:
            stream, reader = _listen_for_sse(server)
            assert stream.get(timeout=1)[0] == "hello"
            assert reader.is_alive()
            raise AssertionError("simulated action assertion")
    assert not any(thread.is_alive() for thread in server.owned_threads)


def test_fixture_join_gives_later_dependency_time_to_finish():
    class _JoinProbe:
        def __init__(self, *, completes_on_join=False):
            self.alive = True
            self.completes_on_join = completes_on_join

        def join(self, timeout):
            if self.completes_on_join and timeout > 0:
                self.alive = False
            else:
                time.sleep(timeout)

        def is_alive(self):
            return self.alive

    waiting_client = _JoinProbe()
    request_handler = _JoinProbe(completes_on_join=True)

    _join_owned_threads([waiting_client, request_handler], timeout=0.02)

    assert not request_handler.is_alive(), "later fixture thread received no join time"


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
@pytest.mark.timeout(90)
def test_e2e_category_a_real_cli(action, slug, fields, assertion, sandbox_cfg):
    if action == "delete":
        slug = "beta"
    result = executor.execute_action(action, slug, dict(fields), timeout=60)
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


def test_e2e_merge_moves_papers_and_tombstones_source(sandbox_cfg):
    result = executor.execute_action("merge", "alpha", {"target": "beta"}, timeout=30)
    registry = ClusterRegistry(sandbox_cfg.clusters_file)
    assert result.ok is True, result.stderr
    # merge now tombstones the source (status=merged + merged_into) instead of
    # deleting it, so re-ingest on the source seed redirects to the target.
    alpha = registry.get("alpha")
    assert alpha is not None and alpha.status == "merged" and alpha.merged_into == "beta"
    assert "alpha" not in {c.slug for c in registry.list()}  # hidden from active set
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
        live_server.port,
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

    thread.join(timeout=2)
    assert not thread.is_alive(), "SSE reader did not stop after state-change"


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
        live_server.port,
        "/api/exec",
        {"action": "rename", "slug": "alpha", "fields": {"new_name": "bad"}},
    )
    assert status == 200
    assert payload["ok"] is False
    # v0.91.0 W8 G3 P2 #16: raw subprocess stderr must NOT reach the
    # browser (it can leak abs paths / partial config / stack traces).
    # The browser gets only a generic message + correlation id; the
    # full stderr is logged server-side under that id.
    assert "stderr" not in payload
    # stdout is intentionally retained (v0.62 stdout drawer); only stderr
    # is the G3 #16 leak surface. Here the failed command produced no
    # stdout, but we assert the secure stderr behaviour + no raw leak.
    assert payload["error"].startswith("execution failed (server log error_id=")
    assert "rename failed" not in str(payload)


def test_e2e_timeout_handling(live_server, monkeypatch):
    def fake_run(args, **kwargs):
        time.sleep(0.1)
        raise executor.subprocess.TimeoutExpired(cmd=args, timeout=kwargs["timeout"])

    monkeypatch.setattr(executor.subprocess, "run", fake_run)
    started = time.monotonic()
    status, payload = _post_json(
        live_server.port,
        "/api/exec",
        {"action": "dashboard", "fields": {}, "timeout": 1},
    )
    elapsed = time.monotonic() - started
    assert elapsed < 10
    assert status == 200
    assert payload["ok"] is False
    assert payload["returncode"] == -1
    assert payload.get("error") == "timeout"
    # v0.91.1: W8 G3 #16 strips raw stderr from the browser response on
    # EVERY branch (incl. timeout). The user-facing signal is the
    # generic `error: "timeout"`; the raw "timeout after Ns" text is no
    # longer leaked into the payload (it stays server-side). This test
    # previously asserted the leaky behaviour and was missed in the W8
    # commit because the dev tree's e2e suite was icacls-polluted.
    assert "stderr" not in payload
