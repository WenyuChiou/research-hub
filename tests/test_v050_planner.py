"""v0.50 — intent planner: freeform user intent → executable workflow plan."""
from __future__ import annotations

from types import SimpleNamespace

import pytest


def _no_cli():
    return None


def _claude_cli():
    return "claude"


def test_plan_extracts_topic_from_intent_prefix():
    from research_hub.planner import plan_workflow

    p = plan_workflow("I want to learn about harness engineering", detect_llm_cli_fn=_no_cli)
    assert p.suggested_topic == "harness engineering"
    assert "harness" in p.suggested_cluster_slug
    assert "engineering" in p.suggested_cluster_slug


def test_plan_handles_empty_intent():
    from research_hub.planner import plan_workflow

    p = plan_workflow("", detect_llm_cli_fn=_no_cli)
    assert p.suggested_topic == ""
    assert any("No intent" in w for w in p.warnings)


def test_plan_recommends_more_papers_for_thesis():
    from research_hub.planner import plan_workflow

    p = plan_workflow("research X for my dissertation", detect_llm_cli_fn=_no_cli)
    assert p.suggested_max_papers == 25


def test_plan_recommends_crystals_when_cli_available_and_intent_is_learning():
    from research_hub.planner import plan_workflow

    p = plan_workflow("I want to learn RAG basics", detect_llm_cli_fn=_claude_cli)
    assert p.suggested_do_crystals is True


def test_plan_skips_crystals_when_no_cli_even_for_learning():
    from research_hub.planner import plan_workflow

    p = plan_workflow("I want to learn RAG basics", detect_llm_cli_fn=_no_cli)
    assert p.suggested_do_crystals is False


def test_plan_respects_no_nlm_hint():
    from research_hub.planner import plan_workflow

    p = plan_workflow("find papers on X, no NotebookLM please", detect_llm_cli_fn=_no_cli)
    assert p.suggested_do_nlm is False


def test_plan_respects_no_zotero_hint_via_persona():
    from research_hub.planner import plan_workflow

    p = plan_workflow("ingest these without Zotero", detect_llm_cli_fn=_no_cli)
    assert p.suggested_persona == "analyst"


def test_plan_warns_on_existing_cluster_collision(tmp_path, monkeypatch):
    from research_hub.planner import plan_workflow

    # Build a fake cfg with a clusters.yaml containing a matching slug
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "harness-engineering").mkdir()
    (raw_dir / "harness-engineering" / "p1.md").write_text("a", encoding="utf-8")

    cfg = SimpleNamespace(
        clusters_file=tmp_path / "clusters.yaml",
        raw=raw_dir,
    )

    class _FakeReg:
        def __init__(self, *a, **kw): pass
        def list(self):
            return [SimpleNamespace(slug="harness-engineering", name="Harness")]

    monkeypatch.setattr("research_hub.clusters.ClusterRegistry", _FakeReg)

    p = plan_workflow("I want to learn harness engineering", cfg=cfg, detect_llm_cli_fn=_no_cli)
    assert p.existing_cluster_match == "harness-engineering"
    assert p.existing_cluster_paper_count == 1
    assert any("already exists" in w for w in p.warnings)
    assert p.next_call["args"]["cluster_slug"] == "harness-engineering"


def test_plan_next_call_is_executable_dict():
    from research_hub.planner import plan_workflow

    p = plan_workflow("research RAG for agriculture", detect_llm_cli_fn=_no_cli)
    nc = p.next_call
    assert nc["tool"] == "auto_research_topic"
    assert nc["args"]["topic"] == "RAG for agriculture"
    assert "max_papers" in nc["args"]
    assert "do_nlm" in nc["args"]


def test_plan_clarifying_questions_always_present():
    from research_hub.planner import plan_workflow

    p = plan_workflow("study agent-based modeling", detect_llm_cli_fn=_no_cli)
    assert len(p.clarifying_questions) >= 2  # depth + nlm + crystals/cli


def test_mcp_plan_research_workflow_returns_structured(monkeypatch):
    from research_hub import mcp_server as m
    from tests._mcp_helpers import _get_mcp_tool

    monkeypatch.setattr("research_hub.config.get_config", lambda: None)
    monkeypatch.setattr("research_hub.auto.detect_llm_cli", _no_cli)

    tool = _get_mcp_tool(m.mcp, "plan_research_workflow")
    result = tool.fn(user_intent="I want to learn about harness engineering")
    assert result["ok"] is True
    assert result["suggested_topic"] == "harness engineering"
    assert "next_call" in result
    assert result["next_call"]["tool"] == "auto_research_topic"
