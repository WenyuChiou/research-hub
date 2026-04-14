from __future__ import annotations

from pathlib import Path

import pytest

from research_hub.clusters import ClusterRegistry


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
    return cfg


def _write_paper(cfg: StubConfig, slug: str, *, subtopics: list[str]) -> Path:
    note_dir = cfg.raw / "my-cluster"
    note_dir.mkdir(parents=True, exist_ok=True)
    path = note_dir / f"{slug}.md"
    path.write_text(
        (
            "---\n"
            f'title: "{slug}"\n'
            'authors: "Doe, Jane"\n'
            'year: "2025"\n'
            f'doi: "10.1/{slug}"\n'
            "subtopics:\n"
            + "".join(f"  - {item}\n" for item in subtopics)
            + "---\n\n"
            "## Abstract\n"
            f"Abstract for {slug}.\n\n"
            "## Summary\n"
            f"Summary for {slug}.\n"
        ),
        encoding="utf-8",
    )
    return path


def _replace_section(path: Path, heading: str, content: str) -> None:
    text = path.read_text(encoding="utf-8")
    start = text.index(f"## {heading}")
    next_heading = text.find("\n## ", start + 1)
    end = next_heading + 1 if next_heading != -1 else len(text)
    replacement = f"## {heading}\n\n{content}\n\n"
    path.write_text(text[:start] + replacement + text[end:], encoding="utf-8")


def test_write_papers_section_preserves_scope_across_rebuild(tmp_path):
    from research_hub.topic import build_subtopic_notes

    cfg = _cfg(tmp_path)
    _write_paper(cfg, "paper-one", subtopics=["benchmarks"])
    build_subtopic_notes(cfg, "my-cluster")
    path = cfg.raw / "my-cluster" / "topics" / "01_benchmarks.md"
    _replace_section(path, "範圍", "Custom scope paragraph.")

    build_subtopic_notes(cfg, "my-cluster")

    assert "Custom scope paragraph." in path.read_text(encoding="utf-8")


def test_write_papers_section_preserves_core_question_across_rebuild(tmp_path):
    from research_hub.topic import build_subtopic_notes

    cfg = _cfg(tmp_path)
    _write_paper(cfg, "paper-one", subtopics=["benchmarks"])
    build_subtopic_notes(cfg, "my-cluster")
    path = cfg.raw / "my-cluster" / "topics" / "01_benchmarks.md"
    _replace_section(path, "核心問題", "Custom core question.")

    build_subtopic_notes(cfg, "my-cluster")

    assert "Custom core question." in path.read_text(encoding="utf-8")


def test_write_papers_section_preserves_open_questions_across_rebuild(tmp_path):
    from research_hub.topic import build_subtopic_notes

    cfg = _cfg(tmp_path)
    _write_paper(cfg, "paper-one", subtopics=["benchmarks"])
    build_subtopic_notes(cfg, "my-cluster")
    path = cfg.raw / "my-cluster" / "topics" / "01_benchmarks.md"
    _replace_section(path, "開放問題", "- Custom open question")

    build_subtopic_notes(cfg, "my-cluster")

    assert "- Custom open question" in path.read_text(encoding="utf-8")


def test_write_papers_section_raises_if_section_deleted(tmp_path, monkeypatch):
    from research_hub.topic import _write_papers_section

    cfg = _cfg(tmp_path)
    path = cfg.raw / "my-cluster" / "topics" / "01_benchmarks.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\ncluster: my-cluster\n---\n\n# Benchmarks\n\n## 範圍\n\nKeep.\n\n## Papers\n\nOld.\n\n## 開放問題\n\n- Keep\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "research_hub.topic._extract_sections_excluding_papers",
        lambda text: {} if "(no papers assigned)" in text else {"範圍": "Keep.", "開放問題": "- Keep"},
    )

    with pytest.raises(ValueError, match="delete section '範圍'"):
        _write_papers_section(path, [], {})


def test_extract_sections_excluding_papers_returns_all_non_papers():
    from research_hub.topic import _extract_sections_excluding_papers

    sections = _extract_sections_excluding_papers(
        "# Title\n\n## 範圍\n\nA\n\n## Papers\n\nX\n\n## 核心問題\n\nB\n\n## 開放問題\n\nC\n\n## See also\n\nD\n"
    )

    assert sections == {
        "範圍": "A",
        "核心問題": "B",
        "開放問題": "C",
        "See also": "D",
    }


def test_build_subtopic_notes_double_run_no_content_loss(tmp_path):
    from research_hub.topic import build_subtopic_notes

    cfg = _cfg(tmp_path)
    _write_paper(cfg, "paper-one", subtopics=["alpha"])
    _write_paper(cfg, "paper-two", subtopics=["beta"])
    _write_paper(cfg, "paper-three", subtopics=["gamma"])
    _write_paper(cfg, "paper-four", subtopics=["delta"])
    build_subtopic_notes(cfg, "my-cluster")

    expected: dict[str, str] = {}
    for path in sorted((cfg.raw / "my-cluster" / "topics").glob("*.md")):
        custom = path.stem
        _replace_section(path, "範圍", f"Scope for {custom}.")
        _replace_section(path, "核心問題", f"Why for {custom}.")
        _replace_section(path, "開放問題", f"- Open for {custom}")
        _replace_section(path, "See also", f"- See also {custom}")
        expected[path.name] = path.read_text(encoding="utf-8")

    build_subtopic_notes(cfg, "my-cluster")

    for path in sorted((cfg.raw / "my-cluster" / "topics").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        assert f"Scope for {path.stem}." in text
        assert f"Why for {path.stem}." in text
        assert f"- Open for {path.stem}" in text
        assert f"- See also {path.stem}" in text


def test_write_papers_section_preserves_see_also_across_rebuild(tmp_path):
    from research_hub.topic import build_subtopic_notes

    cfg = _cfg(tmp_path)
    _write_paper(cfg, "paper-one", subtopics=["benchmarks"])
    build_subtopic_notes(cfg, "my-cluster")
    path = cfg.raw / "my-cluster" / "topics" / "01_benchmarks.md"
    _replace_section(path, "See also", "- Custom see also")

    build_subtopic_notes(cfg, "my-cluster")

    assert "- Custom see also" in path.read_text(encoding="utf-8")
