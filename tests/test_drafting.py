from __future__ import annotations

from pathlib import Path

import pytest

from research_hub.drafting import DraftRequest, DraftingError, compose_draft, compose_draft_from_cli
from research_hub.writing import Quote, save_quote


class StubConfig:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.raw = root / "raw"
        self.research_hub_dir = root / ".research_hub"
        self.clusters_file = self.research_hub_dir / "clusters.yaml"


def _cfg(tmp_path: Path) -> StubConfig:
    cfg = StubConfig(tmp_path / "vault")
    cfg.raw.mkdir(parents=True)
    cfg.research_hub_dir.mkdir(parents=True)
    cfg.clusters_file.write_text(
        "- slug: agents\n  name: Agents\n- slug: policy\n  name: Policy\n",
        encoding="utf-8",
    )
    return cfg


def _note(
    cfg: StubConfig,
    slug: str,
    *,
    title: str,
    authors: str,
    year: str,
    doi: str,
    cluster: str = "agents",
) -> Path:
    note_dir = cfg.raw / cluster
    note_dir.mkdir(parents=True, exist_ok=True)
    path = note_dir / f"{slug}.md"
    path.write_text(
        f"""---
title: "{title}"
authors: "{authors}"
year: "{year}"
doi: "{doi}"
topic_cluster: "{cluster}"
status: "cited"
---
Body
""",
        encoding="utf-8",
    )
    return path


def _quote(
    cfg: StubConfig,
    slug: str,
    *,
    page: str,
    text: str,
    context_note: str = "",
    cluster_slug: str = "agents",
    cluster_name: str = "Agents",
) -> Quote:
    quote = Quote(
        slug=slug,
        doi="",
        title="",
        authors="",
        year="",
        cluster_slug=cluster_slug,
        cluster_name=cluster_name,
        page=page,
        text=text,
        context_note=context_note,
    )
    save_quote(cfg, quote)
    return quote


def _seed_quotes(cfg: StubConfig) -> None:
    _note(cfg, "paper-one", title="Paper One", authors="Doe, Jane; Roe, Alex", year="2025", doi="10.1000/one")
    _note(cfg, "paper-two", title="Paper Two", authors="Smith, Jamie", year="2024", doi="10.1000/two")
    _note(cfg, "paper-three", title="Paper Three", authors="Taylor, Robin; Lane, Casey; Park, Drew", year="2023", doi="10.1000/three")
    _quote(cfg, "paper-one", page="12", text="Intro quote.", context_note="Introduction framing")
    _quote(cfg, "paper-two", page="4", text="Methods quote.", context_note="Methods section details")
    _quote(cfg, "paper-three", page="9", text="Results quote.", context_note="Findings and results")


def test_compose_draft_default_single_section_with_all_quotes(tmp_path):
    cfg = _cfg(tmp_path)
    _seed_quotes(cfg)

    result = compose_draft(cfg, DraftRequest(cluster_slug="agents"))

    assert result.quote_count == 3
    assert result.section_count == 1
    assert "## Notes" in result.markdown
    assert result.markdown.count("> ") >= 3


def test_compose_draft_multi_section_with_outline(tmp_path):
    cfg = _cfg(tmp_path)
    _seed_quotes(cfg)

    result = compose_draft(
        cfg,
        DraftRequest(cluster_slug="agents", outline=["Introduction", "Methods", "Findings"]),
    )

    assert result.section_count == 3
    assert "## Introduction" in result.markdown
    assert "## Methods" in result.markdown
    assert "## Findings" in result.markdown


def test_compose_draft_assigns_quotes_by_context_note_substring(tmp_path):
    cfg = _cfg(tmp_path)
    _seed_quotes(cfg)

    result = compose_draft(
        cfg,
        DraftRequest(cluster_slug="agents", outline=["Introduction", "Methods", "Findings"]),
    )

    assert "## Introduction\n\n> Intro quote." in result.markdown
    assert "## Methods\n\n> Methods quote." in result.markdown
    assert "## Findings\n\n> Results quote." in result.markdown


def test_compose_draft_unmatched_quotes_go_to_first_section(tmp_path):
    cfg = _cfg(tmp_path)
    _note(cfg, "paper-one", title="Paper One", authors="Doe, Jane", year="2025", doi="10.1000/one")
    _quote(cfg, "paper-one", page="12", text="Loose quote.", context_note="Something else entirely")

    result = compose_draft(
        cfg,
        DraftRequest(cluster_slug="agents", outline=["Introduction", "Methods"]),
    )

    assert "## Introduction\n\n> Loose quote." in result.markdown


def test_compose_draft_filter_quote_slugs_subset(tmp_path):
    cfg = _cfg(tmp_path)
    _seed_quotes(cfg)

    result = compose_draft(
        cfg,
        DraftRequest(cluster_slug="agents", quote_slugs=["paper-two"]),
    )

    assert result.quote_count == 1
    assert "Methods quote." in result.markdown
    assert "Intro quote." not in result.markdown


def test_compose_draft_style_apa_emits_author_year_inline(tmp_path):
    cfg = _cfg(tmp_path)
    _seed_quotes(cfg)

    result = compose_draft(cfg, DraftRequest(cluster_slug="agents", style="apa"))

    assert "(Doe & Roe, 2025)" in result.markdown


def test_compose_draft_style_latex_emits_bibtex_bibliography(tmp_path):
    cfg = _cfg(tmp_path)
    _seed_quotes(cfg)

    result = compose_draft(cfg, DraftRequest(cluster_slug="agents", style="latex"))

    assert "```bibtex" in result.markdown
    assert "@article{paper-one," in result.markdown
    assert "doi = {10.1000/one}" in result.markdown


def test_compose_draft_include_bibliography_false_skips_references(tmp_path):
    cfg = _cfg(tmp_path)
    _seed_quotes(cfg)

    result = compose_draft(
        cfg,
        DraftRequest(cluster_slug="agents", include_bibliography=False),
    )

    assert "## References" not in result.markdown


def test_compose_draft_writes_file_to_default_path(tmp_path):
    cfg = _cfg(tmp_path)
    _seed_quotes(cfg)

    result = compose_draft(cfg, DraftRequest(cluster_slug="agents"))

    assert result.path.exists()
    assert result.path.parent == cfg.root / "drafts"
    assert result.path.name.endswith("-agents-draft.md")


def test_compose_draft_writes_file_to_custom_out_path(tmp_path):
    cfg = _cfg(tmp_path)
    _seed_quotes(cfg)
    out_path = cfg.root / "custom" / "draft.md"

    result = compose_draft(cfg, DraftRequest(cluster_slug="agents", out_path=out_path))

    assert result.path == out_path
    assert out_path.exists()


def test_compose_draft_empty_cluster_raises_drafting_error(tmp_path):
    cfg = _cfg(tmp_path)

    with pytest.raises(DraftingError):
        compose_draft(cfg, DraftRequest(cluster_slug="agents"))


def test_compose_draft_from_cli_parses_semicolon_outline(tmp_path):
    cfg = _cfg(tmp_path)
    _seed_quotes(cfg)

    result = compose_draft_from_cli(cfg, "agents", outline="Introduction;Methods;Findings")

    assert result.section_count == 3
    assert "## Findings" in result.markdown


def test_compose_draft_from_cli_parses_comma_quote_slugs(tmp_path):
    cfg = _cfg(tmp_path)
    _seed_quotes(cfg)

    result = compose_draft_from_cli(cfg, "agents", quote_slugs="paper-two,paper-three")

    assert result.quote_count == 2
    assert "Methods quote." in result.markdown
    assert "Results quote." in result.markdown
    assert "Intro quote." not in result.markdown
