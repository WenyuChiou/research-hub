"""v0.47 — MCP wrappers for lazy mode commands."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest


def test_auto_research_topic_returns_structured(monkeypatch):
    from research_hub import mcp_server as m
    from research_hub.auto import AutoReport, AutoStepResult

    captured = {}

    def _fake_pipeline(topic, **kwargs):
        captured["topic"] = topic
        captured["kwargs"] = kwargs
        return AutoReport(
            cluster_slug="x",
            cluster_created=True,
            ok=True,
            papers_ingested=3,
            nlm_uploaded=3,
            notebook_url="https://notebooklm.google.com/notebook/abc",
            brief_path=Path("/tmp/brief.txt"),
            total_duration_sec=42.0,
            steps=[AutoStepResult(name="cluster", ok=True, detail="created: x")],
        )

    monkeypatch.setattr("research_hub.auto.auto_pipeline", _fake_pipeline)

    from tests._mcp_helpers import _get_mcp_tool

    tool = _get_mcp_tool(m.mcp, "auto_research_topic")
    result = tool.fn(topic="harness engineering", max_papers=3)
    assert result["ok"] is True
    assert result["cluster_slug"] == "x"
    assert result["papers_ingested"] == 3
    assert result["notebook_url"].endswith("abc")
    assert captured["topic"] == "harness engineering"
    assert captured["kwargs"]["max_papers"] == 3
    assert captured["kwargs"]["print_progress"] is False


def test_auto_research_topic_failure(monkeypatch):
    from research_hub import mcp_server as m
    from research_hub.auto import AutoReport

    monkeypatch.setattr(
        "research_hub.auto.auto_pipeline",
        lambda topic, **kw: AutoReport(
            cluster_slug="x", cluster_created=False, ok=False,
            error="search returned 0 papers",
        ),
    )
    from tests._mcp_helpers import _get_mcp_tool

    tool = _get_mcp_tool(m.mcp, "auto_research_topic")
    result = tool.fn(topic="bad topic")
    assert result["ok"] is False
    assert "0 papers" in result["error"]


def test_cleanup_garbage_dry_run(monkeypatch):
    from research_hub import mcp_server as m

    fake_report = MagicMock(
        total_bytes=12345,
        files_deleted=0,
        dirs_deleted=0,
        apply=False,
        bundles=[MagicMock(path=Path("/tmp/x"), size_bytes=12345)],
        debug_logs=[],
        artifacts=[],
    )
    monkeypatch.setattr("research_hub.cleanup.collect_garbage", lambda cfg, **kw: fake_report)
    monkeypatch.setattr("research_hub.cleanup.format_bytes", lambda n: "12.1 KB")

    from tests._mcp_helpers import _get_mcp_tool

    tool = _get_mcp_tool(m.mcp, "cleanup_garbage")
    result = tool.fn(everything=True)
    assert result["ok"] is True
    assert result["total_bytes"] == 12345
    assert result["applied"] is False
    assert len(result["candidates"]) == 1
    assert result["candidates"][0]["kind"] == "bundle"


def test_cleanup_garbage_apply_passes_through(monkeypatch):
    from research_hub import mcp_server as m

    captured = {}

    def _gc(cfg, **kwargs):
        captured.update(kwargs)
        return MagicMock(
            total_bytes=0, files_deleted=2, dirs_deleted=1,
            apply=True, bundles=[], debug_logs=[], artifacts=[],
        )

    monkeypatch.setattr("research_hub.cleanup.collect_garbage", _gc)
    monkeypatch.setattr("research_hub.cleanup.format_bytes", lambda n: "0 B")

    from tests._mcp_helpers import _get_mcp_tool

    tool = _get_mcp_tool(m.mcp, "cleanup_garbage")
    result = tool.fn(bundles=True, apply=True)
    assert result["ok"] is True
    assert captured["apply"] is True
    assert captured["do_bundles"] is True


def test_tidy_vault_returns_steps(monkeypatch):
    from research_hub import mcp_server as m
    from research_hub.tidy import TidyReport, TidyStep

    monkeypatch.setattr(
        "research_hub.tidy.run_tidy",
        lambda apply_cleanup, print_progress: TidyReport(
            steps=[
                TidyStep(name="doctor", ok=True, detail="all green"),
                TidyStep(name="dedup", ok=True, detail="767 DOIs"),
                TidyStep(name="bases", ok=True, detail="8 clusters"),
                TidyStep(name="cleanup", ok=True, detail="0 B"),
            ],
            total_duration_sec=4.2,
            cleanup_preview_bytes=0,
        ),
    )

    from tests._mcp_helpers import _get_mcp_tool

    tool = _get_mcp_tool(m.mcp, "tidy_vault")
    result = tool.fn()
    assert result["ok"] is True
    assert len(result["steps"]) == 4
    assert result["steps"][0]["name"] == "doctor"
    assert result["total_duration_sec"] == 4.2
