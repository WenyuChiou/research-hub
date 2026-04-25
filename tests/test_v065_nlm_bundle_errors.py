from __future__ import annotations

import json
from pathlib import Path
from types import ModuleType, SimpleNamespace

from research_hub.notebooklm.bundle import bundle_cluster


def _cfg(tmp_path: Path) -> SimpleNamespace:
    root = tmp_path / "vault"
    raw = root / "raw"
    hub = root / ".research_hub"
    raw.mkdir(parents=True)
    hub.mkdir()
    return SimpleNamespace(root=root, raw=raw, research_hub_dir=hub)


def _cluster() -> SimpleNamespace:
    return SimpleNamespace(slug="alpha", name="Alpha")


def _note(path: Path, frontmatter: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(frontmatter, encoding="utf-8")
    return path


def _install_list_cluster_notes(monkeypatch, notes: list[Path]) -> None:
    module = ModuleType("research_hub.vault.sync")
    module.list_cluster_notes = lambda _slug, _raw: notes
    monkeypatch.setitem(__import__("sys").modules, "research_hub.vault.sync", module)


def test_bundle_empty_cluster_returns_empty_bundle_no_crash(tmp_path: Path, monkeypatch, capsys):
    cfg = _cfg(tmp_path)
    _install_list_cluster_notes(monkeypatch, [])

    report = bundle_cluster(_cluster(), cfg)

    assert report.entries == []
    assert report.pdf_count == 0
    assert report.url_count == 0
    assert report.skip_count == 0
    manifest = json.loads((report.bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["entries"] == []
    assert "bundle summary - alpha" in capsys.readouterr().out


def test_bundle_missing_pdf_and_url_marks_note_skipped(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    note = _note(
        cfg.raw / "alpha" / "paper.md",
        "---\n"
        "title: Missing PDF\n"
        "doi: 10.1000/missing\n"
        "url: not-a-url\n"
        "---\n",
    )
    _install_list_cluster_notes(monkeypatch, [note])

    report = bundle_cluster(_cluster(), cfg)

    assert len(report.entries) == 1
    entry = report.entries[0]
    assert entry.action == "url"
    assert entry.url == "https://doi.org/10.1000/missing"


def test_bundle_author_year_pdf_fallback_copies_local_pdf(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    pdfs_dir = cfg.root / "pdfs"
    pdfs_dir.mkdir()
    source_pdf = pdfs_dir / "Ben-Zion_2025.pdf"
    source_pdf.write_bytes(b"%PDF-1.4\n")
    note = _note(
        cfg.raw / "alpha" / "paper.md",
        "---\n"
        "title: Author Year Match\n"
        "authors: Ben-Zion, Yair\n"
        "year: 2025\n"
        "---\n",
    )
    _install_list_cluster_notes(monkeypatch, [note])

    report = bundle_cluster(_cluster(), cfg)

    entry = report.entries[0]
    assert entry.action == "pdf"
    assert entry.pdf_source == "local-slug"
    assert Path(entry.pdf_path).read_bytes() == b"%PDF-1.4\n"


def test_bundle_fetch_failure_falls_back_to_url(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    note = _note(
        cfg.raw / "alpha" / "paper.md",
        "---\n"
        "title: Fetch Failure\n"
        "doi: 10.1000/fetch\n"
        "---\n",
    )
    _install_list_cluster_notes(monkeypatch, [note])
    fetcher = ModuleType("research_hub.notebooklm.pdf_fetcher")
    fetcher.fetch_paper_pdf = lambda *_args, **_kwargs: SimpleNamespace(
        ok=False,
        path=None,
        source="",
        error="no OA copy",
    )
    monkeypatch.setitem(__import__("sys").modules, "research_hub.notebooklm.pdf_fetcher", fetcher)

    report = bundle_cluster(_cluster(), cfg, download_pdfs=True)

    entry = report.entries[0]
    assert entry.action == "url"
    assert entry.url == "https://doi.org/10.1000/fetch"
    assert entry.skip_reason == "no OA; url fallback used"


def test_bundle_prefers_doi_named_pdf_before_url(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    pdfs_dir = cfg.root / "pdfs"
    pdfs_dir.mkdir()
    source_pdf = pdfs_dir / "10.1000_exact.pdf"
    source_pdf.write_bytes(b"%PDF")
    note = _note(
        cfg.raw / "alpha" / "paper.md",
        "---\n"
        "title: DOI Match\n"
        "doi: 10.1000/exact\n"
        "url: https://example.com/fallback\n"
        "---\n",
    )
    _install_list_cluster_notes(monkeypatch, [note])

    report = bundle_cluster(_cluster(), cfg)

    entry = report.entries[0]
    assert entry.action == "pdf"
    assert entry.pdf_source == "local-doi"
    assert entry.url == ""


def test_bundle_manifest_and_sources_file_match_url_entries(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    note = _note(
        cfg.raw / "alpha" / "paper.md",
        "---\n"
        "title: URL Only\n"
        "url: https://example.com/paper\n"
        "---\n",
    )
    _install_list_cluster_notes(monkeypatch, [note])

    report = bundle_cluster(_cluster(), cfg)

    manifest = json.loads((report.bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["url_count"] == 1
    assert manifest["entries"][0]["url"] == "https://example.com/paper"
    assert (report.bundle_dir / "sources.txt").read_text(encoding="utf-8").strip() == "https://example.com/paper"
