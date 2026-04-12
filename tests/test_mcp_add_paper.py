"""Tests for MCP add_paper wrapper."""

from __future__ import annotations


def test_add_paper_mcp_tool_returns_dict(monkeypatch):
    from research_hub.mcp_server import mcp

    monkeypatch.setattr(
        "research_hub.operations.add_paper",
        lambda *args, **kwargs: {"status": "ok", "title": "T", "doi": "10", "slug": "s"},
    )

    result = mcp._tool_manager._tools["add_paper"].fn("10.1000/example")

    assert result["status"] == "ok"
    assert result["slug"] == "s"


def test_add_paper_mcp_tool_error_handling(monkeypatch):
    from research_hub.mcp_server import mcp

    def boom(*args, **kwargs):
        raise RuntimeError("broken")

    monkeypatch.setattr("research_hub.operations.add_paper", boom)

    assert mcp._tool_manager._tools["add_paper"].fn("10.1000/example") == {"error": "broken"}
