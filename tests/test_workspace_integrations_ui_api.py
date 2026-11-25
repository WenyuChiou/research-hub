"""Unit and loopback HTTP tests for workspace opt-in local integrations and markdown export."""

from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from research_hub.config import get_config
from research_hub.security.secret_box import decrypt, is_encrypted
from research_hub.workspace.core import Workspace
from research_hub.workspace.integrations import LocalIntegrationsManager
from research_hub.workspace.server import WorkspaceServer


def _get_json(url: str) -> tuple[int, dict]:
    try:
        with urlopen(url, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _fetch_csrf(base: str) -> str:
    with urlopen(f"{base}/app/", timeout=5) as resp:
        html = resp.read().decode("utf-8")
    m = re.search(r'<meta name="research-hub-csrf-token" content="([^"]+)"', html)
    assert m, "CSRF meta tag not found in /app/ response"
    return m.group(1)


def _post_json(url: str, payload: dict, *, csrf: str | None = None, origin: str | None = None) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if csrf is not None:
        headers["X-CSRF-Token"] = csrf
    if origin is not None:
        headers["Origin"] = origin
    req = Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_integrations_disabled_by_default(tmp_path: Path):
    ws = Workspace(tmp_path / "ws")
    server = WorkspaceServer(ws.root, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        csrf = _fetch_csrf(base)

        code, body = _get_json(f"{base}/api/v1/workspace")
        assert code == 200
        assert "local_integrations" not in body["capabilities"]

        code, body = _get_json(f"{base}/api/v1/integrations/status")
        assert code == 403 and body["code"] == "integrations_unavailable"

        for endpoint, payload in (
            ("/api/v1/integrations/credentials", {"zotero_library_id": "123"}),
            ("/api/v1/integrations/zotero/check", {}),
            ("/api/v1/integrations/notebooklm/check", {}),
            ("/api/v1/integrations/notebooklm/login", {"mode": "browser_cookies"}),
        ):
            code, body = _post_json(f"{base}{endpoint}", payload, csrf=csrf, origin=base)
            assert code == 403 and body["code"] == "integrations_unavailable"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_credentials_save_encrypts_secrets_and_never_echoes(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("ZOTERO_API_KEY", raising=False)
    monkeypatch.delenv("ZOTERO_LIBRARY_ID", raising=False)
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    monkeypatch.delenv("UNPAYWALL_EMAIL", raising=False)

    cfg_path = tmp_path / "cfg" / "config.json"
    monkeypatch.setenv("RESEARCH_HUB_CONFIG", str(cfg_path))
    ws = Workspace(tmp_path / "ws")

    server = WorkspaceServer(ws.root, port=0, integrations_config=cfg_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        csrf = _fetch_csrf(base)

        # Missing CSRF token -> 403 forbidden
        code, body = _post_json(f"{base}/api/v1/integrations/credentials", {"zotero_library_id": "12345"})
        assert code == 403 and body["code"] == "forbidden"

        # Invalid inputs rejected
        code, body = _post_json(
            f"{base}/api/v1/integrations/credentials",
            {"zotero_library_id": "000"},
            csrf=csrf,
            origin=base,
        )
        assert code == 400 and body["code"] == "invalid_request"

        code, body = _post_json(
            f"{base}/api/v1/integrations/credentials",
            {"unpaywall_email": "not-an-email"},
            csrf=csrf,
            origin=base,
        )
        assert code == 400 and body["code"] == "invalid_request"

        code, body = _post_json(
            f"{base}/api/v1/integrations/credentials",
            {"zotero_api_key": "bad key with space"},
            csrf=csrf,
            origin=base,
        )
        assert code == 400 and body["code"] == "invalid_request"

        raw_zot_secret = "zot-super-secret-value-991"
        raw_s2_secret = "s2-super-secret-value-882"
        raw_email = "researcher@example.edu"

        code, body = _post_json(
            f"{base}/api/v1/integrations/credentials",
            {
                "zotero_library_id": "007654",
                "zotero_library_type": "group",
                "zotero_api_key": raw_zot_secret,
                "unpaywall_email": raw_email,
                "s2_api_key": raw_s2_secret,
            },
            csrf=csrf,
            origin=base,
        )
        assert code == 200 and body["saved"] is True
        creds = body["credentials"]
        assert creds["zotero_configured"] is True
        assert creds["zotero_api_key_present"] is True
        assert creds["zotero_api_key_encrypted"] is True
        assert creds["zotero_library_id"] == "7654"
        assert creds["zotero_library_type"] == "group"
        assert creds["unpaywall_email_present"] is True
        assert creds["s2_api_key_present"] is True
        assert creds["s2_api_key_encrypted"] is True

        # Ensure raw secrets/email never appear in HTTP responses
        _, status_body = _get_json(f"{base}/api/v1/integrations/status")
        _, ws_body = _get_json(f"{base}/api/v1/workspace")
        dumped = json.dumps({"save": body, "status": status_body, "ws": ws_body})
        assert raw_zot_secret not in dumped
        assert raw_s2_secret not in dumped
        assert raw_email not in dumped

        # Verify on-disk encryption & get_config() hot-reload
        saved_json = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert is_encrypted(saved_json["zotero"]["api_key"])
        assert is_encrypted(saved_json["search"]["semantic_scholar_api_key"])
        assert decrypt(saved_json["zotero"]["api_key"], cfg_path.parent) == raw_zot_secret
        assert decrypt(saved_json["search"]["semantic_scholar_api_key"], cfg_path.parent) == raw_s2_secret

        reloaded = get_config()
        assert reloaded.zotero_library_id == "7654"
        assert reloaded.zotero_library_type == "group"
        assert reloaded.zotero_api_key == raw_zot_secret
        assert reloaded.s2_api_key == raw_s2_secret
        assert reloaded.unpaywall_email == raw_email

        # Verify env ZOTERO_LIBRARY_TYPE fallback when not in config
        monkeypatch.setenv("ZOTERO_LIBRARY_TYPE", "group")
        clear_type_mgr = LocalIntegrationsManager(tmp_path / "env_only.json")
        assert clear_type_mgr.capability()["zotero_library_type"] == "group"

        # Refuse secret saves when cryptography package is unavailable
        import research_hub.workspace.integrations as integ_mod

        monkeypatch.setattr(integ_mod, "_HAS_CRYPTO", False)
        with pytest.raises(Exception) as crypto_exc:
            clear_type_mgr.save_credentials({"zotero_api_key": "must-not-save-plain"})
        assert "cryptography" in str(crypto_exc.value).lower()
        assert not (tmp_path / "env_only.json").exists()

        # Clear keys explicitly
        code, body = _post_json(
            f"{base}/api/v1/integrations/credentials",
            {"clear_zotero_api_key": True, "clear_s2_api_key": True},
            csrf=csrf,
            origin=base,
        )
        assert code == 200
        assert body["credentials"]["zotero_api_key_present"] is False
        assert body["credentials"]["s2_api_key_present"] is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_zotero_and_notebooklm_probes_and_login_modes(tmp_path: Path, monkeypatch):
    kb_root = tmp_path / "kb"
    (kb_root / ".research_hub").mkdir(parents=True)
    cfg_path = tmp_path / "cfg" / "config.json"
    cfg_path.parent.mkdir(parents=True)
    cfg_path.write_text(
        json.dumps({"knowledge_base": {"root": str(kb_root)}, "zotero": {"library_id": "12345"}}),
        encoding="utf-8",
    )

    mgr = LocalIntegrationsManager(cfg_path)
    # Save encrypted Zotero key so check_zotero uses web API
    mgr.save_credentials({"zotero_api_key": "zot-secret-test"})

    # Mock local API down & pyzotero ok
    import research_hub.workspace.integrations as integ_mod

    monkeypatch.setattr(integ_mod, "urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError("closed")))

    class _FakeZot:
        def __init__(self, lib_id, lib_type, api_key):
            assert lib_id == "12345"
            assert lib_type == "user"
            assert api_key == "zot-secret-test"

        def top(self, limit=1):
            return [{"key": "ABC"}]

    import pyzotero.zotero as pyzot_mod

    monkeypatch.setattr(pyzot_mod, "Zotero", _FakeZot)
    zot_res = mgr.check_zotero()
    assert zot_res["ok"] is True
    assert zot_res["probe"]["status"] == "connected_web"
    assert "zot-secret-test" not in json.dumps(zot_res)

    # NotebookLM check when state file missing
    import research_hub.notebooklm.auth as nlm_auth

    monkeypatch.setattr(
        nlm_auth,
        "ensure_session_health",
        lambda sf, auto_refresh=True: {"ok": False, "refreshed": False},
    )
    nlm_res = mgr.check_notebooklm()
    assert nlm_res["probe"]["status"] == "missing"

    # import_state rejects relative path and missing cookies
    with pytest.raises(Exception) as rel_exc:
        mgr.start_notebooklm_login({"mode": "import_state", "state_path": "relative/state.json"})
    assert "absolute" in str(rel_exc.value).lower()

    bad_state = tmp_path / "bad_state.json"
    bad_state.write_text(json.dumps({"cookies": []}), encoding="utf-8")
    with pytest.raises(Exception) as bad_exc:
        mgr.start_notebooklm_login({"mode": "import_state", "state_path": str(bad_state)})
    assert "cookies" in str(bad_exc.value).lower()

    # Valid import_state creates working state.json
    good_state = tmp_path / "good_state.json"
    good_state.write_text(
        json.dumps({"cookies": [{"name": "SID", "value": "v", "domain": ".google.com"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        nlm_auth,
        "ensure_session_health",
        lambda sf, auto_refresh=True: {"ok": True, "refreshed": True},
    )
    imp_res = mgr.start_notebooklm_login({"mode": "import_state", "state_path": str(good_state)})
    assert imp_res["ok"] is True
    assert imp_res["probe"]["status"] == "authenticated"
    assert imp_res["probe"]["refreshed"] is True

    # Invalid/expired import_state must NOT overwrite working state_file
    expired_state = tmp_path / "expired_state.json"
    expired_state.write_text(
        json.dumps({"cookies": [{"name": "SID", "value": "expired", "domain": ".google.com"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        nlm_auth,
        "ensure_session_health",
        lambda sf, auto_refresh=True: {"ok": False, "refreshed": False},
    )
    exp_res = mgr.start_notebooklm_login({"mode": "import_state", "state_path": str(expired_state)})
    assert exp_res["ok"] is False and exp_res["code"] == "auth_invalid"
    active_state = json.loads(nlm_auth.default_state_file(kb_root / ".research_hub").read_text(encoding="utf-8"))
    assert active_state["cookies"][0]["value"] == "v"

    # Re-enable ok health check for browser_cookies
    monkeypatch.setattr(
        nlm_auth,
        "ensure_session_health",
        lambda sf, auto_refresh=True: {"ok": True, "refreshed": True},
    )

    # browser_cookies mode
    monkeypatch.setattr(nlm_auth, "login_from_browser", lambda sf, browser=None: 0)
    bc_res = mgr.start_notebooklm_login({"mode": "browser_cookies", "browser": "chrome"})
    assert bc_res["ok"] is True and bc_res["probe"]["status"] == "authenticated"

    # browser_window mode starts background thread & reports succeeded
    monkeypatch.setattr(nlm_auth, "login_nlm", lambda *a, **k: 0)
    monkeypatch.setattr(nlm_auth, "check_session_health", lambda *a, **k: {"ok": True})
    bw_res = mgr.start_notebooklm_login({"mode": "browser_window"})
    assert bw_res["ok"] is True and bw_res["login"]["mode"] == "browser_window"
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        st = mgr.status()
        if st["login_job"]["status"] in {"succeeded", "failed"}:
            break
        time.sleep(0.02)
    assert mgr.status()["login_job"]["status"] == "succeeded"


def test_http_native_summary_markdown_endpoint(tmp_path: Path, monkeypatch):
    ws = Workspace(tmp_path / "ws")

    server = WorkspaceServer(ws.root, port=0)
    monkeypatch.setattr(
        server,
        "_call",
        lambda resource, op, payload: (
            {"ok": True, "markdown": "# Paper\n\n## Why\nBecause [supported]", "status": "current"}
            if resource == "project" and op == "native-summary-export" and payload.get("source_record_id") == "rec1"
            else {"ok": False, "code": "missing", "error": "No native summary", "markdown": None}
        ),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        code, body = _get_json(f"{base}/api/v1/projects/p/native-summary/markdown?source_record_id=rec1")
        assert code == 200 and body["ok"] is True and "## Why" in body["markdown"]

        code, body = _get_json(f"{base}/api/v1/projects/p/native-summary/markdown")
        assert code == 400 and body["code"] == "invalid_request"

        code, body = _get_json(f"{base}/api/v1/projects/p/native-summary/markdown?source_record_id=other")
        assert code == 400 and body["markdown"] is None
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
