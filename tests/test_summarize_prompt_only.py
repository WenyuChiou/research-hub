"""Offline prompt-only status checks; no host/model or live destination acceptance."""

import ast
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from research_hub import llm_cli, summarize
from research_hub.cli_summarize import _cmd_summarize


@pytest.fixture
def prompt_only(tmp_path, monkeypatch):
    cluster = tmp_path / "raw" / "fixture-cluster"
    cluster.mkdir(parents=True)
    note = cluster / "fixture-paper.md"
    original = b"---\ntitle: Fixture paper\nsummary_status: pending\n---\n\n## Abstract\n\nSynthetic abstract for offline tests.\n\n## Key Findings\n\n[TODO]\n"
    note.write_bytes(original)
    cfg = SimpleNamespace(raw=cluster.parent, research_hub_dir=tmp_path / ".research_hub")
    detect = Mock(return_value=None)
    invoke = Mock(side_effect=AssertionError("Model invocation is forbidden"))
    apply = Mock(side_effect=AssertionError("Destination apply is forbidden"))
    monkeypatch.setattr(llm_cli, "detect_llm_cli", detect)
    monkeypatch.setattr(llm_cli, "invoke_llm_cli", invoke)
    monkeypatch.setattr(summarize, "apply_summaries", apply)
    monkeypatch.setattr(llm_cli.shutil, "which", Mock(side_effect=AssertionError("Real CLI discovery is forbidden")))
    monkeypatch.setattr(llm_cli.subprocess, "Popen", Mock(side_effect=AssertionError("Subprocess execution is forbidden")))
    yield cfg
    detect.assert_called_once_with()
    invoke.assert_not_called()
    apply.assert_not_called()
    assert note.read_bytes() == original
    assert sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file()) == [
        ".research_hub/artifacts/fixture-cluster/summarize-prompt.md",
        "raw/fixture-cluster/fixture-paper.md",
    ]


@pytest.mark.parametrize("apply", [False, True])
def test_no_cli_is_prompt_only_even_with_apply(prompt_only, apply):
    report = summarize.summarize_cluster(prompt_only, "fixture-cluster", apply=apply)
    assert report.to_dict() == {
        "cluster_slug": "fixture-cluster", "ok": True, "error": "", "cli_used": "",
        "prompt_path": str(prompt_only.research_hub_dir / "artifacts/fixture-cluster/summarize-prompt.md"),
        "apply_result": None,
    }
    assert "Synthetic abstract for offline tests." in report.prompt_path.read_text(encoding="utf-8")


@pytest.mark.parametrize("apply", [False, True])
@pytest.mark.parametrize("emit_json", [False, True])
def test_cli_reports_prompt_only_without_changing_json_contract(prompt_only, apply, emit_json, capsys):
    args = SimpleNamespace(cluster="fixture-cluster", llm_cli=None, apply=apply,
                           no_zotero=False, no_obsidian=False)
    assert _cmd_summarize(args, prompt_only, emit_json=emit_json) == 0
    output = capsys.readouterr()
    assert output.err == ""
    if emit_json:
        envelope = json.loads(output.out)
        assert envelope["ok"] is True
        assert envelope["schema_version"] == "1.0"
        assert envelope["report"]["apply_result"] is None
        assert envelope["report"]["cli_used"] == ""
        assert set(envelope["report"]) == {
            "cluster_slug", "ok", "error", "cli_used", "prompt_path", "apply_result",
        }
    else:
        assert str(prompt_only.research_hub_dir / "artifacts/fixture-cluster/summarize-prompt.md") in output.out
        for status in ["Prompt-only", "no summaries were generated or applied", "even with --apply",
                       "authorized tools", "readable abstract-based summaries",
                       "separately authorized supported operation", "selected destination",
                       "report saving as pending", "does not import externally generated summaries"]:
            assert status in output.out
        assert "pipe it through" not in output.out


def test_no_cli_guidance_matches_source_and_packaged_skill():
    root = Path(__file__).resolve().parents[1]
    paths = [root / "skills/paper-summarize/SKILL.md",
             root / "src/research_hub/skills_data/paper-summarize/SKILL.md"]
    texts = [path.read_text(encoding="utf-8") for path in paths]
    assert texts[0] == texts[1]
    guidance = [next(line for line in text.splitlines() if line.startswith("- **No LLM CLI on PATH**"))
                for text in texts]
    assert guidance[0] == guidance[1]
    for required in ["prompt-only", "no summaries were generated or applied", "does not import",
                     "native host agent", "readable abstract-based summaries", "not full-text validation",
                     "separately authorized", "defaults to writing both Obsidian and Zotero",
                     "not an automatically authorized fallback", "saving as pending",
                     "do not ask the researcher to author JSON"]:
        assert required in guidance[0]
    eval_paths = [path.parent / "evals/evals.json" for path in paths]
    evals = [json.loads(path.read_text(encoding="utf-8")) for path in eval_paths]
    assert evals[0] == evals[1]
    assert "prompt-only" in eval_paths[0].read_text(encoding="utf-8")


def test_active_mcp_description_reports_prompt_only_and_authorized_persistence():
    root = Path(__file__).resolve().parents[1]
    tree = ast.parse((root / "src/research_hub/mcp_server.py").read_text(encoding="utf-8"))
    node = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                and node.name == "summarize_cluster")
    description = " ".join(ast.get_docstring(node).split())
    for required in ["prompt-only", "No summaries were generated or applied", "even with apply=True",
                     "does not import external summaries", "native host agent", "authorized tools",
                     "readable abstract-based summaries, not full-text validation",
                     "separately authorized supported destination operation",
                     "defaults to writing both Obsidian and Zotero",
                     "not an automatically authorized fallback", "report saving as pending",
                     "do not ask the researcher to author JSON"]:
        assert required in description
