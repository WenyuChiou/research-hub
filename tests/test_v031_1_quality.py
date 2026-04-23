"""v0.31.1 quality fix tests."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from research_hub.clusters import ClusterRegistry


def _make_cfg(tmp_path: Path):
    root = tmp_path / "vault"
    raw = root / "raw"
    hub = root / "hub"
    research_hub_dir = root / ".research_hub"
    raw.mkdir(parents=True)
    hub.mkdir(parents=True)
    research_hub_dir.mkdir(parents=True)
    return SimpleNamespace(
        raw=raw,
        hub=hub,
        research_hub_dir=research_hub_dir,
        clusters_file=research_hub_dir / "clusters.yaml",
    )


def test_pdf_title_uses_first_line_when_no_heading_marker(tmp_path):
    from research_hub import importer

    fake_pdf = tmp_path / "test.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4")

    with patch.object(importer, "_pdf_metadata_title", return_value=None):
        title = importer._derive_title_for_kind("My Real Title\n\nBody content here.", fake_pdf, "pdf")

    assert title == "My Real Title"


def test_docx_title_uses_extractor_provided_title(tmp_path):
    from research_hub.importer import _derive_title_for_kind

    title = _derive_title_for_kind(
        "irrelevant body",
        tmp_path / "x.docx",
        "docx",
        title_hint="Heading From DOCX",
    )

    assert title == "Heading From DOCX"


def test_markdown_title_still_uses_h1(tmp_path):
    from research_hub.importer import _derive_title_for_kind

    title = _derive_title_for_kind("# Real H1 Title\n\nBody.", tmp_path / "doc.md", "markdown")

    assert title == "Real H1 Title"


def test_clusters_delete_purge_folder_removes_raw_and_hub_dirs(tmp_path, monkeypatch, capsys):
    from research_hub.cli import _clusters_delete

    cfg = _make_cfg(tmp_path)
    slug = "test-purge"
    raw_dir = cfg.raw / slug
    hub_dir = cfg.hub / slug
    raw_dir.mkdir(parents=True)
    hub_dir.mkdir(parents=True)
    (raw_dir / "note.md").write_text("---\ntopic_cluster: test-purge\n---\n", encoding="utf-8")
    (hub_dir / "overview.md").write_text("# Hub", encoding="utf-8")

    registry = ClusterRegistry(cfg.clusters_file)
    registry.create(query="test", slug=slug, name="Test Purge")

    monkeypatch.setattr("research_hub.cli.get_config", lambda: cfg)
    monkeypatch.setattr("research_hub.clusters.get_config", lambda: cfg)

    rc = _clusters_delete(slug, dry_run=False, purge_folder=True)

    # v0.62: _clusters_delete now calls cascade_delete_cluster which moves
    # raw/<slug> to raw/_deleted_<slug> and removes hub/<slug>. Output is a
    # human-readable cascade summary (not JSON).
    assert rc == 0
    assert not raw_dir.exists()
    assert not hub_dir.exists()
    assert (cfg.raw / f"_deleted_{slug}").exists()
    out = capsys.readouterr().out
    assert slug in out
    assert "Obsidian papers:" in out
