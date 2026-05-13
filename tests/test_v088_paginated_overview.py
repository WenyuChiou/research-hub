from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from research_hub.vault import hub_overview
from research_hub.vault.hub_overview import (
    OVERVIEW_FILENAME,
    PAPERS_BY_YEAR_FILENAME,
    _render_papers_by_year_sidecar,
    populate_overview,
)


def _write_paper(
    vault: Path,
    slug: str,
    stem: str,
    *,
    title: str,
    year: int,
    ingested_at: str = "2026-05-13T00:00:00Z",
    authors: str = "Author, A.",
    fit_score: int | None = None,
) -> None:
    raw = vault / "raw" / slug
    raw.mkdir(parents=True, exist_ok=True)
    fit_line = f"fit_score: {fit_score}\n" if fit_score is not None else ""
    (raw / f"{stem}.md").write_text(
        f"""---
title: "{title}"
authors: "{authors}"
year: {year}
ingested_at: "{ingested_at}"
{fit_line}---

# {title}
""",
        encoding="utf-8",
    )


def _write_many_papers(vault: Path, slug: str, count: int) -> None:
    base = datetime(2026, 5, 13, tzinfo=timezone.utc)
    for index in range(count):
        ts = (base - timedelta(minutes=index)).strftime("%Y-%m-%dT%H:%M:%SZ")
        _write_paper(
            vault,
            slug,
            f"paper-{index:03d}",
            title=f"Paper {index:03d}",
            year=2026 - (index // 50),
            ingested_at=ts,
            authors=f"Author {index:03d}, A.",
            fit_score=index,
        )


def _section(text: str, heading: str) -> str:
    marker = f"## {heading}"
    start = text.index(marker) + len(marker)
    next_heading = text.find("\n## ", start)
    end = next_heading if next_heading != -1 else len(text)
    return text[start:end].strip()


def _subsection(text: str, heading: str) -> str:
    marker = f"### {heading}"
    start = text.index(marker) + len(marker)
    next_positions = [
        pos
        for pos in (
            text.find("\n### ", start),
            text.find("\nFull list by year:", start),
            text.find("\n> [!details]", start),
        )
        if pos != -1
    ]
    end = min(next_positions) if next_positions else len(text)
    return text[start:end].strip()


def _plain_bullet_count(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.startswith("- [["))


def _marker(vault: Path, slug: str) -> dict:
    path = vault / ".research_hub" / "clusters" / f"{slug}.rebuild_marker.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_zero_papers_keeps_flat_empty_behavior(tmp_path: Path) -> None:
    path = populate_overview(cluster_slug="demo", vault_root=tmp_path)

    papers = _section(path.read_text(encoding="utf-8"), "Papers in this cluster")
    assert "(no papers found)" in papers
    assert "Most-cited" not in papers
    assert "> [!details]" not in papers
    assert not (tmp_path / "hub" / "demo" / PAPERS_BY_YEAR_FILENAME).exists()


def test_31_papers_render_recent_fit_collapsible_and_sidecar_link(tmp_path: Path) -> None:
    _write_many_papers(tmp_path, "demo", 31)

    path = populate_overview(cluster_slug="demo", vault_root=tmp_path)
    papers = _section(path.read_text(encoding="utf-8"), "Papers in this cluster")

    recent = _subsection(papers, "Recent (top 12)")
    assert _plain_bullet_count(recent) == 12
    assert "[[paper-000]]" in recent
    assert "[[paper-012]]" not in recent

    fit = _subsection(papers, "Most-cited (top 20 by fit score)")
    assert _plain_bullet_count(fit) == 20
    assert "[[paper-030]]" in fit
    assert "[[paper-010]]" not in fit

    assert "[[01_papers_by_year|Papers by year]]" in papers
    assert "> [!details]- Full list (31 papers)" in papers
    assert "> - [[paper-000]]" in papers
    assert "> - [[paper-030]]" in papers


@pytest.mark.parametrize("count", [31, 200])
def test_paginated_overview_structure_scales_past_threshold(tmp_path: Path, count: int) -> None:
    _write_many_papers(tmp_path, "demo", count)

    path = populate_overview(cluster_slug="demo", vault_root=tmp_path)
    papers = _section(path.read_text(encoding="utf-8"), "Papers in this cluster")

    assert _plain_bullet_count(_subsection(papers, "Recent (top 12)")) == 12
    assert _plain_bullet_count(_subsection(papers, "Most-cited (top 20 by fit score)")) == 20
    assert f"> [!details]- Full list ({count} papers)" in papers
    assert (tmp_path / "hub" / "demo" / PAPERS_BY_YEAR_FILENAME).exists()


def test_sidecar_file_written_when_over_threshold(tmp_path: Path) -> None:
    _write_many_papers(tmp_path, "demo", 31)

    populate_overview(cluster_slug="demo", vault_root=tmp_path)

    sidecar = tmp_path / "hub" / "demo" / PAPERS_BY_YEAR_FILENAME
    assert sidecar.exists()
    text = sidecar.read_text(encoding="utf-8")
    assert "type: papers-by-year" in text
    assert "total_papers: 31" in text
    assert "- [[paper-000|Paper 000]]" in text


def test_sidecar_groups_by_year_desc(tmp_path: Path) -> None:
    for index, year in enumerate([2024, 2026, 2025, 2026]):
        _write_paper(
            tmp_path,
            "demo",
            f"paper-{index}",
            title=f"Paper {index}",
            year=year,
            ingested_at=f"{year}-01-01T00:00:00Z",
        )

    sidecar = _render_papers_by_year_sidecar(tmp_path, "demo")
    text = sidecar.read_text(encoding="utf-8")

    assert text.index("## 2026 (2 papers)") < text.index("## 2025 (1 papers)")
    assert text.index("## 2025 (1 papers)") < text.index("## 2024 (1 papers)")


def test_sidecar_is_idempotent(tmp_path: Path) -> None:
    _write_many_papers(tmp_path, "demo", 31)

    sidecar = _render_papers_by_year_sidecar(tmp_path, "demo")
    first = sidecar.read_bytes()
    _render_papers_by_year_sidecar(tmp_path, "demo")

    assert sidecar.read_bytes() == first


def test_debounce_marker_increments_on_tiny_adds(tmp_path: Path) -> None:
    _write_many_papers(tmp_path, "demo", 31)
    overview = populate_overview(cluster_slug="demo", vault_root=tmp_path)
    before = overview.read_bytes()

    _write_paper(
        tmp_path,
        "demo",
        "new-paper",
        title="New Paper",
        year=2030,
        ingested_at="2030-01-01T00:00:00Z",
    )
    populate_overview(cluster_slug="demo", vault_root=tmp_path)

    assert overview.read_bytes() == before
    marker = _marker(tmp_path, "demo")
    assert marker["last_rebuild_paper_count"] == 31
    assert marker["since_last_rebuild"] == 1


def test_force_rebuild_bypasses_debounce(tmp_path: Path) -> None:
    _write_many_papers(tmp_path, "demo", 31)
    overview = populate_overview(cluster_slug="demo", vault_root=tmp_path)

    _write_paper(
        tmp_path,
        "demo",
        "new-paper",
        title="Newest Paper",
        year=2030,
        ingested_at="2030-01-01T00:00:00Z",
    )
    populate_overview(cluster_slug="demo", vault_root=tmp_path, force_rebuild=True)

    assert "Newest Paper" in overview.read_text(encoding="utf-8")
    marker = _marker(tmp_path, "demo")
    assert marker["last_rebuild_paper_count"] == 32
    assert marker["since_last_rebuild"] == 0


def test_cli_rebuild_overviews_force_threads_to_populator(monkeypatch) -> None:
    import research_hub.cli as cli

    calls: dict[str, object] = {}

    def fake_populate_all_overviews(cfg, *, cluster_slug_filter=None, force_rebuild=False):
        calls["cfg"] = cfg
        calls["cluster_slug_filter"] = cluster_slug_filter
        calls["force_rebuild"] = force_rebuild
        return [("demo", Path("overview.md"))]

    cfg = SimpleNamespace(root=Path("vault"), clusters_file=Path("clusters.yaml"))
    monkeypatch.setattr(cli, "get_config", lambda: cfg)
    monkeypatch.setattr(hub_overview, "populate_all_overviews", fake_populate_all_overviews)

    rc = cli.main(["vault", "rebuild-overviews", "--cluster", "demo", "--force"])

    assert rc == 0
    assert calls == {
        "cfg": cfg,
        "cluster_slug_filter": "demo",
        "force_rebuild": True,
    }
