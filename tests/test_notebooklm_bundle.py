"""Tests for notebooklm.bundle."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from research_hub.clusters import Cluster
from research_hub.notebooklm.bundle import (
    _find_pdf_for_doi,
    _parse_note_metadata,
    _pick_url,
    bundle_cluster,
)


def _note(
    path: Path,
    doi: str,
    title: str = "Paper",
    topic_cluster: str = "alpha",
    url: str = "",
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'---\ntitle: "{title}"\ndoi: "{doi}"\nurl: "{url}"\ntopic_cluster: "{topic_cluster}"\n---\n\n# {title}\n',
        encoding="utf-8",
    )
    return path


class StubCfg:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.raw = root / "raw"
        self.logs = root / "logs"
        self.research_hub_dir = root / ".research_hub"


def test_parse_note_metadata_extracts_title_doi_url(tmp_path):
    path = _note(tmp_path / "note.md", doi="10.1/a", title="Alpha Paper", url="https://example.com/a")
    meta = _parse_note_metadata(path)
    assert meta["title"] == "Alpha Paper"
    assert meta["doi"] == "10.1/a"
    assert meta["url"] == "https://example.com/a"


def test_find_pdf_for_doi_matches_tail_substring(tmp_path):
    pdfs = tmp_path / "pdfs"
    pdfs.mkdir()
    target = pdfs / "s41599-024-03611-3.pdf"
    target.write_bytes(b"fake pdf")
    found = _find_pdf_for_doi(pdfs, "10.1057/s41599-024-03611-3")
    assert found == target


def test_find_pdf_for_doi_returns_none_when_missing(tmp_path):
    pdfs = tmp_path / "pdfs"
    pdfs.mkdir()
    assert _find_pdf_for_doi(pdfs, "10.9999/nothing") is None


def test_pick_url_prefers_doi():
    assert _pick_url({"doi": "10.1/a", "url": "https://x.com"}) == "https://doi.org/10.1/a"


def test_pick_url_arxiv_rewrites_to_abs():
    assert (
        _pick_url({"doi": "10.48550/arxiv.2502.10978", "url": ""})
        == "https://arxiv.org/abs/2502.10978"
    )


def test_pick_url_falls_back_to_url_field():
    assert (
        _pick_url({"doi": "", "url": "https://arxiv.org/abs/2301.99999"})
        == "https://arxiv.org/abs/2301.99999"
    )


def test_bundle_cluster_emits_pdfs_urls_and_readme(tmp_path):
    cfg = StubCfg(tmp_path)
    cfg.raw.mkdir(parents=True)
    (cfg.root / "pdfs").mkdir()
    cfg.research_hub_dir.mkdir(parents=True)

    _note(cfg.raw / "alpha" / "a.md", doi="10.1/a", topic_cluster="alpha")
    (cfg.root / "pdfs" / "10.1_a.pdf").write_bytes(b"pdf-a")
    _note(cfg.raw / "alpha" / "b.md", doi="10.48550/arxiv.2502.10978", topic_cluster="alpha")
    _note(cfg.raw / "alpha" / "c.md", doi="", url="", topic_cluster="alpha", title="No source")

    cluster = Cluster(slug="alpha", name="Alpha Cluster", obsidian_subfolder="alpha")
    report = bundle_cluster(cluster, cfg)

    assert report.pdf_count == 1
    assert report.url_count == 1
    assert report.skip_count == 1
    assert (report.bundle_dir / "README.md").exists()
    assert (report.bundle_dir / "manifest.json").exists()
    assert (report.bundle_dir / "sources.txt").exists()

    manifest = json.loads((report.bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["pdf_count"] == 1
    assert manifest["url_count"] == 1
    assert manifest["skip_count"] == 1

    sources = (report.bundle_dir / "sources.txt").read_text(encoding="utf-8").strip().splitlines()
    assert len(sources) == 1
    assert "arxiv.org/abs/2502.10978" in sources[0]


def test_bundle_with_download_pdfs_flag_calls_fetcher(tmp_path):
    cfg = StubCfg(tmp_path)
    cfg.raw.mkdir(parents=True)
    cfg.research_hub_dir.mkdir(parents=True)
    _note(cfg.raw / "alpha" / "missing.md", doi="10.1/missing", topic_cluster="alpha")
    cluster = Cluster(slug="alpha", name="Alpha Cluster", obsidian_subfolder="alpha")

    with patch("research_hub.notebooklm.pdf_fetcher.fetch_paper_pdf") as fetcher:
        fetcher.return_value.ok = False
        fetcher.return_value.source = "not-found"
        fetcher.return_value.error = "missing"
        bundle_cluster(cluster, cfg, download_pdfs=True)

    fetcher.assert_called_once()


def test_bundle_without_flag_skips_fetcher(tmp_path):
    cfg = StubCfg(tmp_path)
    cfg.raw.mkdir(parents=True)
    cfg.research_hub_dir.mkdir(parents=True)
    _note(cfg.raw / "alpha" / "missing.md", doi="10.1/missing", topic_cluster="alpha")
    cluster = Cluster(slug="alpha", name="Alpha Cluster", obsidian_subfolder="alpha")

    with patch("research_hub.notebooklm.pdf_fetcher.fetch_paper_pdf") as fetcher:
        bundle_cluster(cluster, cfg, download_pdfs=False)

    fetcher.assert_not_called()


def test_bundle_records_pdf_source_in_entry(tmp_path):
    cfg = StubCfg(tmp_path)
    cfg.raw.mkdir(parents=True)
    cfg.research_hub_dir.mkdir(parents=True)
    _note(cfg.raw / "alpha" / "missing.md", doi="10.1/missing", topic_cluster="alpha")
    cluster = Cluster(slug="alpha", name="Alpha Cluster", obsidian_subfolder="alpha")
    downloaded = tmp_path / "downloaded.pdf"
    downloaded.write_bytes(b"pdf")

    class Result:
        ok = True
        path = downloaded
        source = "unpaywall"
        error = ""

    with patch("research_hub.notebooklm.pdf_fetcher.fetch_paper_pdf", return_value=Result()):
        report = bundle_cluster(cluster, cfg, download_pdfs=True)

    assert report.entries[0].action == "pdf"
    assert report.entries[0].pdf_source == "unpaywall"


def test_bundle_falls_back_to_url_when_fetch_returns_not_found(tmp_path):
    cfg = StubCfg(tmp_path)
    cfg.raw.mkdir(parents=True)
    cfg.research_hub_dir.mkdir(parents=True)
    _note(
        cfg.raw / "alpha" / "missing.md",
        doi="10.1/missing",
        topic_cluster="alpha",
        url="https://example.com/paper",
    )
    cluster = Cluster(slug="alpha", name="Alpha Cluster", obsidian_subfolder="alpha")

    class Result:
        ok = False
        path = None
        source = "not-found"
        error = "missing"

    with patch("research_hub.notebooklm.pdf_fetcher.fetch_paper_pdf", return_value=Result()):
        report = bundle_cluster(cluster, cfg, download_pdfs=True)

    assert report.entries[0].action == "url"
    assert report.entries[0].url == "https://doi.org/10.1/missing"
    assert report.entries[0].skip_reason == "no OA; url fallback used"
