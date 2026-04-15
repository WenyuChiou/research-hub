from __future__ import annotations

from pathlib import Path

from research_hub.dashboard.sections import LibrarySection
from research_hub.dashboard.types import ClusterCard, DashboardData, PaperRow


def _data(tmp_path: Path, **overrides) -> DashboardData:
    base = DashboardData(
        vault_root=str(tmp_path / "vault"),
        generated_at="2026-04-15T12:00:00Z",
        persona="researcher",
        total_papers=0,
        total_clusters=0,
        papers_this_week=0,
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def _paper(slug: str, title: str | None = None) -> PaperRow:
    return PaperRow(
        slug=slug,
        title=title or slug.replace("-", " ").title(),
        authors="Doe, J.",
        year="2025",
        abstract="Compact abstract.",
        doi=f"10.1000/{slug}",
        obsidian_path=f"raw/agents/{slug}.md",
        zotero_key=slug.upper(),
        bibtex=f"@article{{{slug}}}",
    )


def _cluster(papers: list[PaperRow]) -> ClusterCard:
    return ClusterCard(
        slug="agents",
        name="Agents",
        papers=papers,
        zotero_collection_key="ZK123",
        notebooklm_notebook="Agents Notebook",
        notebooklm_notebook_url="https://example.com/notebook",
    )


def _write_subtopic(vault_root: Path, filename: str, title: str, members: list[str], paper_count: int | None = None) -> None:
    topics_dir = vault_root / "raw" / "agents" / "topics"
    topics_dir.mkdir(parents=True, exist_ok=True)
    papers = "\n".join(f"- [[{slug}]]" for slug in members)
    count = len(members) if paper_count is None else paper_count
    (topics_dir / filename).write_text(
        "---\n"
        f'subtopic_slug: "{filename.split("_", 1)[-1].removesuffix(".md")}"\n'
        f'subtopic_title: "{title}"\n'
        f'papers: "{count}"\n'
        "---\n\n"
        "## Papers\n"
        f"{papers}\n",
        encoding="utf-8",
    )


def test_library_section_renders_subtopics_when_present(tmp_path: Path):
    vault_root = tmp_path / "vault"
    _write_subtopic(vault_root, "01_methods.md", "Methods", ["paper-1", "paper-2", "paper-3"])
    _write_subtopic(vault_root, "02_eval.md", "Evaluation", ["paper-4", "paper-5", "paper-6"])
    papers = [_paper(f"paper-{index}") for index in range(1, 7)]

    html = LibrarySection().render(
        _data(tmp_path, clusters=[_cluster(papers)], total_clusters=1, total_papers=6)
    )

    assert html.count('class="subtopic-card"') == 2
    assert "Methods &middot; 3 papers" in html
    assert "Evaluation &middot; 3 papers" in html


def test_library_section_falls_back_to_flat_when_no_subtopics(tmp_path: Path):
    html = LibrarySection().render(
        _data(tmp_path, clusters=[_cluster([_paper("paper-1"), _paper("paper-2")])], total_clusters=1, total_papers=2)
    )

    assert 'class="paper-list"' in html
    assert 'class="subtopic-card"' not in html


def test_library_section_unassigned_papers_in_trailing_group(tmp_path: Path):
    vault_root = tmp_path / "vault"
    _write_subtopic(vault_root, "01_methods.md", "Methods", ["paper-1", "paper-2"])
    papers = [_paper("paper-1"), _paper("paper-2"), _paper("paper-3")]

    html = LibrarySection().render(
        _data(tmp_path, clusters=[_cluster(papers)], total_clusters=1, total_papers=3)
    )

    assert "Unassigned &middot; 1 papers" in html
    assert "Paper 3" in html


def test_library_section_subtopic_paper_count_matches_display(tmp_path: Path):
    vault_root = tmp_path / "vault"
    _write_subtopic(vault_root, "01_methods.md", "Methods", ["paper-1", "paper-2", "missing-paper"], paper_count=5)
    papers = [_paper("paper-1"), _paper("paper-2"), _paper("paper-3")]

    html = LibrarySection().render(
        _data(tmp_path, clusters=[_cluster(papers)], total_clusters=1, total_papers=3)
    )

    assert "Methods &middot; 2 papers" in html
    assert "Methods &middot; 5 papers" not in html


def test_load_subtopics_returns_empty_for_missing_topics_dir(tmp_path: Path):
    section = LibrarySection()

    assert section._load_subtopics_for_cluster(str(tmp_path / "vault"), "agents") == []
