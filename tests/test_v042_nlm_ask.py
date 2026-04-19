"""v0.42 tests for `research-hub notebooklm ask` and its MCP tool.

Adapted patterns are attributed in production code to:
https://github.com/PleasePrompto/notebooklm-skill (MIT)
"""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_cluster():
    c = MagicMock()
    c.slug = "test-cluster"
    c.notebooklm_notebook_url = "https://notebooklm.google.com/notebook/abc123"
    return c


@pytest.fixture
def mock_cfg(tmp_path):
    cfg = MagicMock()
    cfg.research_hub_dir = tmp_path / ".research_hub"
    cfg.research_hub_dir.mkdir()
    return cfg


def test_ask_cluster_missing_url_returns_error(mock_cfg):
    from research_hub.notebooklm.ask import ask_cluster_notebook

    c = MagicMock()
    c.slug = "no-url"
    c.notebooklm_notebook_url = ""
    result = ask_cluster_notebook(c, mock_cfg, question="anything")
    assert not result.ok
    assert "notebooklm upload" in result.error.lower()


def test_ask_cluster_empty_question_returns_error(mock_cluster, mock_cfg):
    from research_hub.notebooklm.ask import ask_cluster_notebook

    result = ask_cluster_notebook(mock_cluster, mock_cfg, question="   ")
    assert not result.ok


def test_ask_cluster_saves_artifact_on_success(mock_cluster, mock_cfg, monkeypatch):
    from research_hub.notebooklm import ask as ask_module

    @contextmanager
    def _fake_launch(**kwargs):
        yield MagicMock(), MagicMock()

    monkeypatch.setattr(ask_module, "launch_nlm_context", _fake_launch)
    monkeypatch.setattr(ask_module, "_find_query_input", lambda page: "textarea")
    monkeypatch.setattr(ask_module, "_human_type", lambda page, sel, text: None)
    monkeypatch.setattr(ask_module, "_wait_for_stable_answer", lambda page, **kw: "The answer is 42.")

    result = ask_module.ask_cluster_notebook(mock_cluster, mock_cfg, question="What is the answer?")
    assert result.ok
    assert result.artifact_path is not None and result.artifact_path.exists()
    body = result.artifact_path.read_text(encoding="utf-8")
    assert "What is the answer?" in body
    assert "The answer is 42." in body


def test_ask_cluster_no_answer_reports_timeout(mock_cluster, mock_cfg, monkeypatch):
    from research_hub.notebooklm import ask as ask_module

    @contextmanager
    def _fake_launch(**kwargs):
        page = MagicMock()
        page.keyboard = MagicMock()
        yield MagicMock(), page

    monkeypatch.setattr(ask_module, "launch_nlm_context", _fake_launch)
    monkeypatch.setattr(ask_module, "_find_query_input", lambda page: "textarea")
    monkeypatch.setattr(ask_module, "_human_type", lambda *a, **kw: None)
    monkeypatch.setattr(ask_module, "_wait_for_stable_answer", lambda page, **kw: "")

    result = ask_module.ask_cluster_notebook(mock_cluster, mock_cfg, question="?")
    assert not result.ok
    assert "no answer" in result.error.lower() or "generating" in result.error.lower()


def test_wait_for_stable_answer_requires_three_consistent_reads(monkeypatch):
    from research_hub.notebooklm import ask as ask_module

    reads = iter(["partial", "full", "done", "done", "done"])
    monkeypatch.setattr(ask_module, "_read_response_text", lambda page: next(reads, ""))
    monkeypatch.setattr(ask_module, "_is_thinking", lambda page: False)
    monkeypatch.setattr("time.sleep", lambda _: None)

    result = ask_module._wait_for_stable_answer(
        MagicMock(), timeout_sec=10, stable_reads_required=3, poll_interval_sec=0
    )
    assert result == "done"


def test_wait_for_stable_answer_pauses_while_thinking(monkeypatch):
    from research_hub.notebooklm import ask as ask_module

    thinking_states = iter([True, True, False, False, False, False])
    texts = iter(["", "", "partial", "answer", "answer", "answer"])
    monkeypatch.setattr(ask_module, "_is_thinking", lambda page: next(thinking_states, False))
    monkeypatch.setattr(ask_module, "_read_response_text", lambda page: next(texts, ""))
    monkeypatch.setattr("time.sleep", lambda _: None)

    result = ask_module._wait_for_stable_answer(
        MagicMock(), timeout_sec=10, stable_reads_required=3, poll_interval_sec=0
    )
    assert result == "answer"


def test_ask_cli_dispatch(monkeypatch):
    from research_hub import cli as cli_module

    called = {}

    def _fake_ask(slug, *, question, headless, timeout_sec):
        called["slug"] = slug
        called["question"] = question
        called["headless"] = headless
        called["timeout_sec"] = timeout_sec
        return 0

    monkeypatch.setattr(cli_module, "_nlm_ask", _fake_ask)
    rc = cli_module.main(["notebooklm", "ask", "--cluster", "X", "--question", "Hello?"])
    assert rc == 0
    assert called == {
        "slug": "X",
        "question": "Hello?",
        "headless": True,
        "timeout_sec": 120,
    }


def test_mcp_ask_cluster_notebooklm_returns_structured(monkeypatch):
    from research_hub import mcp_server as m
    from research_hub.notebooklm.ask import AskResult

    fake_cluster = MagicMock(slug="x", notebooklm_notebook_url="https://x")
    fake_cfg = MagicMock(clusters_file=Path("clusters.yaml"))
    fake_registry = MagicMock()
    fake_registry.get.return_value = fake_cluster

    monkeypatch.setattr(m, "get_config", lambda: fake_cfg)
    monkeypatch.setattr("research_hub.clusters.ClusterRegistry", lambda *a, **kw: fake_registry)
    monkeypatch.setattr(
        "research_hub.notebooklm.ask.ask_cluster_notebook",
        lambda c, cfg, **kw: AskResult(
            ok=True, answer="42", artifact_path=Path("/tmp/a.md"), latency_seconds=2.5
        ),
    )

    tool = getattr(m.ask_cluster_notebooklm, "fn", m.ask_cluster_notebooklm)
    result = tool(cluster="x", question="meaning of life?")
    assert result["ok"] is True
    assert result["answer"] == "42"
    assert result["artifact_path"].endswith("a.md")
