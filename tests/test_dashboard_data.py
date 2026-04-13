from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from research_hub.clusters import ClusterRegistry
from research_hub.dedup import DedupHit, DedupIndex
from research_hub.dashboard.briefing import load_briefing_preview
from research_hub.dashboard.citation import build_bibtex_for_cluster, build_bibtex_for_paper
from research_hub.dashboard.data import collect_dashboard_data
from research_hub.dashboard.drift import detect_drift
from research_hub.dashboard.types import ClusterCard, PaperRow


class StubConfig:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.raw = root / "raw"
        self.research_hub_dir = root / ".research_hub"
        self.clusters_file = self.research_hub_dir / "clusters.yaml"
        self.no_zotero = False


def _make_config(tmp_path: Path) -> StubConfig:
    cfg = StubConfig(tmp_path / "vault")
    cfg.raw.mkdir(parents=True)
    cfg.research_hub_dir.mkdir(parents=True)
    return cfg


def _write_note(
    cfg: StubConfig,
    cluster_slug: str,
    filename: str,
    *,
    title: str = "Test paper",
    authors: str = "Doe, Jane",
    year: str = "2025",
    doi: str = "10.1/test",
    abstract: str = "Abstract body",
    status: str = "unread",
    ingested_at: str = "2026-04-12T10:00:00Z",
    topic_cluster: str | None = None,
    zotero_key: str = "ABCD1234",
) -> Path:
    note_dir = cfg.raw / cluster_slug
    note_dir.mkdir(parents=True, exist_ok=True)
    note_path = note_dir / filename
    assigned_cluster = cluster_slug if topic_cluster is None else topic_cluster
    zotero_line = f'zotero-key: "{zotero_key}"\n' if zotero_key is not None else ""
    note_path.write_text(
        f"""---
title: "{title}"
authors: "{authors}"
year: "{year}"
doi: "{doi}"
abstract: "{abstract}"
topic_cluster: "{assigned_cluster}"
status: "{status}"
ingested_at: "{ingested_at}"
tags: ["tag-a", "tag-b"]
{zotero_line}---
Body
""",
        encoding="utf-8",
    )
    return note_path


def test_load_briefing_preview_strips_header(tmp_path):
    artifacts = tmp_path / "artifacts" / "alpha"
    artifacts.mkdir(parents=True)
    body = "This is the actual briefing body."
    (artifacts / "brief-20260412T220106Z.txt").write_text(
        "# Alpha\n\nSource: https://notebooklm.google.com/notebook/x\nDownloaded: 20260412T220106Z\nSources: 0\nSaved briefings: One\n\n"
        + body,
        encoding="utf-8",
    )

    preview = load_briefing_preview("alpha", "Alpha", {}, artifacts)

    assert preview is not None
    assert preview.preview_text.startswith(body)
    assert preview.full_text == body
    assert preview.char_count == len(body)


def test_load_briefing_preview_returns_none_when_missing(tmp_path):
    preview = load_briefing_preview("alpha", "Alpha", {}, tmp_path / "missing")
    assert preview is None


def test_load_briefing_preview_truncates_at_word_boundary(tmp_path):
    artifacts = tmp_path / "artifacts" / "alpha"
    artifacts.mkdir(parents=True)
    body = ("word " * 200).strip()
    (artifacts / "brief-20260412T220106Z.txt").write_text(
        "# Alpha\n\nSource: x\nDownloaded: y\nSources: 0\n\n" + body,
        encoding="utf-8",
    )

    preview = load_briefing_preview("alpha", "Alpha", {}, artifacts, char_limit=500)

    assert preview is not None
    assert len(preview.preview_text) <= 500
    assert not preview.preview_text.endswith(" ")
    assert preview.full_text == body


def test_build_bibtex_for_paper_analyst_fallback():
    paper = PaperRow(slug="paper-1", title="Alpha", authors="Doe, Jane", year="2025", abstract="", doi="10.1/a")
    bibtex = build_bibtex_for_paper(paper, zot=None)
    assert "@article{paper-1," in bibtex
    assert "title  = {Alpha}" in bibtex
    assert "doi    = {10.1/a}" in bibtex


def test_build_bibtex_for_paper_researcher_calls_zotero():
    paper = PaperRow(slug="paper-1", title="Alpha", authors="Doe, Jane", year="2025", abstract="", doi="10.1/a", zotero_key="KEY1")
    zot = Mock()
    zot.get_formatted.return_value = "@article{KEY1}"

    bibtex = build_bibtex_for_paper(paper, zot=zot)

    assert bibtex == "@article{KEY1}"
    zot.get_formatted.assert_called_once_with("KEY1", "bibtex")


def test_build_bibtex_for_paper_falls_back_to_frontmatter_on_zotero_error():
    """When the Zotero API call fails, we still emit a frontmatter
    BibTeX entry instead of an empty string — the [Cite] button must
    always have something to copy."""
    paper = PaperRow(slug="paper-1", title="Alpha", authors="Doe, Jane", year="2025", abstract="", doi="10.1/a", zotero_key="KEY1")
    zot = Mock()
    zot.get_formatted.side_effect = RuntimeError("boom")

    result = build_bibtex_for_paper(paper, zot=zot)
    assert "@article{paper-1" in result
    assert "title  = {Alpha}" in result
    assert "doi    = {10.1/a}" in result


def test_build_bibtex_for_cluster_concatenates_papers():
    cluster = ClusterCard(
        slug="alpha",
        name="Alpha",
        papers=[
            PaperRow(slug="a", title="A", authors="", year="", abstract="", doi="", bibtex="@a"),
            PaperRow(slug="b", title="B", authors="", year="", abstract="", doi="", bibtex=""),
            PaperRow(slug="c", title="C", authors="", year="", abstract="", doi="", bibtex="@c"),
        ],
    )
    assert build_bibtex_for_cluster(cluster) == "@a\n\n@c"


def test_detect_drift_finds_folder_mismatch(tmp_path):
    cfg = _make_config(tmp_path)
    _write_note(cfg, "A", "paper.md", topic_cluster="B")

    alerts = detect_drift(cfg, DedupIndex.empty())

    assert len(alerts) == 1
    assert alerts[0].kind == "folder_mismatch"
    assert "paper.md" in alerts[0].sample_paths[0]


def test_detect_drift_finds_orphan_note(tmp_path):
    cfg = _make_config(tmp_path)
    note_dir = cfg.raw / "alpha"
    note_dir.mkdir(parents=True)
    (note_dir / "paper.md").write_text(
        '---\ntitle: "No Cluster"\n---\nBody\n',
        encoding="utf-8",
    )

    alerts = detect_drift(cfg, DedupIndex.empty())

    assert len(alerts) == 1
    assert alerts[0].kind == "orphan_note"


def test_detect_drift_clean_vault_returns_empty(tmp_path):
    cfg = _make_config(tmp_path)
    _write_note(cfg, "alpha", "paper.md")
    assert detect_drift(cfg, DedupIndex.empty()) == []


def test_collect_dashboard_data_persona_researcher(tmp_path, monkeypatch):
    cfg = _make_config(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    _write_note(cfg, "agents", "paper-1.md", ingested_at="2026-04-12T10:00:00Z")
    _write_note(cfg, "agents", "paper-2.md", ingested_at="2026-04-11T10:00:00Z", zotero_key="KEY2")
    monkeypatch.setattr("research_hub.dashboard.data.run_doctor", lambda: [])
    monkeypatch.setattr("research_hub.dashboard.data.detect_drift", lambda cfg, dedup: [])
    zot = Mock()
    zot.get_formatted.return_value = "@article{key}"

    data = collect_dashboard_data(cfg, zot=zot)

    assert data.persona == "researcher"
    assert data.total_papers == 2
    assert data.clusters[0].papers[0].in_obsidian is True
    assert all(paper.bibtex for paper in data.clusters[0].papers)


def test_collect_dashboard_data_persona_analyst(tmp_path, monkeypatch):
    cfg = _make_config(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    _write_note(cfg, "agents", "paper-1.md")
    _write_note(cfg, "agents", "paper-2.md", zotero_key="")
    monkeypatch.setenv("RESEARCH_HUB_NO_ZOTERO", "1")
    monkeypatch.setattr("research_hub.dashboard.data.run_doctor", lambda: [])
    monkeypatch.setattr("research_hub.dashboard.data.detect_drift", lambda cfg, dedup: [])

    data = collect_dashboard_data(cfg, zot=None)

    assert data.persona == "analyst"
    assert data.show_zotero_column is False
    assert all(paper.bibtex == "" for paper in data.clusters[0].papers)


def test_collect_dashboard_data_briefings_picked_up(tmp_path, monkeypatch):
    cfg = _make_config(tmp_path)
    ClusterRegistry(cfg.clusters_file).create(query="agents", name="Agents", slug="agents")
    _write_note(cfg, "agents", "paper-1.md")
    artifacts = cfg.research_hub_dir / "artifacts" / "agents"
    artifacts.mkdir(parents=True)
    (artifacts / "brief-20260412T120000Z.txt").write_text(
        "# Agents\n\nSource: https://notebooklm.google.com/notebook/x\nDownloaded: 20260412T120000Z\nSources: 0\n\nBrief body here.",
        encoding="utf-8",
    )
    (cfg.research_hub_dir / "nlm_cache.json").write_text(
        json.dumps(
            {
                "agents": {
                    "notebook_url": "https://notebooklm.google.com/notebook/x",
                    "artifacts": {
                        "brief": {
                            "downloaded_at": "2026-04-12T12:00:00Z",
                            "titles": ["Brief A"],
                        }
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("research_hub.dashboard.data.run_doctor", lambda: [])
    monkeypatch.setattr("research_hub.dashboard.data.detect_drift", lambda cfg, dedup: [])

    data = collect_dashboard_data(cfg, zot=None)

    assert len(data.briefings) == 1
    assert data.briefings[0].preview_text.startswith("Brief body here.")


def test_detect_drift_duplicate_doi_requires_both_sources_and_conflicting_clusters(tmp_path):
    cfg = _make_config(tmp_path)
    dedup = DedupIndex(
        doi_to_hits={
            "10.1/x": [
                DedupHit(source="zotero", doi="10.1/x", zotero_key="K1"),
                DedupHit(source="obsidian", doi="10.1/x", obsidian_path=str(cfg.raw / "alpha" / "a.md")),
                DedupHit(source="obsidian", doi="10.1/x", obsidian_path=str(cfg.raw / "beta" / "b.md")),
            ]
        }
    )

    alerts = detect_drift(cfg, dedup)

    assert any(alert.kind == "duplicate_doi" for alert in alerts)
