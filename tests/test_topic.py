from __future__ import annotations

from pathlib import Path

import pytest

from research_hub.clusters import ClusterRegistry
from research_hub.topic import (
    OVERVIEW_FILENAME,
    TopicDigest,
    overview_path,
    get_topic_digest,
    read_overview,
    scaffold_overview,
)


class StubConfig:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.raw = root / "raw"
        self.hub = root / "hub"
        self.research_hub_dir = root / ".research_hub"
        self.clusters_file = self.research_hub_dir / "clusters.yaml"
        self.raw.mkdir(parents=True)
        self.hub.mkdir(parents=True)
        self.research_hub_dir.mkdir(parents=True)


def _cfg(tmp_path: Path) -> StubConfig:
    cfg = StubConfig(tmp_path / "vault")
    ClusterRegistry(cfg.clusters_file).create(query="my cluster", name="My Cluster", slug="my-cluster")
    overview = cfg.hub / "my-cluster" / OVERVIEW_FILENAME
    if overview.exists():
        overview.unlink()
    return cfg


def _write_note(
    cfg: StubConfig,
    name: str,
    *,
    title: str = "Paper Title",
    authors: str = "Doe, Jane; Roe, Alex",
    year: str = "2025",
    doi: str = "10.1/example",
    abstract: str = "Abstract line one.\nAbstract line two.",
    frontmatter: bool = True,
) -> Path:
    note_dir = cfg.raw / "my-cluster"
    note_dir.mkdir(parents=True, exist_ok=True)
    path = note_dir / name
    if frontmatter:
        text = (
            "---\n"
            f'title: "{title}"\n'
            f'authors: "{authors}"\n'
            f'year: "{year}"\n'
            f'doi: "{doi}"\n'
            "---\n\n"
            "# Body\n\n"
            "## Abstract\n"
            f"{abstract}\n\n"
            "## Notes\n"
            "Body.\n"
        )
    else:
        text = "# Body\n\n## Abstract\nNo frontmatter abstract.\n"
    path.write_text(text, encoding="utf-8")
    return path


def test_scaffold_overview_writes_template(tmp_path):
    cfg = _cfg(tmp_path)

    path = scaffold_overview(cfg, "my-cluster")

    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "type: topic-overview" in text
    assert "cluster: my-cluster" in text


def test_scaffold_overview_raises_if_exists_without_force(tmp_path):
    cfg = _cfg(tmp_path)
    scaffold_overview(cfg, "my-cluster")

    with pytest.raises(FileExistsError):
        scaffold_overview(cfg, "my-cluster")


def test_scaffold_overview_overwrites_with_force(tmp_path):
    cfg = _cfg(tmp_path)
    path = scaffold_overview(cfg, "my-cluster")
    path.write_text("old", encoding="utf-8")

    scaffold_overview(cfg, "my-cluster", force=True)

    assert "type: topic-overview" in path.read_text(encoding="utf-8")


def test_scaffold_overview_unknown_cluster_raises_valueerror(tmp_path):
    cfg = _cfg(tmp_path)

    with pytest.raises(ValueError, match="unknown cluster"):
        scaffold_overview(cfg, "missing")


def test_get_topic_digest_reads_all_paper_notes(tmp_path):
    cfg = _cfg(tmp_path)
    _write_note(cfg, "paper1.md", title="One")
    _write_note(cfg, "paper2.md", title="Two", doi="10.1/two")

    digest = get_topic_digest(cfg, "my-cluster")

    assert digest.paper_count == 2
    assert [paper.title for paper in digest.papers] == ["One", "Two"]


def test_get_topic_digest_skips_overview_and_index_files(tmp_path):
    cfg = _cfg(tmp_path)
    _write_note(cfg, "paper1.md")
    _write_note(cfg, "index.md", title="Index")
    _write_note(cfg, OVERVIEW_FILENAME, title="Overview")

    digest = get_topic_digest(cfg, "my-cluster")

    assert digest.paper_count == 1
    assert digest.papers[0].slug == "paper1"


def test_get_topic_digest_extracts_abstract_from_body(tmp_path):
    cfg = _cfg(tmp_path)
    _write_note(cfg, "paper1.md", abstract="First paragraph.\nSecond paragraph.")

    digest = get_topic_digest(cfg, "my-cluster")

    assert digest.papers[0].abstract == "First paragraph.\nSecond paragraph."


def test_get_topic_digest_handles_missing_frontmatter_gracefully(tmp_path):
    cfg = _cfg(tmp_path)
    _write_note(cfg, "paper1.md", frontmatter=False)

    digest = get_topic_digest(cfg, "my-cluster")

    assert digest.papers[0].title == "paper1"
    assert digest.papers[0].authors == []
    assert digest.papers[0].year is None


def test_topic_digest_to_markdown_renders_blockquote_abstracts():
    digest = TopicDigest(
        cluster_slug="my-cluster",
        cluster_title="My Cluster",
        paper_count=1,
        papers=[
            type("Paper", (), {
                "title": "Paper One",
                "authors": ["Doe", "Roe"],
                "year": 2025,
                "doi": "10.1/x",
                "abstract": "Line one.\nLine two.",
            })()
        ],
    )

    markdown = digest.to_markdown()

    assert "### Paper One" in markdown
    assert "> Line one.\n> Line two." in markdown


def test_topic_digest_to_markdown_truncates_authors_over_five():
    digest = TopicDigest(
        cluster_slug="my-cluster",
        cluster_title="My Cluster",
        paper_count=1,
        papers=[
            type("Paper", (), {
                "title": "Paper One",
                "authors": ["A", "B", "C", "D", "E", "F", "G"],
                "year": 2025,
                "doi": "",
                "abstract": "",
            })()
        ],
    )

    markdown = digest.to_markdown()

    assert "*A, B, C, D, E +2 more*" in markdown


def test_read_overview_returns_none_when_missing(tmp_path):
    cfg = _cfg(tmp_path)

    assert read_overview(cfg, "my-cluster") is None


def test_read_overview_returns_content_when_present(tmp_path):
    cfg = _cfg(tmp_path)
    path = overview_path(cfg, "my-cluster")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Overview", encoding="utf-8")

    assert read_overview(cfg, "my-cluster") == "# Overview"
