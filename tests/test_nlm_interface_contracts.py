"""Offline interface contracts using the installed SDK's real return types.

The SDK poller and mind-map parser run, but RPC and note persistence are
synthetic. No storage, browser, credentials or provider network is used.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from notebooklm._artifacts import ArtifactsAPI
from notebooklm.types import GenerationStatus

from research_hub.clusters import Cluster, ClusterRegistry
from research_hub.connectors._notebooklm_adapter import NotebookLMConnector
from research_hub.mcp_server import mcp
from research_hub.notebooklm.client import NotebookLMClient, NotebookLMError, UploadResult
from research_hub.notebooklm.upload import UploadReport, generate_artifact
from tests._mcp_helpers import _get_mcp_tool


@pytest.fixture
def sdk_client(tmp_path):
    core = SimpleNamespace(
        get_source_ids=AsyncMock(return_value=["source-synthetic"]),
        rpc_call=AsyncMock(return_value=[[json.dumps({"name": "Synthetic map"})]]),
    )
    notes = SimpleNamespace(create=AsyncMock(return_value=SimpleNamespace(id="note-synthetic")))
    artifacts = ArtifactsAPI(core, notes)
    client = NotebookLMClient.__new__(NotebookLMClient)
    client._client = SimpleNamespace(artifacts=artifacts)
    client._timeout = 0.01
    client._state_file = tmp_path / "unused-state.json"
    client._closed = False
    client._loop = asyncio.new_event_loop()
    yield client, artifacts, core, notes
    client.close()


def _report_generation(artifacts, monkeypatch, *, final_status="failed"):
    monkeypatch.setattr(
        artifacts, "generate_report",
        AsyncMock(return_value=GenerationStatus(task_id="task-synthetic", status="pending")),
    )
    monkeypatch.setattr(
        artifacts, "poll_status",
        AsyncMock(return_value=GenerationStatus(
            task_id="task-synthetic", status=final_status,
            error="Synthetic quota rejection" if final_status == "failed" else None,
            error_code="USER_DISPLAYABLE_ERROR" if final_status == "failed" else None,
        )),
    )


def _cluster_cfg(tmp_path, monkeypatch):
    hub = tmp_path / "hub"
    hub.mkdir()
    cfg = SimpleNamespace(research_hub_dir=hub, clusters_file=hub / "clusters.yaml")
    cluster = Cluster(slug="alpha", name="Alpha", notebooklm_notebook_id="notebook-synthetic")
    registry = ClusterRegistry(cfg.clusters_file)
    registry.clusters[cluster.slug] = cluster
    registry.save()
    monkeypatch.setattr("research_hub.config.get_config", lambda: cfg)
    monkeypatch.setattr("research_hub.cli_notebooklm.get_config", lambda: cfg)
    monkeypatch.setattr("research_hub.cli_notebooklm._preflight_nlm_session", lambda *a, **kw: None)
    return cluster, cfg


def _call_mcp(name, *args, **kwargs):
    tool = _get_mcp_tool(mcp, name)
    return getattr(tool, "fn", tool)(*args, **kwargs)


def test_real_sdk_failed_poll_is_not_a_successful_artifact(sdk_client, monkeypatch):
    client, artifacts, *_ = sdk_client
    _report_generation(artifacts, monkeypatch)
    with pytest.raises(NotebookLMError, match="Synthetic quota rejection"):
        client.trigger_briefing("notebook-synthetic")
    assert artifacts.poll_status.await_count == 1


@pytest.mark.parametrize("kind,method", [
    ("brief", "generate_report"), ("audio", "generate_audio"),
    ("video", "generate_video"), ("slide_deck", "generate_slide_deck"),
])
def test_immediate_sdk_failure_is_not_polled(sdk_client, monkeypatch, kind, method):
    client, artifacts, *_ = sdk_client
    monkeypatch.setattr(artifacts, method, AsyncMock(return_value=GenerationStatus(
        task_id="rejected-task", status="failed", error="Synthetic immediate rejection",
    )))
    poller = AsyncMock(side_effect=AssertionError("rejected task must not be polled"))
    monkeypatch.setattr(artifacts, "wait_for_completion", poller)
    with pytest.raises(NotebookLMError, match="Synthetic immediate rejection"):
        client._trigger_generation(kind, "notebook-synthetic")
    poller.assert_not_awaited()


@pytest.mark.parametrize("state", ["pending", "in_progress", "not_found", "unknown"])
def test_nonterminal_or_unknown_result_never_claims_completion(sdk_client, monkeypatch, state):
    client, artifacts, *_ = sdk_client
    _report_generation(artifacts, monkeypatch)
    monkeypatch.setattr(artifacts, "wait_for_completion", AsyncMock(return_value=GenerationStatus(
        task_id="task-synthetic", status=state,
    )))
    with pytest.raises(NotebookLMError, match=state):
        client.trigger_briefing("notebook-synthetic")


@pytest.mark.parametrize("prefer_id", [True, False])
def test_completed_sdk_result_preserves_artifact_reference(sdk_client, monkeypatch, prefer_id):
    client, artifacts, *_ = sdk_client
    _report_generation(artifacts, monkeypatch, final_status="completed")
    artifacts.poll_status.return_value.url = "https://example.invalid/artifact-synthetic"
    expected = "task-synthetic" if prefer_id else "https://example.invalid/artifact-synthetic"
    assert client._trigger_generation("brief", "notebook-synthetic", prefer_id=prefer_id) == expected
    assert artifacts.poll_status.await_count == 1


def test_failed_briefing_result_does_not_attempt_download(sdk_client, monkeypatch):
    client, artifacts, *_ = sdk_client
    _report_generation(artifacts, monkeypatch)
    downloader = AsyncMock(side_effect=AssertionError("failed artifact must not be downloaded"))
    monkeypatch.setattr(artifacts, "download_report", downloader)
    result = client.generate_briefing("notebook-synthetic")
    assert result.ok is False and result.text == ""
    assert "Synthetic quota rejection" in result.error
    downloader.assert_not_awaited()


def test_completed_briefing_downloads_exact_generated_artifact(sdk_client, monkeypatch):
    from pathlib import Path

    client, artifacts, *_ = sdk_client
    _report_generation(artifacts, monkeypatch, final_status="completed")

    async def download(notebook_id, output_path, *, artifact_id):
        assert notebook_id == "notebook-synthetic"
        assert artifact_id == "task-synthetic"
        Path(output_path).write_text("Synthetic report", encoding="utf-8")

    monkeypatch.setattr(artifacts, "download_report", download)
    result = client.generate_briefing("notebook-synthetic")
    assert result.ok is True and result.text == "Synthetic report"


def test_real_sdk_mind_map_dictionary_uses_note_id_without_polling(sdk_client, monkeypatch):
    client, artifacts, core, notes = sdk_client
    poller = AsyncMock(side_effect=AssertionError("mind maps are already persisted notes"))
    monkeypatch.setattr(artifacts, "wait_for_completion", poller)
    assert client.trigger_mind_map("notebook-synthetic") == "note-synthetic"
    assert core.rpc_call.await_count == 1
    notes.create.assert_awaited_once_with(
        "notebook-synthetic", title="Synthetic map", content=json.dumps({"name": "Synthetic map"})
    )
    poller.assert_not_awaited()


@pytest.mark.parametrize("sdk_response", [
    {"mind_map": None, "note_id": None}, {"mind_map": {}, "note_id": ""},
    {"mind_map": {}, "note_id": "  "}, {"mind_map": {}, "note_id": 123},
])
def test_mind_map_without_saved_note_is_not_success(sdk_client, monkeypatch, sdk_response):
    client, artifacts, *_ = sdk_client
    monkeypatch.setattr(artifacts, "generate_mind_map", AsyncMock(return_value=sdk_response))
    with pytest.raises(NotebookLMError, match="saved note id"):
        client.trigger_mind_map("notebook-synthetic")


@pytest.mark.parametrize("surface", ["cli", "mcp", "connector"])
def test_mind_map_note_identity_survives_public_surfaces(
    surface, sdk_client, monkeypatch, tmp_path, capsys
):
    client, *_ = sdk_client
    cluster, cfg = _cluster_cfg(tmp_path, monkeypatch)
    monkeypatch.setattr("research_hub.notebooklm.upload._make_client", lambda *a, **kw: client)
    if surface == "cli":
        from research_hub.cli_notebooklm import _nlm_generate

        assert _nlm_generate("alpha", "mind-map", True) == 0
        assert "mind_map: note-synthetic" in capsys.readouterr().out
    elif surface == "mcp":
        result = _call_mcp("notebooklm_generate", "alpha", artifact_type="mind-map")
        assert result["status"] == "ok"
        assert result["artifacts"] == {"mind_map": "note-synthetic"}
    else:
        result = NotebookLMConnector().generate(cluster, cfg, artifact_type="mind-map")
        assert result["ok"] is True
        assert result["url"] == "note-synthetic"
    cache = json.loads((cfg.research_hub_dir / "nlm_cache.json").read_text(encoding="utf-8"))
    assert cache["alpha"]["mind_map_url"] == "note-synthetic"
    assert client._closed


@pytest.mark.parametrize("surface", ["module", "cli", "mcp", "connector"])
def test_failed_generation_does_not_publish_success_or_update_cache(
    surface, sdk_client, monkeypatch, tmp_path, capsys
):
    client, artifacts, *_ = sdk_client
    _report_generation(artifacts, monkeypatch)
    cluster, cfg = _cluster_cfg(tmp_path, monkeypatch)
    monkeypatch.setattr("research_hub.notebooklm.upload._make_client", lambda *a, **kw: client)
    cache_path = cfg.research_hub_dir / "nlm_cache.json"
    original = '{"alpha":{"briefing_url":"previous-good","last_synced":"old"}}'
    cache_path.write_text(original, encoding="utf-8")
    if surface == "mcp":
        result = _call_mcp("notebooklm_generate", "alpha", artifact_type="brief")
        assert result.get("status") != "ok"
        assert "Synthetic quota rejection" in result["error"]
        assert "artifacts" not in result
    else:
        with pytest.raises(NotebookLMError, match="Synthetic quota rejection"):
            if surface == "module":
                generate_artifact(cluster, cfg, kind="brief")
            elif surface == "cli":
                from research_hub.cli_notebooklm import _nlm_generate

                _nlm_generate("alpha", "brief", True)
            else:
                NotebookLMConnector().generate(cluster, cfg)
    assert cache_path.read_text(encoding="utf-8") == original
    assert "task-synthetic" not in capsys.readouterr().out
    assert client._closed
    events = [json.loads(line) for p in cfg.research_hub_dir.glob("nlm-debug-*.jsonl")
              for line in p.read_text(encoding="utf-8").splitlines()]
    assert not any(event["kind"] == "generate_ok" for event in events)


@pytest.mark.parametrize("failure", ["timeout", "cancel"])
def test_sdk_timeout_and_cancellation_preserve_cache_and_close_client(
    failure, sdk_client, monkeypatch, tmp_path
):
    client, artifacts, *_ = sdk_client
    _report_generation(artifacts, monkeypatch, final_status="pending")
    expected_error = TimeoutError
    if failure == "timeout":
        # Run the real SDK timeout branch without a timer/sleep or network.
        client._timeout = -1
    else:
        expected_error = asyncio.CancelledError
        artifacts.poll_status.side_effect = asyncio.CancelledError("Synthetic cancellation")
    cluster, cfg = _cluster_cfg(tmp_path, monkeypatch)
    monkeypatch.setattr("research_hub.notebooklm.upload._make_client", lambda *a, **kw: client)
    cache_path = cfg.research_hub_dir / "nlm_cache.json"
    original = '{"alpha":{"briefing_url":"previous-good"}}'
    cache_path.write_text(original, encoding="utf-8")
    with pytest.raises(expected_error):
        generate_artifact(cluster, cfg, kind="brief")
    assert cache_path.read_text(encoding="utf-8") == original
    assert client._closed and client._loop.is_closed()


@pytest.mark.parametrize("successes,failures", [(1, 1), (0, 2), (2, 0), (0, 0)])
def test_connector_upload_preserves_partial_counts_and_errors(
    successes, failures, monkeypatch, tmp_path, capsys
):
    cluster, cfg = _cluster_cfg(tmp_path, monkeypatch)
    report = UploadReport(
        cluster_slug="alpha", notebook_id="notebook-synthetic",
        skipped_already_uploaded=3,
        uploaded=[UploadResult(success=True) for _ in range(successes)]
        + [UploadResult(success=False, error="Synthetic expired session") for _ in range(failures)],
        errors=[{"source": f"source-{n}", "error": "Synthetic expired session"}
                for n in range(failures)],
    )
    monkeypatch.setattr("research_hub.notebooklm.upload.upload_cluster", lambda *a, **kw: report)
    connector = NotebookLMConnector().upload(cluster, cfg)
    mcp_result = _call_mcp("notebooklm_upload", "alpha")
    assert connector.uploaded_count == mcp_result["uploaded_count"] == successes
    assert connector.failed_count == mcp_result["failed_count"] == failures
    assert connector.errors == mcp_result["errors"] == report.errors
    assert connector.skipped_count == mcp_result["skipped_already_uploaded"] == 3
    from research_hub.cli_notebooklm import _nlm_upload

    monkeypatch.setattr("research_hub.notebooklm.upload.check_cluster_capacity", lambda *a: None)
    rc = _nlm_upload("alpha", dry_run=False, headless=True, create_if_missing=False)
    assert rc == (1 if failures else 0)
    assert f"Uploads: {successes} succeeded, {failures} failed, 3 skipped" in capsys.readouterr().out
    # Preserve the real upload report; mapping must not rewrite partial results.
    assert report.success_count == successes
    assert report.fail_count == failures
