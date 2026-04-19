"""v0.42 tests for the new patchright-based NotebookLM browser layer.

Adapted patterns are attributed in production code to:
https://github.com/PleasePrompto/notebooklm-skill (MIT)
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def test_patchright_importable():
    import patchright.sync_api  # noqa: F401


def test_default_session_dir_and_state_file(tmp_path: Path):
    from research_hub.notebooklm.browser import default_session_dir, default_state_file

    research_hub_dir = tmp_path / ".research_hub"
    assert default_session_dir(research_hub_dir) == research_hub_dir / "nlm_sessions" / "default"
    assert default_state_file(research_hub_dir) == research_hub_dir / "nlm_sessions" / "state.json"


def test_save_auth_state_writes_valid_json(tmp_path: Path):
    from research_hub.notebooklm.browser import save_auth_state

    state_file = tmp_path / "state.json"
    ctx = MagicMock()
    ctx.storage_state.return_value = {"cookies": [{"name": "SID", "value": "abc"}], "origins": []}
    save_auth_state(ctx, state_file)
    data = json.loads(state_file.read_text(encoding="utf-8"))
    assert data["cookies"][0]["name"] == "SID"


def test_load_auth_state_missing_returns_false(tmp_path: Path):
    from research_hub.notebooklm.browser import _load_auth_state

    ctx = MagicMock()
    assert _load_auth_state(ctx, tmp_path / "nope.json") is False
    ctx.add_cookies.assert_not_called()


def test_load_auth_state_injects_cookies(tmp_path: Path):
    from research_hub.notebooklm.browser import _load_auth_state

    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps({"cookies": [{"name": "A", "value": "1"}]}), encoding="utf-8")
    ctx = MagicMock()
    assert _load_auth_state(ctx, state_file) is True
    ctx.add_cookies.assert_called_once()


def test_default_launch_args_include_automation_stealth():
    from research_hub.notebooklm.browser import _DEFAULT_LAUNCH_ARGS, _IGNORE_DEFAULT_ARGS

    assert "--disable-blink-features=AutomationControlled" in _DEFAULT_LAUNCH_ARGS
    assert "--enable-automation" in _IGNORE_DEFAULT_ARGS


def test_cdp_launcher_shim_raises_on_launch():
    from research_hub.notebooklm.cdp_launcher import launch_chrome_with_cdp

    with pytest.raises(NotImplementedError):
        launch_chrome_with_cdp()


def test_session_open_cdp_session_shim_points_to_new_launcher(tmp_path: Path, monkeypatch):
    from research_hub.notebooklm import session as session_module

    called = {}

    @contextmanager
    def _fake_launch(**kwargs):
        called["kwargs"] = kwargs
        yield MagicMock(), MagicMock()

    monkeypatch.setattr(session_module, "launch_nlm_context", _fake_launch)
    session_dir = tmp_path / "session"
    with session_module.open_cdp_session(session_dir, headless=True) as (ctx, page):
        assert ctx is not None
        assert page is not None
    assert called["kwargs"]["user_data_dir"] == session_dir
    assert called["kwargs"]["headless"] is True


def test_upload_retry_succeeds_on_second_attempt(tmp_path: Path, monkeypatch):
    from research_hub.notebooklm.client import UploadResult
    from research_hub.notebooklm.upload import _upload_with_retry

    client = MagicMock()
    calls = {"count": 0}

    def _upload(path):
        calls["count"] += 1
        if calls["count"] == 1:
            return UploadResult("pdf", str(path), False, "transient")
        return UploadResult("pdf", str(path), True, "")

    client.upload_pdf.side_effect = _upload
    monkeypatch.setattr("research_hub.notebooklm.upload.time.sleep", lambda _: None)
    result = _upload_with_retry(client, {"action": "pdf", "pdf_path": str(tmp_path / "a.pdf")}, tmp_path / "log.jsonl")
    assert result.success is True
    lines = (tmp_path / "log.jsonl").read_text(encoding="utf-8").splitlines()
    kinds = [json.loads(line)["kind"] for line in lines]
    assert kinds.count("upload_attempt") == 2
    assert "upload_ok" in kinds


def test_upload_retry_reports_failure_after_max_attempts(tmp_path: Path, monkeypatch):
    from research_hub.notebooklm.client import UploadResult
    from research_hub.notebooklm.upload import _upload_with_retry

    client = MagicMock()
    client.upload_pdf.return_value = UploadResult("pdf", "x", False, "boom")
    monkeypatch.setattr("research_hub.notebooklm.upload.time.sleep", lambda _: None)
    result = _upload_with_retry(client, {"action": "pdf", "pdf_path": "x"}, tmp_path / "log.jsonl")
    assert result.success is False
    fails = [
        json.loads(line)
        for line in (tmp_path / "log.jsonl").read_text(encoding="utf-8").splitlines()
        if json.loads(line)["kind"] == "upload_fail"
    ]
    assert len(fails) == 3


def test_upload_cluster_writes_header_and_retry_count(tmp_path: Path, monkeypatch):
    from research_hub.clusters import Cluster
    from research_hub.notebooklm.client import UploadResult
    from research_hub.notebooklm.upload import upload_cluster
    from tests.test_notebooklm_client import StubCfg, StubPage, _write_cluster

    cfg = StubCfg(tmp_path)
    cfg.research_hub_dir.mkdir(parents=True)
    bundle_dir = cfg.research_hub_dir / "bundles" / "alpha-20260411T000000Z"
    bundle_dir.mkdir(parents=True)
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"pdf")
    (bundle_dir / "manifest.json").write_text(
        json.dumps({"entries": [{"action": "pdf", "pdf_path": str(pdf_path)}]}),
        encoding="utf-8",
    )
    cluster = Cluster(slug="alpha", name="Alpha", notebooklm_notebook="Alpha Notebook")
    _write_cluster(cfg, cluster)

    class FakeClient:
        def __init__(self, page):
            self.calls = 0

        def open_or_create_notebook(self, name):
            return type("Handle", (), {"url": "https://notebooklm.google.com/notebook/abc", "notebook_id": "abc", "name": name})()

        def upload_pdf(self, path):
            self.calls += 1
            if self.calls == 1:
                return UploadResult("pdf", str(path), False, "once")
            return UploadResult("pdf", str(path), True, "")

    @contextmanager
    def fake_open(*args, **kwargs):
        yield object(), StubPage()

    monkeypatch.setattr("research_hub.notebooklm.upload.open_cdp_session", fake_open)
    monkeypatch.setattr("research_hub.notebooklm.upload.NotebookLMClient", FakeClient)
    monkeypatch.setattr("research_hub.notebooklm.upload._check_session_health", lambda page: (True, "ok"))
    monkeypatch.setattr("research_hub.notebooklm.upload.time.sleep", lambda _: None)

    report = upload_cluster(cluster, cfg, dry_run=False)
    assert report.success_count == 1
    logs = sorted(cfg.research_hub_dir.glob("nlm-debug-*.jsonl"))
    assert logs
    payloads = [json.loads(line) for line in logs[-1].read_text(encoding="utf-8").splitlines()]
    assert payloads[0]["kind"] == "upload_run_start"
    assert payloads[-1]["kind"] == "upload_run_complete"
    assert payloads[-1]["retry_count"] == 1
