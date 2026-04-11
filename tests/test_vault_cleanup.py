"""Tests for vault.cleanup.dedup_hub_pages."""

from __future__ import annotations

from research_hub.vault.cleanup import (
    DedupReport,
    dedup_hub_pages,
    dedup_wikilinks_in_file,
)


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_dedup_wikilinks_in_file_removes_exact_duplicates(tmp_path):
    p = tmp_path / "page.md"
    _write(p, "# Page\n\n- [[alpha]]\n- [[beta]]\n- [[alpha]]\n- [[alpha]]\n- [[gamma]]\n")
    removed = dedup_wikilinks_in_file(p)
    assert removed == 2
    result = p.read_text(encoding="utf-8")
    assert result.count("[[alpha]]") == 1
    assert "[[beta]]" in result
    assert "[[gamma]]" in result


def test_dedup_wikilinks_preserves_non_link_content(tmp_path):
    p = tmp_path / "page.md"
    _write(
        p,
        "---\ntitle: Test\n---\n\n# Heading\n\nParagraph text.\n\n- [[alpha]]\n- [[alpha]]\n\n## Section\n\nMore prose.\n",
    )
    removed = dedup_wikilinks_in_file(p)
    assert removed == 1
    result = p.read_text(encoding="utf-8")
    assert "Paragraph text." in result
    assert "## Section" in result
    assert "More prose." in result


def test_dedup_wikilinks_no_change_on_unique_links(tmp_path):
    p = tmp_path / "page.md"
    _write(p, "- [[a]]\n- [[b]]\n- [[c]]\n")
    removed = dedup_wikilinks_in_file(p)
    assert removed == 0


def test_dedup_wikilinks_missing_file_returns_zero(tmp_path):
    assert dedup_wikilinks_in_file(tmp_path / "missing.md") == 0


def test_dedup_hub_pages_walks_recursively(tmp_path):
    hub = tmp_path / "hub"
    _write(hub / "root.md", "- [[x]]\n- [[x]]\n")
    _write(hub / "sub" / "child.md", "- [[y]]\n- [[y]]\n- [[y]]\n")
    _write(hub / "sub" / "ok.md", "- [[unique]]\n")
    report = dedup_hub_pages(hub)
    assert report.files_scanned == 3
    assert report.files_modified == 2
    assert report.wikilinks_removed == 3  # 1 from root + 2 from child
    assert set(report.per_file.keys()) == {"root.md", "sub\\child.md"} or set(
        report.per_file.keys()
    ) == {"root.md", "sub/child.md"}


def test_dedup_hub_pages_dry_run_does_not_write(tmp_path):
    hub = tmp_path / "hub"
    p = hub / "page.md"
    _write(p, "- [[a]]\n- [[a]]\n")
    original = p.read_text(encoding="utf-8")
    report = dedup_hub_pages(hub, dry_run=True)
    assert report.wikilinks_removed == 1
    assert report.files_modified == 1
    assert p.read_text(encoding="utf-8") == original


def test_dedup_hub_pages_empty_report_for_missing_dir(tmp_path):
    report = dedup_hub_pages(tmp_path / "nowhere")
    assert isinstance(report, DedupReport)
    assert report.files_scanned == 0
    assert report.wikilinks_removed == 0
