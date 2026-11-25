"""Resilience tests for MCP stdio protocol safety, config hot-reload, Zotero reconnect, and NLM cookie auto-refresh."""

from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import urllib.error

import pytest


def test_stdio_protocol_guard_keeps_binary_buffer_and_redirects_stray_stdout():
    from research_hub.mcp_server import _StdioProtocolGuard

    raw_bytes = io.BytesIO()
    proto_stdout = io.TextIOWrapper(raw_bytes, encoding="utf-8")
    err_buf = io.StringIO()
    guard = _StdioProtocolGuard(proto_stdout, err_buf)

    assert guard.buffer is raw_bytes
    assert guard.writable() is True
    assert guard.closed is False
    assert guard.errors == "strict"
    assert guard.isatty() is False
    with pytest.raises(io.UnsupportedOperation):
        guard.fileno()

    guard.write("[ZoteroDualClient] Local API lost connection\n")
    guard.writelines(["line-two\n"])
    guard.flush()

    assert err_buf.getvalue() == "[ZoteroDualClient] Local API lost connection\nline-two\n"
    assert raw_bytes.getvalue() == b""

    # Verify redirect_stdout captures and restores _StdioProtocolGuard cleanly.
    orig = sys.stdout
    sys.stdout = guard  # type: ignore[assignment]
    try:
        captured = io.StringIO()
        with redirect_stdout(captured):
            print("@article{ok}")
        assert sys.stdout is guard
        assert captured.getvalue().strip() == "@article{ok}"
        print("stray-after-restore")
    finally:
        sys.stdout = orig

    assert "stray-after-restore" in err_buf.getvalue()
    assert raw_bytes.getvalue() == b""


def test_mcp_main_wraps_stdout_only_on_stdio_and_enforces_loopback_http(monkeypatch):
    from research_hub import mcp_server

    seen = []

    class DummyMCP:
        def run(self, **kwargs):
            seen.append((kwargs, type(sys.stdout).__name__))

    monkeypatch.setattr(mcp_server, "mcp", DummyMCP())
    monkeypatch.setattr(mcp_server, "FastMCP", object)

    orig_stdout = sys.stdout
    try:
        mcp_server.main(transport="stdio")
        assert seen[-1][0] == {"transport": "stdio"}
        if hasattr(orig_stdout, "buffer"):
            assert seen[-1][1] == "_StdioProtocolGuard"
        assert sys.stdout is orig_stdout

        # Also verifies sys.stdout restoration even when mcp.run raises.
        class BoomMCP:
            def run(self, **kwargs):
                raise RuntimeError("boom")

        monkeypatch.setattr(mcp_server, "mcp", BoomMCP())
        with pytest.raises(RuntimeError, match="boom"):
            mcp_server.main(transport="stdio")
        assert sys.stdout is orig_stdout

        monkeypatch.setattr(mcp_server, "mcp", DummyMCP())
        mcp_server.main(transport="streamable-http", host="127.0.0.1", port=9123)
        assert seen[-1] == ({"transport": "streamable-http", "host": "127.0.0.1", "port": 9123}, type(orig_stdout).__name__)

        with pytest.raises(ValueError, match="loopback-only"):
            mcp_server.main(transport="streamable-http", host="0.0.0.0", port=9123)
    finally:
        sys.stdout = orig_stdout


def test_mcp_main_missing_fastmcp_prints_to_stderr(monkeypatch, capsys):
    from research_hub import mcp_server

    monkeypatch.setattr(mcp_server, "FastMCP", None)
    with pytest.raises(SystemExit) as exc:
        mcp_server.main()
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "fastmcp" in captured.err.lower()


def test_cli_mcp_transport_validation(tmp_path, monkeypatch):
    from research_hub import cli

    with pytest.raises(SystemExit):
        cli.main(["serve", "--mcp-transport", "streamable-http", "--workspace", "--root", str(tmp_path)])
    with pytest.raises(SystemExit):
        cli.main(["serve", "--mcp-transport", "sse", "--dashboard"])

    monkeypatch.setenv("RESEARCH_HUB_ROOT", str(tmp_path))
    with pytest.raises(SystemExit, match="loopback-only"):
        cli.main(["serve", "--mcp-transport", "streamable-http", "--host", "0.0.0.0", "--allow-external"])


def test_config_hot_reload_and_secret_decryption(tmp_path, monkeypatch):
    from research_hub import config as hub_config
    from research_hub.security.secret_box import encrypt

    monkeypatch.delenv("ZOTERO_API_KEY", raising=False)
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    hub_config.invalidate_config_cache()

    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir(parents=True)
    kb = tmp_path / "kb"
    kb.mkdir()
    cfg_path = cfg_dir / "config.json"
    monkeypatch.setenv("RESEARCH_HUB_CONFIG", str(cfg_path))

    enc_zot = encrypt("zot-secret-123", cfg_dir)
    enc_s2 = encrypt("s2-secret-456", cfg_dir)
    cfg_path.write_text(
        json.dumps(
            {
                "knowledge_base": {"root": str(kb)},
                "zotero": {"library_id": "111", "api_key": enc_zot},
                "search": {"semantic_scholar_api_key": enc_s2},
            }
        ),
        encoding="utf-8",
    )

    first = hub_config.get_config()
    assert first.zotero_library_id == "111"
    assert first.zotero_api_key == "zot-secret-123"
    assert first.s2_api_key == "s2-secret-456"

    # Update config on disk; mtime_ns/size change must invalidate cache automatically.
    enc_s2_new = encrypt("s2-secret-rotated-7890", cfg_dir)
    cfg_path.write_text(
        json.dumps(
            {
                "knowledge_base": {"root": str(kb)},
                "zotero": {"library_id": "2222", "api_key": enc_zot},
                "search": {"semantic_scholar_api_key": enc_s2_new},
            }
        ),
        encoding="utf-8",
    )

    second = hub_config.get_config()
    assert second is not first
    assert second.zotero_library_id == "2222"
    assert second.s2_api_key == "s2-secret-rotated-7890"

    # Corrupted secret_box key must not crash get_config() / doctor / where; returns None safely.
    key_file = cfg_dir / ".secret_box.key"
    if key_file.exists():
        from cryptography.fernet import Fernet

        key_file.write_bytes(Fernet.generate_key())
        hub_config.invalidate_config_cache()
        degraded = hub_config.get_config()
        assert degraded.s2_api_key is None
        assert degraded.zotero_api_key is None

    hub_config.invalidate_config_cache()


def test_search_fallback_forwards_configured_s2_key_when_env_unset(tmp_path, monkeypatch):
    from research_hub import config as hub_config
    from research_hub.search import fallback

    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    monkeypatch.setattr(hub_config, "_resolve_config_path", lambda: tmp_path / "config.json")
    monkeypatch.setattr(hub_config, "get_config", lambda: SimpleNamespace(s2_api_key="cfg-s2-key"))

    captured_keys: list[str | None] = []

    class FakeS2(fallback.SemanticScholarClient):
        def __init__(self, api_key: str | None = None):
            super().__init__(api_key=api_key)
            captured_keys.append(self.api_key)

        def search(self, query, limit=20, year_from=None, year_to=None):
            return []

    monkeypatch.setattr(fallback, "SemanticScholarClient", FakeS2)
    monkeypatch.setitem(fallback._BACKEND_REGISTRY, "semantic-scholar", FakeS2)
    fallback.search_papers("test query", limit=2, backends=("semantic-scholar",))
    assert captured_keys == ["cfg-s2-key"]

    # Env var wins over config key.
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "env-s2-key")
    fallback.search_papers("test query", limit=2, backends=("semantic-scholar",))
    assert captured_keys == ["cfg-s2-key", "env-s2-key"]


def test_zotero_dual_client_logs_stderr_and_reconnects_local_api(monkeypatch, capsys):
    from research_hub.zotero import client as zclient

    monkeypatch.setattr(zclient, "_load_credentials", lambda: ("web-key", "54321", "user"))
    local_state = {"up": True, "calls": 0}
    now = [100.0]
    monkeypatch.setattr(zclient.time, "monotonic", lambda: now[0])

    class FakeZotero:
        def __init__(self, lib_id, lib_type, api_key=None, *, local=False):
            self.local = local

        def top(self, limit=1):
            if self.local and not local_state["up"]:
                raise urllib.error.URLError("Connection refused")
            return [{"key": "TOP"}]

        def item(self, key):
            if self.local:
                local_state["calls"] += 1
                if key == "BAD-KEY":
                    raise KeyError("item missing")
                if not local_state["up"]:
                    raise urllib.error.URLError("Connection refused")
                return {"source": "local", "key": key}
            return {"source": "web", "key": key}

    import pyzotero.zotero as pyz

    monkeypatch.setattr(pyz, "Zotero", FakeZotero)
    monkeypatch.setattr(zclient, "check_local_api", lambda timeout=2, library_id=None: local_state["up"])

    # Minimal __new__ instance without local_available attr still works safely via getattr guards.
    minimal = zclient.ZoteroDualClient.__new__(zclient.ZoteroDualClient)
    minimal.web = FakeZotero("54321", "user", "web-key")
    minimal._local_retry_after = 999.0
    assert minimal.get_item("M1")["source"] == "web"

    dual = zclient.ZoteroDualClient.__new__(zclient.ZoteroDualClient)
    dual.user_id = "54321"
    dual.api_key = "web-key"
    dual.lib_type = "user"
    dual._local_retry_after = 0.0
    dual.web = FakeZotero("54321", "user", "web-key")
    dual.local = FakeZotero("54321", "user", local=True)
    dual.local_available = True
    assert dual.get_item("A1")["source"] == "local"

    # Non-connection exceptions must still propagate rather than latching local_available=False.
    with pytest.raises(KeyError):
        dual.get_item("BAD-KEY")
    assert dual.local_available is True

    # Drop local API: logs go to stderr (never stdout!), falls back to Web API.
    local_state["up"] = False
    assert dual.get_item("A2")["source"] == "web"
    assert dual.local_available is False

    # Failed probe after cooldown keeps cooldown extending without crashing.
    now[0] += dual._LOCAL_RETRY_COOLDOWN_SEC + 1.0
    assert dual.get_item("A2b")["source"] == "web"
    assert dual.local_available is False

    # Recover local API before cooldown expires: stays on Web API without probing every call.
    local_state["up"] = True
    assert dual.get_item("A3")["source"] == "web"

    # Advance clock past cooldown: automatically reconnects to Local API.
    now[0] += dual._LOCAL_RETRY_COOLDOWN_SEC + 1.0
    assert dual.get_item("A4")["source"] == "local"
    assert dual.local_available is True

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "[ZoteroDualClient]" in captured.err
    assert "Reconnected Local API" in captured.err


def test_ensure_session_health_auto_refreshes_and_handles_negative_cases(tmp_path, monkeypatch):
    from research_hub.errors import RequiresAuthRefresh
    from research_hub.notebooklm import auth as nlm_auth
    from research_hub.notebooklm import keepalive as nlm_keepalive

    missing = tmp_path / "missing-state.json"
    assert nlm_auth.ensure_session_health(missing) == {
        "ok": False,
        "reason": "state.json missing",
        "expires_at": None,
        "refreshed": False,
    }

    state_file = tmp_path / "state.json"
    state_file.write_text('{"cookies": [{"name": "SID", "value": "x"}]}', encoding="utf-8")

    # Happy recovery via refresh_and_persist_session.
    probes = [{"ok": False, "reason": "auth error: expired", "expires_at": None}, {"ok": True, "reason": "ok", "expires_at": None}]
    refreshed = []
    monkeypatch.setattr(nlm_auth, "check_session_health", lambda _path: probes.pop(0))
    monkeypatch.setattr(
        nlm_keepalive,
        "refresh_and_persist_session",
        lambda path: refreshed.append(path) or SimpleNamespace(ok=True, reason="ok"),
    )

    health = nlm_auth.ensure_session_health(state_file)
    assert health == {"ok": True, "reason": "ok", "expires_at": None, "refreshed": True}
    assert refreshed == [state_file]

    # auto_refresh=False skips keepalive.
    monkeypatch.setattr(nlm_auth, "check_session_health", lambda _path: {"ok": False, "reason": "expired", "expires_at": None})
    no_ref = nlm_auth.ensure_session_health(state_file, auto_refresh=False)
    assert no_ref["ok"] is False and no_ref["refreshed"] is False
    assert len(refreshed) == 1

    # Failed keepalive leaves ok=False and raises RequiresAuthRefresh in require_session_health.
    monkeypatch.setattr(
        nlm_keepalive,
        "refresh_and_persist_session",
        lambda _path: SimpleNamespace(ok=False, reason="revoked"),
    )
    with pytest.raises(RequiresAuthRefresh):
        nlm_auth.require_session_health(state_file)

    # Re-probe still returning ok=False even after keepalive ok also raises RequiresAuthRefresh.
    monkeypatch.setattr(
        nlm_keepalive,
        "refresh_and_persist_session",
        lambda _path: SimpleNamespace(ok=True, reason="ok"),
    )
    res_still_bad = nlm_auth.ensure_session_health(state_file)
    assert res_still_bad == {"ok": False, "reason": "expired", "expires_at": None, "refreshed": False}
