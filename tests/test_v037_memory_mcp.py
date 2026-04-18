"""v0.37 memory MCP tool tests (call functions directly, not over stdio)."""

from __future__ import annotations

from tests._mcp_helpers import _get_mcp_tool
from tests._persona_factory import make_persona_vault


def test_mcp_list_entities(tmp_path, monkeypatch):
    from research_hub import mcp_server
    from research_hub.crystal import _read_cluster_papers
    from research_hub.memory import apply_memory

    cfg, _ = make_persona_vault(tmp_path, persona="A")
    monkeypatch.setattr("research_hub.mcp_server.get_config", lambda: cfg)
    paper_slug = _read_cluster_papers(cfg, "persona-a-test")[0]["slug"]
    apply_memory(cfg, "persona-a-test", {
        "entities": [{"slug": "ai21", "name": "AI21 Labs", "type": "org", "papers": [paper_slug]}],
    })
    result = _get_mcp_tool(mcp_server.mcp, "list_entities").fn(cluster="persona-a-test")
    assert result["count"] == 1
    assert result["entities"][0]["slug"] == "ai21"


def test_mcp_list_claims_filters_by_min_confidence(tmp_path, monkeypatch):
    from research_hub import mcp_server
    from research_hub.crystal import _read_cluster_papers
    from research_hub.memory import apply_memory

    cfg, _ = make_persona_vault(tmp_path, persona="A")
    monkeypatch.setattr("research_hub.mcp_server.get_config", lambda: cfg)
    paper_slug = _read_cluster_papers(cfg, "persona-a-test")[0]["slug"]
    apply_memory(cfg, "persona-a-test", {
        "claims": [
            {"slug": "high-claim", "text": "h", "confidence": "high", "papers": [paper_slug]},
            {"slug": "low-claim", "text": "l", "confidence": "low", "papers": [paper_slug]},
        ],
    })
    list_claims = _get_mcp_tool(mcp_server.mcp, "list_claims").fn
    high = list_claims(cluster="persona-a-test", min_confidence="high")
    assert high["count"] == 1
    all_levels = list_claims(cluster="persona-a-test", min_confidence="low")
    assert all_levels["count"] == 2


def test_mcp_list_methods(tmp_path, monkeypatch):
    from research_hub import mcp_server
    from research_hub.crystal import _read_cluster_papers
    from research_hub.memory import apply_memory

    cfg, _ = make_persona_vault(tmp_path, persona="A")
    monkeypatch.setattr("research_hub.mcp_server.get_config", lambda: cfg)
    paper_slug = _read_cluster_papers(cfg, "persona-a-test")[0]["slug"]
    apply_memory(cfg, "persona-a-test", {
        "methods": [{"slug": "ppo", "name": "PPO", "family": "rl", "papers": [paper_slug]}],
    })
    result = _get_mcp_tool(mcp_server.mcp, "list_methods").fn(cluster="persona-a-test")
    assert result["count"] == 1
    assert result["methods"][0]["family"] == "rl"


def test_mcp_read_cluster_memory_missing_returns_found_false(tmp_path, monkeypatch):
    from research_hub import mcp_server

    cfg, _ = make_persona_vault(tmp_path, persona="A")
    monkeypatch.setattr("research_hub.mcp_server.get_config", lambda: cfg)
    result = _get_mcp_tool(mcp_server.mcp, "read_cluster_memory").fn(cluster="persona-a-test")
    assert result["found"] is False
    assert "memory emit" in result["message"]
