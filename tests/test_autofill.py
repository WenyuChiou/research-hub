from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace


def _cfg(tmp_path: Path) -> SimpleNamespace:
    root = tmp_path / "vault"
    raw = root / "raw"
    hub = root / "hub"
    research_hub_dir = root / ".research_hub"
    raw.mkdir(parents=True)
    hub.mkdir(parents=True)
    research_hub_dir.mkdir(parents=True)
    return SimpleNamespace(
        root=root,
        raw=raw,
        hub=hub,
        research_hub_dir=research_hub_dir,
        clusters_file=research_hub_dir / "clusters.yaml",
    )


def _write_note(
    cfg,
    slug: str,
    *,
    summary: str = "[TODO: fill from abstract]",
    key_findings: str = "- [TODO: fill from abstract]",
    methodology: str = "[TODO: fill from abstract]",
    relevance: str = "[TODO: fill from abstract]",
    abstract: str = "This paper studies agent evaluation.",
    related: str = "## Related Papers in This Cluster\n\n- [[other-paper]]\n",
) -> Path:
    note_dir = cfg.raw / "agents"
    note_dir.mkdir(parents=True, exist_ok=True)
    path = note_dir / f"{slug}.md"
    path.write_text(
        (
            "---\n"
            f'title: "{slug.title()}"\n'
            f'doi: "10.1/{slug}"\n'
            'topic_cluster: "agents"\n'
            "---\n\n"
            "## Abstract\n"
            f"{abstract}\n\n"
            "## Summary\n\n"
            f"{summary}\n\n"
            "## Key Findings\n\n"
            f"{key_findings}\n\n"
            "## Methodology\n\n"
            f"{methodology}\n\n"
            "## Relevance\n\n"
            f"{relevance}\n\n"
            f"{related}"
        ),
        encoding="utf-8",
    )
    return path


def test_find_todo_papers_detects_todo_marker(tmp_path):
    from research_hub.autofill import find_todo_papers

    cfg = _cfg(tmp_path)
    _write_note(cfg, "paper-one")

    papers = find_todo_papers(cfg, "agents")

    assert [paper.slug for paper in papers] == ["paper-one"]


def test_find_todo_papers_skips_papers_with_real_content(tmp_path):
    from research_hub.autofill import find_todo_papers

    cfg = _cfg(tmp_path)
    _write_note(
        cfg,
        "paper-one",
        summary="Real summary.",
        key_findings="- Finding",
        methodology="Real method.",
        relevance="Real relevance.",
    )

    assert find_todo_papers(cfg, "agents") == []


def test_find_todo_papers_skips_papers_without_abstract(tmp_path):
    from research_hub.autofill import find_todo_papers

    cfg = _cfg(tmp_path)
    _write_note(cfg, "paper-one", abstract="(no abstract)")

    assert find_todo_papers(cfg, "agents") == []


def test_find_todo_papers_skips_overview_and_index_files(tmp_path):
    from research_hub.autofill import find_todo_papers

    cfg = _cfg(tmp_path)
    _write_note(cfg, "paper-one")
    _write_note(cfg, "00_overview")
    _write_note(cfg, "index")

    papers = find_todo_papers(cfg, "agents")

    assert [paper.slug for paper in papers] == ["paper-one"]


def test_emit_autofill_prompt_lists_all_todo_papers(tmp_path):
    from research_hub.autofill import emit_autofill_prompt

    cfg = _cfg(tmp_path)
    _write_note(cfg, "paper-one")
    _write_note(cfg, "paper-two")

    prompt = emit_autofill_prompt(cfg, "agents")

    assert "paper-one" in prompt
    assert "paper-two" in prompt
    assert "## Papers to autofill (2 total)" in prompt


def test_emit_autofill_prompt_empty_cluster_message(tmp_path):
    from research_hub.autofill import emit_autofill_prompt

    cfg = _cfg(tmp_path)

    prompt = emit_autofill_prompt(cfg, "agents")

    assert "No papers need autofill" in prompt


def test_apply_autofill_fills_sections(tmp_path):
    from research_hub.autofill import apply_autofill

    cfg = _cfg(tmp_path)
    path = _write_note(cfg, "paper-one")

    result = apply_autofill(
        cfg,
        "agents",
        {
            "papers": [
                {
                    "slug": "paper-one",
                    "summary": "Filled summary.",
                    "key_findings": ["A", "B"],
                    "methodology": "Filled method.",
                    "relevance": "Filled relevance.",
                }
            ]
        },
    )

    text = path.read_text(encoding="utf-8")
    assert result.filled == ["paper-one"]
    assert "Filled summary." in text
    assert "- A" in text
    assert "Filled method." in text
    assert "Filled relevance." in text


def test_apply_autofill_preserves_frontmatter_and_abstract(tmp_path):
    from research_hub.autofill import apply_autofill

    cfg = _cfg(tmp_path)
    path = _write_note(cfg, "paper-one", abstract="Original abstract.")
    original = path.read_text(encoding="utf-8")

    apply_autofill(
        cfg,
        "agents",
        [{"slug": "paper-one", "summary": "Filled", "key_findings": ["A"], "methodology": "M", "relevance": "R"}],
    )

    text = path.read_text(encoding="utf-8")
    assert 'title: "Paper-One"' in text
    assert "## Abstract\nOriginal abstract." in text
    assert original.startswith("---\n")


def test_apply_autofill_preserves_related_papers_section(tmp_path):
    from research_hub.autofill import apply_autofill

    cfg = _cfg(tmp_path)
    path = _write_note(cfg, "paper-one")

    apply_autofill(
        cfg,
        "agents",
        [{"slug": "paper-one", "summary": "Filled", "key_findings": ["A"], "methodology": "M", "relevance": "R"}],
    )

    text = path.read_text(encoding="utf-8")
    assert "## Related Papers in This Cluster" in text
    assert "- [[other-paper]]" in text


def test_apply_autofill_missing_slug_recorded(tmp_path):
    from research_hub.autofill import apply_autofill

    cfg = _cfg(tmp_path)

    result = apply_autofill(cfg, "agents", [{"slug": "missing", "summary": "Filled"}])

    assert result.missing == ["missing"]


def test_apply_autofill_skips_empty_content_entries(tmp_path):
    from research_hub.autofill import apply_autofill

    cfg = _cfg(tmp_path)
    _write_note(cfg, "paper-one")

    result = apply_autofill(cfg, "agents", [{"slug": "paper-one"}])

    assert result.skipped == ["paper-one"]


def test_cli_autofill_emit_writes_prompt_file(tmp_path, monkeypatch):
    from research_hub import cli

    cfg = _cfg(tmp_path)
    _write_note(cfg, "paper-one")
    out = tmp_path / "prompt.md"
    monkeypatch.setattr(cli, "get_config", lambda: cfg)

    rc = cli.main(["autofill", "emit", "--cluster", "agents", "--out", str(out)])

    assert rc == 0
    assert "paper-one" in out.read_text(encoding="utf-8")


def test_cli_autofill_apply_updates_note(tmp_path, monkeypatch):
    from research_hub import cli

    cfg = _cfg(tmp_path)
    path = _write_note(cfg, "paper-one")
    scored = tmp_path / "autofill.json"
    scored.write_text(
        json.dumps(
            {
                "papers": [
                    {
                        "slug": "paper-one",
                        "summary": "CLI summary.",
                        "key_findings": ["A"],
                        "methodology": "CLI method.",
                        "relevance": "CLI relevance.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "get_config", lambda: cfg)

    rc = cli.main(["autofill", "apply", "--cluster", "agents", "--scored", str(scored)])

    assert rc == 0
    assert "CLI summary." in path.read_text(encoding="utf-8")


def test_mcp_autofill_emit_returns_prompt_and_count(tmp_path, monkeypatch):
    from tests._mcp_helpers import _get_mcp_tool
    from research_hub.mcp_server import mcp

    cfg = _cfg(tmp_path)
    _write_note(cfg, "paper-one")
    monkeypatch.setattr("research_hub.config.get_config", lambda: cfg)

    result = _get_mcp_tool(mcp, "autofill_emit").fn("agents")

    assert result["paper_count"] == 1
    assert "paper-one" in result["prompt"]


def test_mcp_autofill_apply_returns_result_payload(tmp_path, monkeypatch):
    from tests._mcp_helpers import _get_mcp_tool
    from research_hub.mcp_server import mcp

    cfg = _cfg(tmp_path)
    _write_note(cfg, "paper-one")
    monkeypatch.setattr("research_hub.config.get_config", lambda: cfg)

    result = _get_mcp_tool(mcp, "autofill_apply").fn(
        "agents",
        [{"slug": "paper-one", "summary": "MCP summary.", "key_findings": ["A"], "methodology": "M", "relevance": "R"}],
    )

    assert result["filled"] == ["paper-one"]


def test_apply_autofill_accepts_top_level_list_payload(tmp_path):
    from research_hub.autofill import apply_autofill

    cfg = _cfg(tmp_path)
    path = _write_note(cfg, "paper-one")

    result = apply_autofill(
        cfg,
        "agents",
        [{"slug": "paper-one", "summary": "List summary.", "key_findings": ["A"], "methodology": "M", "relevance": "R"}],
    )

    assert result.filled == ["paper-one"]
    assert "List summary." in path.read_text(encoding="utf-8")
