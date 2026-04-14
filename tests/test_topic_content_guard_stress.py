from __future__ import annotations

from pathlib import Path
import re

import pytest

from research_hub.clusters import ClusterRegistry
from research_hub.topic import SUBTOPIC_TEMPLATE, _extract_sections_excluding_papers, _write_papers_section, build_subtopic_notes

SUBTOPIC_SECTIONS = [heading for heading in re.findall(r"^##\s+(.+?)\s*$", SUBTOPIC_TEMPLATE, re.MULTILINE) if heading != "Papers"]


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


def _make_note(cfg: StubConfig) -> Path:
    _write_paper(cfg, "paper-one", subtopics=["benchmarks"])
    build_subtopic_notes(cfg, "my-cluster")
    return cfg.raw / "my-cluster" / "topics" / "01_benchmarks.md"


@pytest.mark.parametrize("section", SUBTOPIC_SECTIONS)
def test_content_guard_raises_on_section_deletion(tmp_path, section, monkeypatch):
    path = _make_note(_cfg(tmp_path))
    real_extract = _extract_sections_excluding_papers

    def fake_extract(text: str) -> dict[str, str]:
        sections = real_extract(text)
        if "(no papers assigned)" in text:
            sections.pop(section, None)
        return sections

    monkeypatch.setattr("research_hub.topic._extract_sections_excluding_papers", fake_extract)

    with pytest.raises(ValueError, match=re.escape(section)):
        _write_papers_section(path, [], {})


@pytest.mark.parametrize("section", SUBTOPIC_SECTIONS)
def test_content_guard_raises_on_section_modification(tmp_path, section, monkeypatch):
    path = _make_note(_cfg(tmp_path))
    real_extract = _extract_sections_excluding_papers

    def fake_extract(text: str) -> dict[str, str]:
        sections = real_extract(text)
        if "(no papers assigned)" in text and section in sections:
            sections[section] = sections[section] + "\nMUTATED"
        return sections

    monkeypatch.setattr("research_hub.topic._extract_sections_excluding_papers", fake_extract)

    with pytest.raises(ValueError, match=re.escape(section)):
        _write_papers_section(path, [], {})


def test_content_guard_allows_papers_section_mutation(tmp_path):
    cfg = _cfg(tmp_path)
    _write_paper(cfg, "paper-one", subtopics=["benchmarks"])
    build_subtopic_notes(cfg, "my-cluster")
    path = cfg.raw / "my-cluster" / "topics" / "01_benchmarks.md"

    _write_paper(cfg, "paper-two", subtopics=["benchmarks"])
    build_subtopic_notes(cfg, "my-cluster")

    text = path.read_text(encoding="utf-8")
    assert "[[paper-one|" in text
    assert "[[paper-two|" in text


def test_content_guard_survives_unicode_section_titles():
    sections = _extract_sections_excluding_papers(
        "# Title\n\n## 蝭?\n\nA\n\n## Papers\n\nX\n\n## ?詨???\n\nB\n\n## See also\n\nC\n"
    )

    assert sections["蝭?"] == "A"
    assert sections["?詨???"] == "B"
    assert sections["See also"] == "C"
