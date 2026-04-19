from __future__ import annotations

from pathlib import Path
import re

from research_hub.clusters import ClusterRegistry
from research_hub.topic import (
    OVERVIEW_TEMPLATE,
    SUBTOPIC_TEMPLATE,
    apply_assignments,
    build_subtopic_notes,
    scaffold_overview,
)


class StubConfig:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.raw = root / "raw"
        self.hub = root / "hub"
        self.research_hub_dir = root / ".research_hub"
        self.clusters_file = self.research_hub_dir / "clusters.yaml"
        self.raw.mkdir(parents=True, exist_ok=True)
        self.hub.mkdir(parents=True, exist_ok=True)
        self.research_hub_dir.mkdir(parents=True, exist_ok=True)


def _cfg(tmp_path: Path) -> StubConfig:
    cfg = StubConfig(tmp_path / "vault")
    ClusterRegistry(cfg.clusters_file).create(query="my cluster", name="My Cluster", slug="my-cluster")
    overview = cfg.hub / "my-cluster" / "00_overview.md"
    if overview.exists():
        overview.unlink()
    return cfg


def _write_paper(cfg: StubConfig, slug: str, *, title: str, subtopics: list[str]) -> Path:
    note_dir = cfg.raw / "my-cluster"
    note_dir.mkdir(parents=True, exist_ok=True)
    path = note_dir / f"{slug}.md"
    path.write_text(
        (
            "---\n"
            f'title: "{title}"\n'
            'authors: "Doe, Jane"\n'
            'year: "2025"\n'
            f'doi: "10.1/{slug}"\n'
            'topic_cluster: "my-cluster"\n'
            'status: "unread"\n'
            'ingested_at: "2026-04-14T00:00:00Z"\n'
            "subtopics:\n"
            + "".join(f"  - {item}\n" for item in subtopics)
            + "---\n\n"
            "## Abstract\n"
            f"Abstract for {slug}.\n\n"
            "## Summary\n"
            f"Summary for {slug}.\n\n"
            "## Key Findings\n"
            f"- Finding for {slug}.\n\n"
            "## Methodology\n"
            f"Methodology for {slug}.\n\n"
            "## Relevance\n"
            f"Relevance for {slug}.\n"
        ),
        encoding="utf-8",
    )
    return path


def _subtopic_sections() -> list[str]:
    return [heading for heading in re.findall(r"^##\s+(.+?)\s*$", SUBTOPIC_TEMPLATE, re.MULTILINE) if heading != "Papers"]


def _replace_section(path: Path, heading: str, content: str) -> None:
    text = path.read_text(encoding="utf-8")
    start = text.index(f"## {heading}")
    next_heading = text.find("\n## ", start + 1)
    end = next_heading + 1 if next_heading != -1 else len(text)
    replacement = f"## {heading}\n\n{content}\n\n"
    path.write_text(text[:start] + replacement + text[end:], encoding="utf-8")


def _write_markers(path: Path) -> dict[str, str]:
    markers: dict[str, str] = {}
    slug = path.stem
    for section in _subtopic_sections():
        marker = f"MARKER_{slug}_{len(markers)}"
        _replace_section(path, section, marker)
        markers[section] = marker
    return markers


def test_apply_assignments_then_build_preserves_structured_content(tmp_path):
    cfg = _cfg(tmp_path)
    _write_paper(cfg, "paper-a", title="Paper A", subtopics=["alpha"])
    _write_paper(cfg, "paper-b", title="Paper B", subtopics=["alpha"])
    _write_paper(cfg, "paper-c", title="Paper C", subtopics=["beta"])
    _write_paper(cfg, "paper-d", title="Paper D", subtopics=["beta"])
    _write_paper(cfg, "paper-e", title="Paper E", subtopics=["alpha", "beta"])

    build_subtopic_notes(cfg, "my-cluster")

    markers_by_file: dict[Path, dict[str, str]] = {}
    for path in sorted((cfg.raw / "my-cluster" / "topics").glob("*.md")):
        markers_by_file[path] = _write_markers(path)

    build_subtopic_notes(cfg, "my-cluster")

    for path, markers in markers_by_file.items():
        text = path.read_text(encoding="utf-8")
        for marker in markers.values():
            assert marker in text


def test_subtopic_reassignment_during_rebuild(tmp_path):
    cfg = _cfg(tmp_path)
    _write_paper(cfg, "paper-a", title="Paper A", subtopics=["alpha"])
    _write_paper(cfg, "paper-b", title="Paper B", subtopics=["alpha"])
    _write_paper(cfg, "paper-c", title="Paper C", subtopics=["beta"])

    build_subtopic_notes(cfg, "my-cluster")
    alpha = cfg.raw / "my-cluster" / "topics" / "01_alpha.md"
    beta = cfg.raw / "my-cluster" / "topics" / "02_beta.md"
    alpha_markers = _write_markers(alpha)
    beta_markers = _write_markers(beta)

    apply_assignments(cfg, "my-cluster", {"paper-a": ["beta"], "paper-b": ["alpha"], "paper-c": ["beta"]})
    build_subtopic_notes(cfg, "my-cluster")

    alpha_text = alpha.read_text(encoding="utf-8")
    beta_text = beta.read_text(encoding="utf-8")
    for marker in alpha_markers.values():
        assert marker in alpha_text
    for marker in beta_markers.values():
        assert marker in beta_text
    assert "[[paper-a|" not in alpha_text
    assert "[[paper-a|" in beta_text
    assert "[[paper-b|" in alpha_text
    assert "[[paper-c|" in beta_text


def test_subtopic_paper_count_updates_in_frontmatter(tmp_path):
    cfg = _cfg(tmp_path)
    _write_paper(cfg, "paper-a", title="Paper A", subtopics=["alpha"])

    build_subtopic_notes(cfg, "my-cluster")
    path = cfg.raw / "my-cluster" / "topics" / "01_alpha.md"
    assert "papers: 1" in path.read_text(encoding="utf-8")

    _write_paper(cfg, "paper-b", title="Paper B", subtopics=["alpha"])
    build_subtopic_notes(cfg, "my-cluster")

    assert "papers: 2" in path.read_text(encoding="utf-8")


def test_scaffold_produces_structured_template(tmp_path):
    cfg = _cfg(tmp_path)

    path = scaffold_overview(cfg, "my-cluster")
    text = path.read_text(encoding="utf-8")

    for heading in re.findall(r"^##\s+(.+?)\s*$", OVERVIEW_TEMPLATE, re.MULTILINE):
        assert f"## {heading}" in text
    assert "## Scope" not in text
