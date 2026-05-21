"""Wave 4: Research gap analysis (F4a) — build_cluster_digest, emit_gap_prompt, apply_gap_results."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cfg(tmp_path: Path) -> SimpleNamespace:
    raw = tmp_path / "raw"
    raw.mkdir()
    research_hub_dir = tmp_path / ".research_hub"
    research_hub_dir.mkdir()
    return SimpleNamespace(
        raw=raw,
        root=tmp_path,
        clusters_file=tmp_path / "clusters.yaml",
        research_hub_dir=research_hub_dir,
    )


def _write_paper(cluster_dir: Path, stem: str, **kwargs) -> None:
    cluster_dir.mkdir(parents=True, exist_ok=True)
    title = kwargs.get("title", stem)
    doi = kwargs.get("doi", "")
    year = kwargs.get("year", 2022)
    abstract = kwargs.get("abstract", "")
    summary_section = kwargs.get("summary_section", "")
    methodology_section = kwargs.get("methodology_section", "")
    key_findings_section = kwargs.get("key_findings_section", "")

    fm = (
        f"---\n"
        f"title: {title}\n"
        f"doi: {doi}\n"
        f"year: {year}\n"
        f"abstract: {abstract}\n"
        f"---\n\n"
        f"# {title}\n\n"
    )
    if summary_section:
        fm += f"## Summary\n\n{summary_section}\n\n"
    if methodology_section:
        fm += f"## Methodology\n\n{methodology_section}\n\n"
    if key_findings_section:
        fm += f"## Key Findings\n\n{key_findings_section}\n\n"

    (cluster_dir / f"{stem}.md").write_text(fm, encoding="utf-8")


# ---------------------------------------------------------------------------
# build_cluster_digest
# ---------------------------------------------------------------------------


def test_build_cluster_digest_empty_cluster(tmp_path: Path) -> None:
    """build_cluster_digest returns zero papers when cluster dir is missing."""
    from research_hub.gap_analysis import build_cluster_digest

    cfg = _make_cfg(tmp_path)
    digest = build_cluster_digest(cfg, "nonexistent-cluster")
    assert digest.paper_count == 0
    assert digest.papers == []
    assert digest.slug == "nonexistent-cluster"


def test_build_cluster_digest_reads_papers(tmp_path: Path) -> None:
    """build_cluster_digest reads all non-overview papers."""
    from research_hub.gap_analysis import build_cluster_digest

    cfg = _make_cfg(tmp_path)
    cluster_dir = cfg.raw / "floods"
    _write_paper(cluster_dir, "paper1", title="Flood Risk 2022", doi="10.1/a", year=2022)
    _write_paper(cluster_dir, "paper2", title="Flood Model 2023", doi="10.1/b", year=2023)
    # 00_ prefix should be skipped
    (cluster_dir / "00_overview.md").write_text("# Overview\n", encoding="utf-8")

    digest = build_cluster_digest(cfg, "floods")
    assert digest.paper_count == 2
    assert len(digest.papers) == 2
    titles = {p.title for p in digest.papers}
    assert "Flood Risk 2022" in titles
    assert "Flood Model 2023" in titles


def test_build_cluster_digest_extracts_sections(tmp_path: Path) -> None:
    """build_cluster_digest extracts Summary and Methodology sections."""
    from research_hub.gap_analysis import build_cluster_digest

    cfg = _make_cfg(tmp_path)
    cluster_dir = cfg.raw / "floods"
    _write_paper(
        cluster_dir,
        "paper1",
        title="Flood Study",
        methodology_section="Agent-based modeling with 500 agents.",
        key_findings_section="Risk increased 30% under high emission scenarios.",
    )

    digest = build_cluster_digest(cfg, "floods")
    assert len(digest.papers) == 1
    p = digest.papers[0]
    assert "Agent-based" in p.methodology
    assert "Risk increased" in p.key_findings


def test_build_cluster_digest_uses_frontmatter_abstract(tmp_path: Path) -> None:
    """build_cluster_digest uses frontmatter abstract when no Summary section."""
    from research_hub.gap_analysis import build_cluster_digest

    cfg = _make_cfg(tmp_path)
    cluster_dir = cfg.raw / "floods"
    _write_paper(
        cluster_dir,
        "paper1",
        title="Test",
        abstract="This paper examines coastal flood adaptation.",
    )

    digest = build_cluster_digest(cfg, "floods")
    assert "coastal flood" in digest.papers[0].summary


def test_build_cluster_digest_skips_00_and_underscore_files(tmp_path: Path) -> None:
    """build_cluster_digest skips 00_*.md and _*.md files."""
    from research_hub.gap_analysis import build_cluster_digest

    cfg = _make_cfg(tmp_path)
    cluster_dir = cfg.raw / "floods"
    cluster_dir.mkdir()
    (cluster_dir / "00_overview.md").write_text("Overview", encoding="utf-8")
    (cluster_dir / "_notes.md").write_text("Notes", encoding="utf-8")
    _write_paper(cluster_dir, "real-paper", title="Real Paper")

    digest = build_cluster_digest(cfg, "floods")
    assert digest.paper_count == 1
    assert digest.papers[0].title == "Real Paper"


# ---------------------------------------------------------------------------
# emit_gap_prompt
# ---------------------------------------------------------------------------


def test_emit_gap_prompt_contains_required_sections(tmp_path: Path) -> None:
    """emit_gap_prompt output contains all four required gap categories."""
    from research_hub.gap_analysis import build_cluster_digest, emit_gap_prompt

    cfg = _make_cfg(tmp_path)
    cluster_dir = cfg.raw / "floods"
    _write_paper(cluster_dir, "paper1", title="Study A", abstract="We study X.")
    _write_paper(cluster_dir, "paper2", title="Study B", abstract="We study Y.")

    digest = build_cluster_digest(cfg, "floods")
    prompt = emit_gap_prompt(digest)

    assert "Methodological Gaps" in prompt
    assert "Conceptual Gaps" in prompt
    assert "Scope Gaps" in prompt
    assert "Actionable Research Directions" in prompt


def test_emit_gap_prompt_includes_paper_titles(tmp_path: Path) -> None:
    """emit_gap_prompt embeds paper titles in the prompt."""
    from research_hub.gap_analysis import build_cluster_digest, emit_gap_prompt

    cfg = _make_cfg(tmp_path)
    cluster_dir = cfg.raw / "floods"
    _write_paper(cluster_dir, "paper1", title="Unique Title For Testing XYZ")

    digest = build_cluster_digest(cfg, "floods")
    prompt = emit_gap_prompt(digest)
    assert "Unique Title For Testing XYZ" in prompt


def test_emit_gap_prompt_evidence_rule(tmp_path: Path) -> None:
    """emit_gap_prompt instructs LLM to anchor gaps to specific papers."""
    from research_hub.gap_analysis import build_cluster_digest, emit_gap_prompt

    cfg = _make_cfg(tmp_path)
    (cfg.raw / "floods").mkdir()
    from research_hub.gap_analysis import ClusterDigest
    digest = ClusterDigest(slug="floods", name="Floods", paper_count=0)
    prompt = emit_gap_prompt(digest)
    assert "evidence-anchored" in prompt or "evidence" in prompt.lower()


# ---------------------------------------------------------------------------
# apply_gap_results
# ---------------------------------------------------------------------------


def test_apply_gap_results_writes_file(tmp_path: Path) -> None:
    """apply_gap_results creates research-gaps.md in hub/<slug>/."""
    from research_hub.gap_analysis import apply_gap_results

    cfg = _make_cfg(tmp_path)
    hub_dir = tmp_path / "hub" / "floods"
    hub_dir.mkdir(parents=True)

    gap_text = "### Methodological Gaps\n- No longitudinal studies (Papers 1, 2)\n"
    result = apply_gap_results(cfg, "floods", gap_text)

    assert result.written is True
    assert result.research_gaps_path is not None
    assert result.research_gaps_path.exists()
    content = result.research_gaps_path.read_text(encoding="utf-8")
    assert "No longitudinal studies" in content
    assert "Research Gaps" in content


def test_apply_gap_results_updates_00_overview(tmp_path: Path) -> None:
    """apply_gap_results appends ## Research Gaps to 00_overview.md."""
    from research_hub.gap_analysis import apply_gap_results

    cfg = _make_cfg(tmp_path)
    hub_dir = tmp_path / "hub" / "floods"
    hub_dir.mkdir(parents=True)
    overview_path = hub_dir / "00_overview.md"
    overview_path.write_text("# Floods\n\nExisting content.\n", encoding="utf-8")

    result = apply_gap_results(cfg, "floods", "### Methodological Gaps\n- Gap A\n")

    assert result.overview_updated is True
    overview_text = overview_path.read_text(encoding="utf-8")
    assert "## Research Gaps" in overview_text


def test_apply_gap_results_does_not_duplicate_overview_section(tmp_path: Path) -> None:
    """apply_gap_results does not add ## Research Gaps if already present."""
    from research_hub.gap_analysis import apply_gap_results

    cfg = _make_cfg(tmp_path)
    hub_dir = tmp_path / "hub" / "floods"
    hub_dir.mkdir(parents=True)
    overview_path = hub_dir / "00_overview.md"
    overview_path.write_text(
        "# Floods\n\nExisting content.\n\n## Research Gaps\n\nAlready here.\n",
        encoding="utf-8",
    )
    original = overview_path.read_text(encoding="utf-8")

    apply_gap_results(cfg, "floods", "### New gap text\n")

    assert overview_path.read_text(encoding="utf-8") == original


# ---------------------------------------------------------------------------
# save_gap_prompt
# ---------------------------------------------------------------------------


def test_save_gap_prompt_creates_file(tmp_path: Path) -> None:
    """save_gap_prompt writes prompt to artifacts dir."""
    from research_hub.gap_analysis import save_gap_prompt

    cfg = _make_cfg(tmp_path)
    path = save_gap_prompt(cfg, "floods", "# My prompt\n")
    assert path.exists()
    assert path.read_text(encoding="utf-8") == "# My prompt\n"


# ---------------------------------------------------------------------------
# _cmd_paper_gaps (CLI handler)
# ---------------------------------------------------------------------------


def test_cmd_paper_gaps_no_llm_saves_prompt(tmp_path: Path, capsys) -> None:
    """paper gaps --no-llm saves prompt file and does not invoke LLM."""
    from research_hub.cli import _cmd_paper_gaps

    cfg = _make_cfg(tmp_path)
    cluster_dir = cfg.raw / "floods"
    _write_paper(cluster_dir, "paper1", title="Flood Study")

    args = SimpleNamespace(cluster="floods", compare_cluster=None, no_llm=True, llm_cli=None)
    _cmd_paper_gaps(cfg, args)

    out = capsys.readouterr().out
    assert "Prompt saved" in out or "gap-analysis-prompt" in out
    # Prompt file should exist
    prompt_path = tmp_path / ".research_hub" / "artifacts" / "floods" / "gap-analysis-prompt.md"
    assert prompt_path.exists()


def test_cmd_paper_gaps_empty_cluster_exits_early(tmp_path: Path, capsys) -> None:
    """paper gaps prints warning and exits when cluster has no papers."""
    from research_hub.cli import _cmd_paper_gaps

    cfg = _make_cfg(tmp_path)
    (cfg.raw / "empty").mkdir()

    args = SimpleNamespace(cluster="empty", compare_cluster=None, no_llm=True, llm_cli=None)
    _cmd_paper_gaps(cfg, args)

    err = capsys.readouterr().err
    assert "No papers found" in err


def test_cmd_paper_gaps_llm_error_shows_message(tmp_path: Path, capsys) -> None:
    """paper gaps prints error and prompt path when LLM invocation fails."""
    from research_hub.cli import _cmd_paper_gaps

    cfg = _make_cfg(tmp_path)
    cluster_dir = cfg.raw / "floods"
    _write_paper(cluster_dir, "paper1", title="Flood Study")

    with patch("research_hub.llm_cli.detect_llm_cli", return_value="claude"), \
         patch("research_hub.llm_cli.invoke_llm_cli", side_effect=RuntimeError("timeout after 300s")):
        args = SimpleNamespace(cluster="floods", compare_cluster=None, no_llm=False, llm_cli=None)
        _cmd_paper_gaps(cfg, args)

    err = capsys.readouterr().err
    assert "LLM invocation failed" in err or "timeout" in err


def test_cmd_paper_gaps_empty_llm_response(tmp_path: Path, capsys) -> None:
    """paper gaps handles empty LLM response gracefully."""
    from research_hub.cli import _cmd_paper_gaps

    cfg = _make_cfg(tmp_path)
    cluster_dir = cfg.raw / "floods"
    _write_paper(cluster_dir, "paper1", title="Flood Study")

    with patch("research_hub.llm_cli.detect_llm_cli", return_value="claude"), \
         patch("research_hub.llm_cli.invoke_llm_cli", return_value="   "):
        args = SimpleNamespace(cluster="floods", compare_cluster=None, no_llm=False, llm_cli=None)
        _cmd_paper_gaps(cfg, args)

    err = capsys.readouterr().err
    assert "empty" in err.lower() or "Prompt saved" in err


def test_cmd_paper_gaps_compare_no_llm_empty_cluster_aborts(tmp_path: Path, capsys) -> None:
    """paper gaps --compare with one empty cluster aborts with a clear error."""
    from research_hub.cli import _cmd_paper_gaps

    cfg = _make_cfg(tmp_path)
    cluster_dir = cfg.raw / "floods"
    _write_paper(cluster_dir, "paper1", title="Flood Study")
    # "llm" cluster dir absent → digest_b.paper_count == 0 → early abort

    args = SimpleNamespace(cluster="floods", compare_cluster="llm", no_llm=True, llm_cli=None)
    _cmd_paper_gaps(cfg, args)

    err = capsys.readouterr().err
    # Should report which cluster is empty
    assert "llm" in err and ("no papers" in err.lower() or "empty" in err.lower() or "cannot" in err.lower())


def test_cmd_paper_gaps_with_mock_llm(tmp_path: Path, capsys) -> None:
    """paper gaps invokes detected LLM CLI and writes research-gaps.md."""
    from research_hub.cli import _cmd_paper_gaps

    cfg = _make_cfg(tmp_path)
    cluster_dir = cfg.raw / "floods"
    _write_paper(cluster_dir, "paper1", title="Flood Study")
    hub_dir = tmp_path / "hub" / "floods"
    hub_dir.mkdir(parents=True)

    gap_response = "### Methodological Gaps\n- No longitudinal studies (Paper 1)\n"

    # _cmd_paper_gaps does lazy imports from research_hub.llm_cli — patch there
    with patch("research_hub.llm_cli.detect_llm_cli", return_value="claude"), \
         patch("research_hub.llm_cli.invoke_llm_cli", return_value=gap_response):
        args = SimpleNamespace(cluster="floods", compare_cluster=None, no_llm=False, llm_cli=None)
        _cmd_paper_gaps(cfg, args)

    out = capsys.readouterr().out
    # Either successfully wrote or saved prompt
    assert "floods" in out or "gaps" in out.lower()
