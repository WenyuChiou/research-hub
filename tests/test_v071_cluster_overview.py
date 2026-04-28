"""v0.71.0 - cluster overview auto-fill."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from research_hub.cluster_overview import (
    ClusterOverview,
    OverviewApplyResult,
    OverviewReport,
    _validate_payload,
    apply_overview,
    build_overview_prompt,
    overview_cluster,
)


def _write_paper_md(path: Path, title: str, abstract: str, year: int = 2024) -> None:
    path.write_text(
        f"""---
title: "{title}"
year: {year}
doi: "10.1/{path.stem}"
---

# {title}

## Abstract

{abstract}

---

## Notes

placeholder
""",
        encoding="utf-8",
    )


def _template_text(title: str, cluster_slug: str, tldr_line: str | None = None) -> str:
    tldr = tldr_line or "銝?啣?亥店隤芣?璆?cluster ?函?蝛嗡?暻潦圾瘙箔?暻澆?憿?"
    return f"""---
type: topic-overview
cluster: {cluster_slug}
title: {title}
status: draft
---

# {title}

## TL;DR

> [!abstract]
> {tldr}
^tldr

## ?詨???

> [!question]
> ?其??亥店撖思?????銝剖??????
^core-question
"""


@pytest.fixture
def cfg(tmp_path):
    raw_cluster = tmp_path / "raw" / "test-cluster"
    raw_cluster.mkdir(parents=True)
    hub_cluster = tmp_path / "hub" / "test-cluster"
    hub_cluster.mkdir(parents=True)
    research_hub_dir = tmp_path / ".research_hub"
    research_hub_dir.mkdir()
    _write_paper_md(
        raw_cluster / "paper-one.md",
        "Paper One",
        "This paper studies multi-agent coordination under flood response with learned policies.",
        year=2024,
    )
    _write_paper_md(
        raw_cluster / "paper-two.md",
        "Paper Two",
        "This paper evaluates communication bottlenecks in LLM-driven agents for evacuation planning.",
        year=2025,
    )
    return SimpleNamespace(
        raw=tmp_path / "raw",
        hub=tmp_path / "hub",
        research_hub_dir=research_hub_dir,
    )


def _valid_payload() -> dict:
    return {
        "tldr": "This cluster studies LLM-based agents for flood response. It emphasizes coordination, planning, and operational limits.",
        "core_question": "The core question is how autonomous language agents can coordinate reliably under real-world uncertainty.",
        "scope_covers": ["Agent coordination", "Flood response planning", "Operational constraints"],
        "scope_excludes": ["General chatbot UX", "Pure hardware sensing"],
        "themes": [
            {"name": "Coordination", "summary": "Papers study how multiple agents share tasks. They focus on handoffs and bottlenecks."},
            {"name": "Planning", "summary": "Papers examine evacuation and response planning. They compare approaches under uncertainty."},
        ],
    }


def test_build_overview_prompt_includes_all_papers_with_abstracts(cfg):
    prompt = build_overview_prompt(cfg, "test-cluster")
    assert "Paper One" in prompt
    assert "Paper Two" in prompt
    assert "multi-agent coordination under flood response" in prompt
    assert "communication bottlenecks in LLM-driven agents" in prompt
    assert '"scope_covers"' in prompt
    assert '"themes"' in prompt


def test_validate_payload_rejects_missing_tldr():
    overview, reason = _validate_payload({"tldr": "", "core_question": "x", "scope_covers": [], "scope_excludes": [], "themes": []})
    assert overview is None
    assert "tldr" in reason.lower()


def test_validate_payload_rejects_themes_not_list():
    overview, reason = _validate_payload(
        {"tldr": "x", "core_question": "y", "scope_covers": [], "scope_excludes": [], "themes": "bad"}
    )
    assert overview is None
    assert "themes" in reason.lower()
    assert "list" in reason.lower()


def test_validate_payload_accepts_well_formed_payload():
    overview, reason = _validate_payload(_valid_payload())
    assert reason is None
    assert isinstance(overview, ClusterOverview)
    assert overview.tldr.startswith("This cluster studies")
    assert overview.scope_covers[0] == "Agent coordination"
    assert overview.themes[0]["name"] == "Coordination"


def test_apply_overview_preserves_frontmatter_and_anchors(cfg):
    overview_path = cfg.hub / "test-cluster" / "00_overview.md"
    original = _template_text("Test Cluster", "test-cluster")
    overview_path.write_text(original, encoding="utf-8")

    result = apply_overview(cfg, "test-cluster", _valid_payload())

    assert result.ok is True
    assert result.written is True
    written = overview_path.read_text(encoding="utf-8")
    assert written.startswith("---\ntype: topic-overview\ncluster: test-cluster\ntitle: Test Cluster\nstatus: draft\n---")
    assert "^tldr" in written
    assert "^core-question" in written
    assert "This cluster studies LLM-based agents for flood response." in written
    assert "銝?啣?亥店" not in written


def test_apply_overview_refuses_to_overwrite_filled_overview_without_force(cfg):
    overview_path = cfg.hub / "test-cluster" / "00_overview.md"
    overview_path.write_text(
        _template_text("Test Cluster", "test-cluster", tldr_line="A real English summary already exists."),
        encoding="utf-8",
    )

    result = apply_overview(cfg, "test-cluster", _valid_payload(), force=False)
    assert result.written is False
    assert result.ok is False
    assert "overwrite" in result.error.lower()

    forced = apply_overview(cfg, "test-cluster", _valid_payload(), force=True)
    assert forced.written is True
    assert "This cluster studies LLM-based agents for flood response." in overview_path.read_text(encoding="utf-8")


def test_overview_cluster_saves_prompt_when_no_llm_cli(cfg, monkeypatch):
    overview_path = cfg.hub / "test-cluster" / "00_overview.md"
    overview_path.write_text(_template_text("Test Cluster", "test-cluster"), encoding="utf-8")
    before = overview_path.read_text(encoding="utf-8")

    monkeypatch.setattr("research_hub.auto.detect_llm_cli", lambda: None)
    report = overview_cluster(cfg, "test-cluster", apply=True)

    assert report.ok is True
    assert report.prompt_path is not None
    assert report.prompt_path.exists()
    assert report.cli_used == ""
    assert overview_path.read_text(encoding="utf-8") == before


def test_overview_cluster_uses_detected_cli_and_applies(cfg, monkeypatch):
    overview_path = cfg.hub / "test-cluster" / "00_overview.md"
    overview_path.write_text(_template_text("Test Cluster", "test-cluster"), encoding="utf-8")

    monkeypatch.setattr("research_hub.auto.detect_llm_cli", lambda: "claude")
    monkeypatch.setattr("research_hub.auto._invoke_llm_cli", lambda cli, prompt: str(_valid_payload()).replace("'", '"'))

    report = overview_cluster(cfg, "test-cluster", apply=True)

    assert report.ok is True
    assert report.cli_used == "claude"
    assert report.apply_result is not None
    assert report.apply_result.written is True
    written = overview_path.read_text(encoding="utf-8")
    assert "## Core Question" in written
    assert "Agent coordination" in written


def test_overview_report_to_dict_serializes_paths():
    report = OverviewReport(
        cluster_slug="x",
        prompt_path=Path("/tmp/prompt.md"),
        apply_result=OverviewApplyResult(cluster_slug="x", overview_path=Path("/tmp/00_overview.md")),
    )
    payload = report.to_dict()
    assert payload["prompt_path"] == str(Path("/tmp/prompt.md"))
    assert payload["apply_result"]["overview_path"] == str(Path("/tmp/00_overview.md"))
