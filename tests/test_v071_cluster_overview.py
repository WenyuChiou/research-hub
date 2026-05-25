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
    # Mirror the Chinese scaffold in src/research_hub/topic.py (≈line 29).
    # If you change the placeholder there, change it here too — the marker
    # constant _CHINESE_TEMPLATE_MARKER in cluster_overview.py only
    # recognises this exact opening (一到兩句話 / "一到兩句話").
    tldr = tldr_line or "一到兩句話說清楚這個 cluster 在研究什麼、解決什麼問題。"
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

## 核心問題

> [!question]
> 用一句話寫下這個領域的中心開放問題。
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
    # No mojibake (cp950/UTF-8 round-trip residue) leaks into the output ...
    # ... and the live Chinese placeholder was actually replaced by LLM
    # content (not silently preserved as "hand-curated").
    assert "一到兩句話" not in written  # "一到兩句話"


def test_apply_overview_treats_chinese_scaffold_placeholder_as_untouched(cfg):
    """Regression: _CHINESE_TEMPLATE_MARKER must match the placeholder
    phrase topic.py actually writes for a fresh cluster (一到兩句話...).
    When it drifted into mojibake the auto-fill step silently treated
    every brand-new scaffold as "hand-curated" and never called the
    LLM, so every cluster's overview stayed at the empty template
    forever. This test pins the round-trip end to end."""
    overview_path = cfg.hub / "test-cluster" / "00_overview.md"
    overview_path.write_text(_template_text("Test Cluster", "test-cluster"), encoding="utf-8")

    result = apply_overview(cfg, "test-cluster", _valid_payload(), force=False)

    # Fresh scaffold -> placeholder -> NOT hand-curated -> write the LLM payload.
    assert result.written is True, (
        "fresh Chinese scaffold must be detected as a placeholder; if this "
        "test fails the marker in cluster_overview.py has drifted out of "
        "sync with topic.py's template (likely re-mojibaked)"
    )
    assert result.skipped is False


def test_apply_overview_treats_populate_overview_topic_string_as_scaffold(tmp_path):
    """Regression: PR #91 was half-fix. In the real `auto` flow,
    `populate_overview` (vault/hub_overview.py) runs BEFORE
    `apply_overview` (cluster_overview.py) and overwrites the Chinese
    scaffold TL;DR with the cluster's topic-string fallback ("LLM for
    flood forecasting..."). The marker `一到兩句話` then no longer
    matches, so `apply_overview` silently classified the topic string as
    "hand-curated" and never called the LLM. This test pins the
    extended scaffold check that recognises the topic-string fallback
    too."""
    from research_hub.clusters import ClusterRegistry
    raw = tmp_path / "raw" / "test-cluster"
    raw.mkdir(parents=True)
    hub_dir = tmp_path / "hub" / "test-cluster"
    hub_dir.mkdir(parents=True)
    research_hub_dir = tmp_path / ".research_hub"
    research_hub_dir.mkdir()
    clusters_file = research_hub_dir / "clusters.yaml"
    _write_paper_md(
        raw / "paper-one.md",
        "Paper One",
        "Multi-agent coordination under flood response.",
        year=2024,
    )
    ClusterRegistry(clusters_file).create(
        query="LLM for flood forecasting, warning, and decision-making",
        name="LLM Flood Cluster",
        slug="test-cluster",
    )
    cfg = SimpleNamespace(
        raw=tmp_path / "raw",
        hub=tmp_path / "hub",
        research_hub_dir=research_hub_dir,
        clusters_file=clusters_file,
    )
    overview_path = hub_dir / "00_overview.md"
    # Simulate post-populate_overview state: TL;DR = the topic string,
    # no Chinese marker.
    overview_path.write_text(
        "---\ntype: topic-overview\ncluster: test-cluster\n---\n\n"
        "# Test Cluster\n\n## TL;DR\n\n"
        "> [!abstract]\n"
        "> LLM for flood forecasting, warning, and decision-making\n"
        "^tldr\n",
        encoding="utf-8",
    )

    result = apply_overview(cfg, "test-cluster", _valid_payload(), force=False)

    # populate_overview's topic-string fallback is scaffold, NOT user content.
    assert result.written is True, (
        "topic-string fallback (populate_overview's output) must be recognised "
        "as scaffold; if this fails, _is_scaffold_tldr's cluster-query branch "
        "is broken — the LLM auto-fill won't fire in real `auto` runs"
    )
    assert result.skipped is False


def test_apply_overview_treats_english_no_summary_fallback_as_scaffold(cfg):
    """Regression: the other populate_overview fallback is the literal
    string "No cluster summary available yet." (rendered by
    `_render_tldr` when `_overview_tldr` returns an empty string). Must
    also be recognised as scaffold."""
    overview_path = cfg.hub / "test-cluster" / "00_overview.md"
    overview_path.write_text(
        "---\ntype: topic-overview\ncluster: test-cluster\n---\n\n"
        "# Test Cluster\n\n## TL;DR\n\n"
        "> [!abstract]\n"
        "> No cluster summary available yet.\n"
        "^tldr\n",
        encoding="utf-8",
    )

    result = apply_overview(cfg, "test-cluster", _valid_payload(), force=False)
    assert result.written is True
    assert result.skipped is False


def test_apply_overview_refuses_to_overwrite_filled_overview_without_force(cfg):
    overview_path = cfg.hub / "test-cluster" / "00_overview.md"
    overview_path.write_text(
        _template_text("Test Cluster", "test-cluster", tldr_line="A real English summary already exists."),
        encoding="utf-8",
    )

    result = apply_overview(cfg, "test-cluster", _valid_payload(), force=False)
    assert result.written is False
    # v0.88.9: idempotent skip is now reported as ok=True + skipped=True
    # (was ok=False with an "overwrite" error string). Auto step renders
    # this as a friendly "preserved hand-curated overview" success line
    # instead of the old false-FAIL noise.
    assert result.ok is True
    assert result.skipped is True
    assert "force=true" in result.skip_reason.lower()
    assert result.error == ""

    forced = apply_overview(cfg, "test-cluster", _valid_payload(), force=True)
    assert forced.written is True
    assert forced.skipped is False
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
    # v0.88.9: skipped + skip_reason are part of the serialised payload
    assert "skipped" in payload["apply_result"]
    assert "skip_reason" in payload["apply_result"]


def test_overview_cluster_propagates_idempotent_skip_as_ok(cfg, monkeypatch):
    """v0.88.9: when apply_overview detects hand-curated content and
    refuses to overwrite, overview_cluster (the CLI-facing wrapper)
    must propagate this as ``report.ok=True`` so the auto step renders
    it as a friendly skip, not a FAIL."""
    overview_path = cfg.hub / "test-cluster" / "00_overview.md"
    overview_path.write_text(
        _template_text(
            "Test Cluster", "test-cluster",
            tldr_line="Substantive hand-written summary the user already curated.",
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("research_hub.auto.detect_llm_cli", lambda: "claude")
    monkeypatch.setattr(
        "research_hub.auto._invoke_llm_cli",
        lambda cli, prompt: str(_valid_payload()).replace("'", '"'),
    )

    report = overview_cluster(cfg, "test-cluster", apply=True)

    assert report.ok is True, "skipped should not propagate as failure"
    assert report.error == ""
    assert report.apply_result is not None
    assert report.apply_result.skipped is True
    assert report.apply_result.written is False
    # User content must be preserved verbatim.
    assert "Substantive hand-written summary" in overview_path.read_text(encoding="utf-8")


def test_auto_run_cluster_overview_step_renders_skip_as_success(monkeypatch):
    """v0.88.9: end-to-end check that _run_cluster_overview_step logs
    the skip case as a positive step (ok=True) with a friendly detail
    line. Previously this was a noisy [FAIL] in the auto report even
    though nothing was actually broken."""
    from research_hub.auto import AutoReport, _run_cluster_overview_step

    fake_apply = OverviewApplyResult(
        cluster_slug="x",
        ok=True,
        written=False,
        skipped=True,
        skip_reason="overview already hand-curated; use force=True to overwrite",
    )

    def fake_overview_cluster(cfg, slug, *, llm_cli=None, apply=False, force=False):
        return OverviewReport(
            cluster_slug=slug,
            ok=True,
            cli_used="claude",
            apply_result=fake_apply,
        )

    monkeypatch.setattr(
        "research_hub.cluster_overview.overview_cluster",
        fake_overview_cluster,
    )

    report = AutoReport(cluster_slug="x", cluster_created=False)
    _run_cluster_overview_step(
        cfg=SimpleNamespace(),
        slug="x",
        llm_cli="claude",
        report=report,
        started=0.0,
        print_progress=False,
    )

    step = next(s for s in report.steps if s.name == "cluster_overview")
    assert step.ok is True, "idempotent skip must NOT log as FAIL"
    assert "skipped" in step.detail.lower() or "preserved" in step.detail.lower()
    assert "FAIL" not in step.detail.upper()
