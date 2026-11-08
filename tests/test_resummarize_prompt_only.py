"""Offline regression for TODO-note selection within a cluster; no providers."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from research_hub import cli_paper, llm_cli, summarize


def write_note(path, title, summary, key=""):
    path.write_text(
        f"---\ntitle: {title}\nzotero-key: {key}\n---\n\n## Abstract\n\n{title} synthetic abstract.\n\n## Summary\n\n{summary}\n\n## Key Findings\n\n[TODO]\n",
        encoding="utf-8",
    )


@pytest.fixture
def isolated_cluster(tmp_path, monkeypatch, request):
    raw = tmp_path / "raw" / "fixture-cluster"
    raw.mkdir(parents=True)
    hub = tmp_path / ".research_hub"
    hub.mkdir()
    registry = hub / "clusters.yaml"
    registry.write_text(json.dumps({"clusters": {"fixture-cluster": {
        "name": "Fixture cluster", "obsidian_subfolder": "fixture-cluster",
    }}}), encoding="utf-8")
    no_todos = getattr(request, "param", False)
    for filename, title, summary, key in [
        ("todo-one.md", "Selected one", "Already summarized." if no_todos else "[TODO]", "TODO1"),
        ("todo-two.md", "Selected two", "Already summarized." if no_todos else "[TODO: summarize]", "TODO2"),
        ("done.md", "Excluded completed", "Existing human summary.", "DONE"),
        ("without-key.md", "Excluded missing key", "[TODO]", ""),
        ("00_overview.md", "Excluded overview", "[TODO]", "OVERVIEW"),
    ]:
        write_note(raw / filename, title, summary, key)
    before = {path: path.read_bytes() for path in [registry, *raw.glob("*.md")]}
    cfg = SimpleNamespace(raw=raw.parent, research_hub_dir=hub, clusters_file=registry)
    detect = Mock(return_value=None)
    invoke = Mock(side_effect=AssertionError("Model/provider invocation forbidden"))
    apply = Mock(side_effect=AssertionError("Destination application forbidden"))
    monkeypatch.setattr(cli_paper, "get_config", lambda: cfg)
    monkeypatch.setattr(llm_cli, "detect_llm_cli", detect)
    monkeypatch.setattr(llm_cli, "invoke_llm_cli", invoke)
    monkeypatch.setattr(summarize, "apply_summaries", apply)
    monkeypatch.setattr(llm_cli.shutil, "which", Mock(side_effect=AssertionError("Real discovery forbidden")))
    monkeypatch.setattr(llm_cli.subprocess, "Popen", Mock(side_effect=AssertionError("Child process forbidden")))
    yield cfg, detect
    invoke.assert_not_called()
    apply.assert_not_called()
    assert all(path.read_bytes() == data for path, data in before.items())


@pytest.mark.parametrize("apply", [False, True])
def test_resummarize_no_cli_reports_prompt_only_for_selected_todo_notes(isolated_cluster, apply, capsys):
    cfg, detect = isolated_cluster
    assert cli_paper._paper_resummarize("fixture-cluster", apply=apply, llm_cli=None) == 0
    detect.assert_called_once_with()
    output = capsys.readouterr()
    assert output.err == ""
    prompt = cfg.research_hub_dir / "artifacts/fixture-cluster/summarize-prompt.md"
    assert output.out.splitlines() == [
        f"no LLM CLI on PATH; prompt saved to {prompt}",
        "Prompt-only: no summaries were generated or applied, even with --apply.",
        "An agent in this host can read the saved prompt with authorized tools and return readable abstract-based summaries.",
        "Saving them requires a separately authorized supported operation for the selected destination.",
        "If that route is unavailable, keep the readable result and report saving as pending.",
        "Re-running --apply does not import externally generated summaries.",
    ]
    text = prompt.read_text(encoding="utf-8")
    assert "Selected one synthetic abstract." in text
    assert "Selected two synthetic abstract." in text
    for excluded in ["Excluded completed", "Excluded missing key", "Excluded overview"]:
        assert excluded not in text
    assert sorted(path.relative_to(cfg.research_hub_dir).as_posix()
                  for path in cfg.research_hub_dir.rglob("*") if path.is_file()) == [
        "artifacts/fixture-cluster/summarize-prompt.md", "clusters.yaml",
    ]


@pytest.mark.parametrize("apply", [False, True])
@pytest.mark.parametrize("isolated_cluster", [True], indirect=True)
def test_resummarize_without_todo_notes_keeps_noop_exit_code(isolated_cluster, apply, capsys):
    cfg, detect = isolated_cluster
    before = {path: path.read_bytes() for path in (cfg.raw / "fixture-cluster").glob("*.md")}
    assert cli_paper._paper_resummarize("fixture-cluster", apply=apply, llm_cli=None) == 0
    detect.assert_not_called()
    assert capsys.readouterr().out == "No papers with [TODO] summary blocks found.\n"
    assert all(path.read_bytes() == data for path, data in before.items())
    assert not (cfg.research_hub_dir / "artifacts").exists()
